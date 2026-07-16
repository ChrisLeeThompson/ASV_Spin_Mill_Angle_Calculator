"""QObject controller for the Position Alignment automation.

Thin Qt orchestration over the Qt-free
:mod:`asv_spin_mill_angle_calc.alignment_sequence`: each Start press
spawns a single-shot ``_AlignmentWorker`` on its own ``QThread`` (the
``microscope_controller`` connect-worker wiring, including the
identity-guarded cleanup and the ``start_worker`` test seam), streams
frames into the ``FrameImageProvider`` plus fit maps to QML, and maps
the sequence's terminal outcome onto the viewer's border-state
choreography:

    ALIGNED -> "success" (green), STOPPED/REFUSED -> "idle",
    NOT_FOUND / NOT_CONVERGED / ERROR / TILT_LIMIT -> "exception"
    (amber); TILT_LIMIT additionally raises the modal dialog via
    ``tiltLimitExceeded``.

Stop is cooperative: the worker's stop event lands at the sequence's
next hardware-call boundary (blocking SDK calls cannot be interrupted),
so the UI immediately shows a distinct "stopping" state while the
in-flight operation completes.

The user inputs (target milling angle, AOI diameter, use-beam-shift)
are pushed one-way from QML via Binding elements and snapshotted into
an immutable ``AlignmentParams`` at Start — mid-run edits apply to the
next run. Confirm/Clear (the results tables) land in phase 6.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot

from asv_spin_mill_angle_calc.alignment_config import (
    DEFAULT_ALIGNMENT_CONFIG,
    AlignmentConfig,
)
from asv_spin_mill_angle_calc.alignment_sequence import (
    AlignmentOutcome,
    AlignmentParams,
    AlignmentResult,
    AlignmentSequence,
)
from asv_spin_mill_angle_calc.ellipse_detector import EllipseFit
from asv_spin_mill_angle_calc.frame_image_provider import (
    FrameImageProvider,
    numpy_to_qimage,
)
from asv_spin_mill_angle_calc.microscope_ops import (
    MicroscopeOps,
    PositionRecord,
    read_position_record,
)
from asv_spin_mill_angle_calc.position_alignment_models import (
    ConfirmedPositionsModel,
)
from asv_spin_mill_angle_calc.sem_geometry_calculator import (
    SEMGeometryCalculator,
    SEMGeometryInputs,
    SEMGeometryStatus,
    SemPositionCandidate,
    SOURCE_ALTERNATE,
    SOURCE_CALCULATED,
)
from asv_spin_mill_angle_calc import sem_geometry_result_formatter as formatter
from asv_spin_mill_angle_calc.sem_positions_models import (
    SemCandidatePositionsModel,
)

logger = logging.getLogger(__name__)

# Minimum confirmed positions for the SEM geometry calculation (three
# points exactly determine the sinusoid fit).
MIN_POSITIONS_FOR_SEM = 3

# Status Log retention (session-long scrollback, oldest lines dropped).
_LOG_MAX_LINES = 500
# Thin rule between runs (U+2500 box drawing reads as a line in text).
_RUN_SEPARATOR = "─" * 40

# Viewer/card visual states (the QML maps these onto border colors).
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_SUCCESS = "success"
STATE_EXCEPTION = "exception"

# Controller run states (module-private, microscope_controller idiom).
_RUN_IDLE = "idle"
_RUN_RUNNING = "running"
_RUN_STOPPING = "stopping"

_VIEWER_STATE_BY_OUTCOME = {
    AlignmentOutcome.ALIGNED: STATE_SUCCESS,
    AlignmentOutcome.STOPPED: STATE_IDLE,
    AlignmentOutcome.REFUSED: STATE_IDLE,
    AlignmentOutcome.NOT_FOUND: STATE_EXCEPTION,
    AlignmentOutcome.TILT_LIMIT: STATE_EXCEPTION,
    AlignmentOutcome.NOT_CONVERGED: STATE_EXCEPTION,
    AlignmentOutcome.ERROR: STATE_EXCEPTION,
}


def fit_to_map(fit: Optional[EllipseFit], frame_shape,
               pixel_size_m: float) -> dict:
    """EllipseFit -> the QML ellipseFit map contract ({} when None)."""
    if fit is None:
        return {}
    height, width = frame_shape[:2]
    image_dx_m = (fit.center_x_px - width / 2.0) * pixel_size_m
    image_dy_m = (fit.center_y_px - height / 2.0) * pixel_size_m
    return {
        "valid": True,
        "centerXPx": fit.center_x_px,
        "centerYPx": fit.center_y_px,
        "majorRadiusPx": fit.semi_major_px,
        "minorRadiusPx": fit.semi_minor_px,
        "rotationDeg": fit.tilt_deg,
        "millingAngleDeg": fit.milling_angle_deg,
        "widthUm": round(2 * fit.semi_major_px * pixel_size_m * 1e6, 1),
        "heightUm": round(2 * fit.semi_minor_px * pixel_size_m * 1e6, 1),
        "offsetXUm": round(image_dx_m * 1e6, 1),
        "offsetYUm": round(image_dy_m * 1e6, 1),
    }


class _AlignmentWorker(QObject):
    """Single-shot worker running one AlignmentSequence. Do not reuse.

    The sequence itself never raises; frames go to the image provider
    directly from this thread (the provider is lock-guarded) while the
    fit map and status text marshal to the GUI thread via queued
    signals.
    """

    statusUpdated = Signal(str)
    frameReady = Signal(object)     # ellipseFit map (may be {})
    finished = Signal(object)       # AlignmentResult

    def __init__(self, sequence: AlignmentSequence,
                 provider: Optional[FrameImageProvider],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sequence = sequence
        self._provider = provider
        self._stop_event = threading.Event()
        # Stashed before finished is emitted; readable after deleteLater
        # (plain Python attribute), mirroring _ConnectWorker.client.
        self.result: AlignmentResult | None = None

    def stop(self) -> None:
        """Request a cooperative stop; safe from any thread."""
        self._stop_event.set()

    @Slot()
    def run(self) -> None:
        result = self._sequence.run(
            self._stop_event,
            on_status=self.statusUpdated.emit,
            on_frame=self._publish_frame,
        )
        self.result = result
        self.finished.emit(result)

    def _publish_frame(self, image, fit, pixel_size_m) -> None:
        if self._provider is not None:
            # numpy_to_qimage copies, so the QImage owns its memory and
            # the sequence may free/reuse the frame array.
            self._provider.set_image(numpy_to_qimage(image))
        self.frameReady.emit(fit_to_map(fit, image.shape, pixel_size_m))


class _ReadbackWorker(QObject):
    """Single-shot worker for Confirm's position readback. Do not reuse.

    A handful of fast SDK property reads — but per the no-AutoScript-on-
    the-GUI-thread invariant they still run on a worker. ``finished``
    carries the PositionRecord, or None on any failure.
    """

    finished = Signal(object)  # PositionRecord | None

    def __init__(self, ops: MicroscopeOps,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ops = ops

    def stop(self) -> None:
        """No-op (reads are near-instant); keeps the worker interface
        uniform for the controller's shutdown path."""

    @Slot()
    def run(self) -> None:
        try:
            record: PositionRecord | None = read_position_record(self._ops)
        except Exception:
            logger.exception("Position readback failed")
            record = None
        self.finished.emit(record)


class PositionAlignmentController(QObject):
    """Position Alignment page automation surface."""

    # Slow state (run/viewer state, statusText, inputs) — one notify.
    changed = Signal()
    # frameSeq + ellipseFit co-vary once per frame; a dedicated notify
    # keeps per-frame updates from re-evaluating every state binding.
    frameChanged = Signal()
    # Terminal-event toasts for the StatusBar.
    statusUpdated = Signal(str)
    # Raises the modal tilt-limit dialog (user requirement).
    tiltLimitExceeded = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        frame_provider: Optional[FrameImageProvider] = None,
        ops_provider: Optional[
            Callable[[], Optional[MicroscopeOps]]] = None,
        config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG,
        sequence_factory: Callable[..., AlignmentSequence] = AlignmentSequence,
        start_worker: Callable[[_AlignmentWorker], None] | None = None,
    ) -> None:
        """``ops_provider`` is wired to MicroscopeController.current_ops;
        ``config``, ``sequence_factory`` and ``start_worker`` are test
        seams (``start_worker=lambda w: w.run()`` runs synchronously)."""
        super().__init__(parent)
        self._provider = frame_provider
        self._ops_provider = ops_provider
        self._config = config
        self._sequence_factory = sequence_factory
        self._start_worker = start_worker
        # Run state
        self._run_state = _RUN_IDLE
        self._viewer_state = STATE_IDLE
        self._status_text = ""
        self._status_log_lines: list = []
        self._frame_seq = 0
        self._ellipse_fit: dict = {}
        # Inputs (Binding-pushed from QML; snapshotted at Start)
        self._target_milling_angle = 4.0
        self._aoi_diameter_um = 800.0
        self._use_beam_shift = False
        self._suppress_start_dialog = False
        # Confirm / results
        self._aligned_ready = False   # last run ended ALIGNED, unconsumed
        self._confirming = False
        self._positions_model = ConfirmedPositionsModel(self)
        self._sem_positions_model = SemCandidatePositionsModel(self)
        self._sem_calculator = SEMGeometryCalculator()
        # Worker lifecycle (alignment and readback workers share the
        # single-slot refs — Confirm is only reachable while idle, so at
        # most one SDK-touching worker exists at any moment).
        self._worker = None
        self._thread: Optional[QThread] = None
        self._shutting_down = False

    # --- Outputs (bound by QML) -----------------------------------------

    def is_busy(self) -> bool:
        """True while any worker may touch the microscope (a run or a
        Confirm readback). Plain method — the microscope controller's
        disconnect guard reads it from Python, not QML."""
        return self._run_state != _RUN_IDLE or self._confirming

    @Property(bool, notify=changed)
    def isRunning(self) -> bool:
        return self._run_state != _RUN_IDLE

    @Property(bool, notify=changed)
    def canStop(self) -> bool:
        return self._run_state == _RUN_RUNNING

    @Property(bool, notify=changed)
    def canConfirm(self) -> bool:
        """A successful, not-yet-recorded alignment is under review."""
        return (self._aligned_ready and self._run_state == _RUN_IDLE
                and not self._confirming)

    @Property(QObject, constant=True)
    def positionsModel(self) -> ConfirmedPositionsModel:
        """Confirmed positions (the Spin Mill Positions table)."""
        return self._positions_model

    @Property(QObject, constant=True)
    def semPositionsModel(self) -> SemCandidatePositionsModel:
        """SEM candidates calculated from the confirmed positions."""
        return self._sem_positions_model

    @Property(str, notify=changed)
    def viewerState(self) -> str:
        return self._viewer_state

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status_text

    @Property(str, notify=changed)
    def statusLog(self) -> str:
        """Session scrollback for the Status Log card (newest last)."""
        return "\n".join(self._status_log_lines)

    def _log(self, line: str) -> None:
        self._status_log_lines.append(line)
        if len(self._status_log_lines) > _LOG_MAX_LINES:
            del self._status_log_lines[:-_LOG_MAX_LINES]

    @Property(int, notify=frameChanged)
    def frameSeq(self) -> int:
        return self._frame_seq

    @Property("QVariantMap", notify=frameChanged)
    def ellipseFit(self) -> dict:
        return self._ellipse_fit

    # --- Inputs (Binding-pushed from QML) --------------------------------

    @Property(float, notify=changed)
    def targetMillingAngle(self) -> float:
        return self._target_milling_angle

    @targetMillingAngle.setter
    def targetMillingAngle(self, value: float) -> None:
        if value == self._target_milling_angle:
            return
        self._target_milling_angle = value
        # The SEM candidates' tilt correction (38 - alpha) tracks the
        # target live, like the SEM page (update_or_replace keeps the
        # table's scroll position across the per-tick updates).
        self._recompute_sem(announce=False)
        self.changed.emit()

    @Property(float, notify=changed)
    def aoiDiameter(self) -> float:
        return self._aoi_diameter_um

    @aoiDiameter.setter
    def aoiDiameter(self, value: float) -> None:
        if value == self._aoi_diameter_um:
            return
        self._aoi_diameter_um = value
        self.changed.emit()

    @Property(bool, notify=changed)
    def useBeamShift(self) -> bool:
        return self._use_beam_shift

    @useBeamShift.setter
    def useBeamShift(self, value: bool) -> None:
        if value == self._use_beam_shift:
            return
        self._use_beam_shift = value
        self.changed.emit()

    @Property(bool, notify=changed)
    def suppressStartDialog(self) -> bool:
        """Per-session first-Start dialog suppression (in-memory only)."""
        return self._suppress_start_dialog

    @suppressStartDialog.setter
    def suppressStartDialog(self, value: bool) -> None:
        if value == self._suppress_start_dialog:
            return
        self._suppress_start_dialog = value
        self.changed.emit()

    # --- Actions (invoked from QML) ---------------------------------------

    @Slot()
    def startAlignment(self) -> None:
        """Run one position's alignment on a fresh worker thread."""
        if self._run_state != _RUN_IDLE or self._confirming:
            logger.warning("Start requested while busy; ignoring")
            return
        ops = self._ops_provider() if self._ops_provider else None
        if ops is None:
            message = "Connect to the microscope first"
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        params = AlignmentParams(
            target_milling_angle_deg=self._target_milling_angle,
            use_beam_shift=self._use_beam_shift,
            aoi_diameter_um=self._aoi_diameter_um,
        )
        logger.info("Starting alignment: target %.1f deg, AOI %.0f um, "
                    "beam shift %s", params.target_milling_angle_deg,
                    params.aoi_diameter_um, params.use_beam_shift)
        sequence = self._sequence_factory(ops, params, self._config)
        worker = _AlignmentWorker(sequence, self._provider)
        worker.statusUpdated.connect(self._on_worker_status)
        worker.frameReady.connect(self._on_frame_ready)
        worker.finished.connect(self._on_worker_finished)

        self._aligned_ready = False  # a new run consumes the review state
        self._run_state = _RUN_RUNNING
        self._viewer_state = STATE_RUNNING
        self._status_text = "Starting alignment..."
        if self._status_log_lines:
            self._log(_RUN_SEPARATOR)  # thin rule between runs
        self._log(self._status_text)
        self.changed.emit()
        self._launch_worker(worker)

    def _launch_worker(self, worker) -> None:
        """Canonical single-shot worker-thread wiring (connect-worker
        pattern), including the identity-guarded ref cleanup — runs
        repeat, and an old thread's late finish must not null a new
        run's refs. Shared by the alignment and readback workers."""
        self._worker = worker
        if self._start_worker is not None:  # test seam: run synchronously
            self._start_worker(worker)
            return
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _clear_refs(t: QThread = thread) -> None:
            if self._thread is t:
                self._thread = None
                self._worker = None
        thread.finished.connect(_clear_refs)

        self._thread = thread
        thread.start()

    @Slot()
    def stopAlignment(self) -> None:
        """Cooperative cancel: lands at the next hardware-call boundary."""
        if self._run_state != _RUN_RUNNING or self._worker is None:
            logger.debug("Stop requested but no run is active; ignoring")
            return
        self._worker.stop()
        self._run_state = _RUN_STOPPING
        self._status_text = ("Stopping — waiting for the current "
                             "microscope operation...")
        self._log(self._status_text)
        self.changed.emit()

    @Slot()
    def confirmPosition(self) -> None:
        """Record the reviewed position: read live values off the GUI
        thread and append a results-table row."""
        if not self.canConfirm:
            logger.warning("Confirm requested without a reviewed "
                           "alignment; ignoring")
            return
        ops = self._ops_provider() if self._ops_provider else None
        if ops is None:
            message = "Connect to the microscope first"
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        self._confirming = True
        self._status_text = "Recording the position..."
        self._log(self._status_text)
        self.changed.emit()
        worker = _ReadbackWorker(ops)
        worker.finished.connect(self._on_readback_finished)
        self._launch_worker(worker)

    @Slot()
    def clearPositions(self) -> None:
        """Clear both the confirmed and the SEM positions tables."""
        if self._run_state != _RUN_IDLE or self._confirming:
            logger.warning("Clear requested while busy; ignoring")
            return
        if self._positions_model.count == 0:
            return
        cleared = self._positions_model.count
        self._positions_model.clear()
        self._recompute_sem(announce=False)
        message = f"Cleared {cleared} confirmed position(s)"
        logger.info("%s", message)
        self._status_text = message
        self._log(message)
        self.changed.emit()
        self.statusUpdated.emit(message)

    @Slot()
    def shutdown(self) -> None:
        """App-quit teardown. Chained before the microscope disconnect."""
        self._shutting_down = True
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None and self._thread.isRunning():
            logger.info("Alignment worker still running at shutdown; "
                        "waiting briefly...")
            if not self._thread.wait(5000):
                logger.warning("Alignment worker did not finish in time; "
                               "process exit will terminate it")

    # --- Worker results (GUI thread via queued connections) ---------------

    @Slot(str)
    def _on_worker_status(self, text: str) -> None:
        if self._shutting_down:
            return
        self._status_text = text
        self._log(text)
        self.changed.emit()

    @Slot(object)
    def _on_frame_ready(self, fit_map: dict) -> None:
        if self._shutting_down:
            return
        self._ellipse_fit = fit_map
        self._frame_seq += 1
        self.frameChanged.emit()

    @Slot(object)
    def _on_worker_finished(self, result: AlignmentResult) -> None:
        if self._shutting_down:
            return
        logger.info("Alignment finished: %s (%d frames, %d tilt moves, "
                    "%d center moves)", result.outcome.value,
                    result.frames_grabbed, result.tilt_moves,
                    result.center_moves)
        self._run_state = _RUN_IDLE
        self._viewer_state = _VIEWER_STATE_BY_OUTCOME[result.outcome]
        self._aligned_ready = result.outcome == AlignmentOutcome.ALIGNED
        self._status_text = result.message
        self._log(result.message)
        self.changed.emit()
        self.statusUpdated.emit(result.message)
        if result.outcome == AlignmentOutcome.TILT_LIMIT:
            self.tiltLimitExceeded.emit(result.message)

    @Slot(object)
    def _on_readback_finished(self,
                              record: Optional[PositionRecord]) -> None:
        if self._shutting_down:
            return
        self._confirming = False
        if record is None:
            # Row NOT appended; the review state survives so Confirm
            # can be retried.
            message = "Position readback failed (see console log)"
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        self._positions_model.append_row(record)
        self._recompute_sem(announce=True)
        self._aligned_ready = False
        self._viewer_state = STATE_IDLE  # ready for the next position
        message = f"Position {self._positions_model.count} recorded"
        self._status_text = message
        self._log(message)
        self.changed.emit()
        self.statusUpdated.emit(message)

    # --- SEM candidates from the confirmed rows ---------------------------

    def _recompute_sem(self, announce: bool) -> None:
        """Rebuild the SEM candidates whenever the confirmed rows or the
        target angle change. Mirrors the SEM page's `_recompute` (fitted
        candidates only on OK; the formatter's log block is the audit
        trail), fed from confirmed rows instead of image metadata."""
        records = self._positions_model.records()
        if len(records) < MIN_POSITIONS_FOR_SEM:
            self._sem_positions_model.replace_all([])
            return
        inputs = SEMGeometryInputs(
            stage_rotations_rad=tuple(r.stage_r_rad for r in records),
            stage_tilts_rad=tuple(r.stage_t_rad for r in records),
            scan_rotations_rad=tuple(r.scan_r_rad for r in records),
            target_milling_angle_deg=self._target_milling_angle,
        )
        result = self._sem_calculator.calculate(inputs)
        rows = []
        if result.status == SEMGeometryStatus.OK:
            rows.append(SemPositionCandidate(
                SOURCE_CALCULATED,
                result.target_stage_rotation_rad,
                result.target_stage_tilt_rad))
            rows.append(SemPositionCandidate(
                SOURCE_ALTERNATE,
                result.alternate_stage_rotation_rad,
                result.alternate_stage_tilt_rad))
        self._sem_positions_model.update_or_replace(rows)
        logger.log(logging.INFO if announce else logging.DEBUG,
                   "%s", formatter.log_block(result))
