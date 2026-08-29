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

The user inputs (target milling angle, AOI diameter, number of spin
mill positions, use-beam-shift) are pushed one-way from QML via Binding
elements and snapshotted into an immutable ``AlignmentParams`` at Start
— mid-run edits apply to the next run. Confirm, Update, and Clear, plus
the per-row Go To / Re-confirm / Confirm-here actions, maintain the
fixed position slots and the SEM candidates derived from the active
ones (slots beyond the current count are kept but excluded).
"""
from __future__ import annotations

import dataclasses
import logging
import math
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
    expected_geometry_for,
)
from asv_spin_mill_angle_calc.ellipse_detector import (
    EllipseFit,
    FiducialEllipseDetector,
)
from asv_spin_mill_angle_calc.frame_image_provider import (
    FrameImageProvider,
    numpy_to_qimage,
)
from asv_spin_mill_angle_calc.microscope_ops import (
    MicroscopeOps,
    PositionRecord,
    read_position_record,
    restore_position,
)
from asv_spin_mill_angle_calc.position_alignment_models import (
    ConfirmedPositionsModel,
)
from asv_spin_mill_angle_calc.sem_geometry_calculator import (
    MIN_POSITIONS,
    SEMGeometryCalculator,
    SEMGeometryInputs,
    SEMGeometryStatus,
    SemPositionCandidate,
    SOURCE_ALTERNATE,
    SOURCE_CALCULATED,
    measured_perpendicular_candidates_from_inputs,
)
from asv_spin_mill_angle_calc import sem_geometry_result_formatter as formatter
from asv_spin_mill_angle_calc.sem_positions_models import (
    SemCandidatePositionsModel,
)
from asv_spin_mill_angle_calc.spin_mill_geometry import (
    FIB_ANGLE_FROM_STAGE_PLANE_DEG,
    fold_scan_rotation_rad,
)

logger = logging.getLogger(__name__)

# Empty-state text for the SEM candidates table below the calculator's
# minimum position count (phrased as the table placeholder, matching
# SemAngleController._compose_status).
#
# The second sentence matters: the card has two independent row
# sources and only one of them needs MIN_POSITIONS. A measured
# (already-perpendicular) position is emitted from a single row by
# measured_perpendicular_candidates_from_inputs, so a bare "3 or more
# positions required." would describe only half the table.
_SEM_INSUFFICIENT_TEXT = (
    f"{MIN_POSITIONS} or more positions required to calculate. A position "
    "already perpendicular in rotation is listed as Measured.")

# Status Log retention (session-long scrollback, oldest lines dropped).
_LOG_MAX_LINES = 500
# Thin rule between runs (U+2500 box drawing reads as a line in text).
_RUN_SEPARATOR = "─" * 40

# Viewer/card visual states (the QML maps these onto border colors).
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_SUCCESS = "success"
# Manual Update re-capture: the review state is armed, but by hand
# rather than by a verified run — the QML paints it accent blue, never
# the green reserved for an alignment the routine itself verified.
STATE_UPDATED = "updated"
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


def publish_frame(provider: Optional[FrameImageProvider], image,
                  fit: Optional[EllipseFit], pixel_size_m: float) -> dict:
    """Push one frame into the image provider and return its QML fit map.

    Shared by the alignment and update workers; called from worker
    threads (the provider is lock-guarded, and numpy_to_qimage copies so
    the QImage owns its memory and the caller may free/reuse the array).
    """
    if provider is not None:
        provider.set_image(numpy_to_qimage(image))
    return fit_to_map(fit, image.shape, pixel_size_m)


@dataclasses.dataclass(frozen=True)
class UpdateCapture:
    """One Update: the live readback plus the advisory ellipse measurement.

    ``record`` is None when the capture failed (the error is already
    logged); ``fit`` is None when no plausible ellipse was measured,
    which is informational only — Update never actuates on it.
    """
    record: Optional[PositionRecord] = None
    fit: Optional[EllipseFit] = None
    pixel_size_m: float = 0.0


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
        self.frameReady.emit(
            publish_frame(self._provider, image, fit, pixel_size_m))


class _ReadbackWorker(QObject):
    """Single-shot worker for a Confirm/Re-confirm readback. Do not reuse.

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


class _GoToWorker(QObject):
    """Single-shot worker for a row's Go To. Do not reuse.

    Drives the stage back to a confirmed position and restores the beam
    shift and scan rotation that were recorded with it. Unlike Update
    this worker actuates, so the controller makes the tilt-floor check
    before the worker is launched — a refusal must never reach the
    hardware.

    ``finished`` carries the position number on success, or None on
    failure (already logged). No frame is grabbed: the operator presses
    Update when they want to see where they landed, which keeps Go To
    fast and keeps the review-before-commit path single.

    What actuates is the record, snapshotted by the controller before
    this worker was built — never the number. Slots never shift, but
    snapshotting keeps the worker independent of any model change in
    flight: the number it carries can at worst misreport where we went;
    it can never misroute the stage.
    """

    finished = Signal(object)  # int position number | None

    def __init__(self, ops: MicroscopeOps, record: PositionRecord,
                 position_number: int,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ops = ops
        self._record = record
        self._position_number = position_number

    def stop(self) -> None:
        """No-op: a stage move cannot be interrupted mid-flight through
        this seam. Keeps the worker interface uniform for shutdown."""

    @Slot()
    def run(self) -> None:
        try:
            self._ops.stage.use_specimen_coordinates()
            restore_position(self._ops, self._record)
        except Exception:
            logger.exception("Go To failed for position %d",
                             self._position_number)
            self.finished.emit(None)
            return
        self.finished.emit(self._position_number)


class _UpdateWorker(QObject):
    """Single-shot worker for the Update button. Do not reuse.

    One observation pass over the instrument, all of it off the GUI
    thread: select the FIB view, read the live position, grab one frame,
    and best-effort measure the AOI ellipse for the viewer overlay.

    Update observes but never actuates: no stage move, no HFW change, no
    scan rotation write. An AOI that does not sit in the detector's size
    band therefore yields no ellipse (an advisory) rather than an HFW
    change made behind the operator's back.
    """

    frameReady = Signal(object)   # ellipseFit map (may be {})
    finished = Signal(object)     # UpdateCapture

    def __init__(self, ops: MicroscopeOps,
                 provider: Optional[FrameImageProvider],
                 config: AlignmentConfig,
                 aoi_diameter_um: float,
                 detect: Callable[..., tuple],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ops = ops
        self._provider = provider
        self._cfg = config
        self._aoi_diameter_um = aoi_diameter_um
        self._detect = detect

    def stop(self) -> None:
        """No-op (a single grab); keeps the worker interface uniform for
        the controller's shutdown path."""

    @Slot()
    def run(self) -> None:
        try:
            self._ops.imaging.prepare_fib_view(self._cfg.fib_view)
            record = read_position_record(self._ops)
            frame = self._ops.imaging.grab_frame()
            fit = self._measure(frame, record)
            # Exactly one publish per Update, fit or not: an empty map
            # clears a stale overlay in the same tick the new image
            # lands, so the viewer can never show the previous run's
            # ellipse over a fresh frame.
            self.frameReady.emit(publish_frame(
                self._provider, frame.data, fit, frame.pixel_size_m))
            self.finished.emit(UpdateCapture(
                record=record, fit=fit,
                pixel_size_m=frame.pixel_size_m))
        except Exception:
            logger.exception("Update capture failed")
            self.finished.emit(UpdateCapture())

    def _measure(self, frame, record: PositionRecord) -> Optional[EllipseFit]:
        """Best-effort ellipse measurement for the overlay.

        Priors come from the same helper the alignment sequence uses, at
        the wide plausibility window: an Update has no planarity anchor.
        """
        model_deg = (math.degrees(record.stage_t_rad)
                     + FIB_ANGLE_FROM_STAGE_PLANE_DEG)
        window_deg = self._cfg.plausibility_window_deg
        low_deg, high_deg = (model_deg - window_deg, model_deg + window_deg)
        expected = expected_geometry_for(
            self._cfg,
            aoi_diameter_um=self._aoi_diameter_um,
            pixel_size_m=frame.pixel_size_m,
            angle_window_deg=(low_deg, high_deg),
            scan_rotation_deg=math.degrees(
                fold_scan_rotation_rad(record.scan_r_rad)),
        )
        fits = self._detect(frame.data, expected)
        if not fits:
            return None
        # Display-only plausibility gate: the fit never actuates, but
        # reporting a clutter fit's angle would mislead the operator.
        best = fits[0]
        if not low_deg <= best.milling_angle_deg <= high_deg:
            logger.info(
                "Update: best fit %.2f deg is outside the plausible "
                "[%.2f, %.2f] deg window; reporting no ellipse",
                best.milling_angle_deg, low_deg, high_deg)
            return None
        return best


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
        debug_dir_provider: Callable[[], str] | None = None,
        tuning_provider: Callable[[], dict] | None = None,
        detect: Callable[..., tuple] | None = None,
    ) -> None:
        """``ops_provider`` is wired to MicroscopeController.current_ops;
        ``config``, ``sequence_factory`` and ``start_worker`` are test
        seams (``start_worker=lambda w: w.run()`` runs synchronously).

        ``debug_dir_provider`` (AppController wires it to the Settings
        page's Save Debug Images checkbox) is read once at each Start and,
        when injected, is authoritative for the run's ``debug_frames_dir``
        — so a mid-session toggle applies to the next run, never a running
        one. The ASV_DEBUG_FRAMES_DIR environment variable still wins
        inside the sequence.

        ``tuning_provider`` (AppController wires it to the Settings
        page's alignment parameters) returns a dict of AlignmentConfig
        field overrides, read once at each Start alongside
        ``debug_dir_provider``. An invalid combination is logged and
        ignored rather than raised — see :meth:`_run_config`.

        ``detect`` is the Update button's ellipse-measurement seam
        (same shape as AlignmentSequence's); it resolves lazily to the
        configured detector so constructing a controller never builds
        one."""
        super().__init__(parent)
        self._provider = frame_provider
        self._ops_provider = ops_provider
        self._config = config
        self._sequence_factory = sequence_factory
        self._start_worker = start_worker
        self._debug_dir_provider = debug_dir_provider
        self._tuning_provider = tuning_provider
        self._detect = detect
        # Run state
        self._run_state = _RUN_IDLE
        self._viewer_state = STATE_IDLE
        self._status_text = ""
        self._status_log_lines: list = []
        self._frame_seq = 0
        self._ellipse_fit: dict = {}
        self._last_run_warnings: list = []
        # Inputs (Binding-pushed from QML; snapshotted at Start)
        self._target_milling_angle = 4.0
        self._aoi_diameter_um = 800.0
        self._use_beam_shift = False
        self._suppress_start_dialog = False
        # Confirm / results
        self._aligned_ready = False   # a position is under review
        # The measured milling angle of whatever armed the review: the
        # run's median verification fit, or the Update capture's fit.
        # None means no ellipse was measured, and the row shows "NA" —
        # never substitute the tilt-derived model angle, which is not a
        # measurement. Consumed and cleared by Confirm and Re-confirm.
        self._armed_angle_deg: Optional[float] = None
        self._confirming = False
        self._updating = False
        self._going_to = False
        # Set by reconfirmPosition for the duration of one readback:
        # which slot the result lands on. None means Confirm — the
        # lowest pending active slot, resolved at landing time in
        # _on_readback_finished (not at click time), so lowering the
        # slot count while a readback flies can never land a capture on
        # a slot that no longer qualifies. Slots never renumber, so an
        # explicit target stays the same physical position for the
        # whole flight; a target trimmed mid-flight fails loudly at
        # fill_slot and keeps the arm.
        self._target_slot: Optional[int] = None
        self._positions_model = ConfirmedPositionsModel(self)
        # averageMillingAngle / hasAverageMillingAngle are derived from the
        # model, so they must re-evaluate whenever the rows change — not
        # merely whenever a controller slot happens to emit `changed`.
        # Without this the header average silently keeps a stale value if
        # the model is ever mutated by anything but a slot.
        self._positions_model.countChanged.connect(self.changed)
        self._positions_model.dataChanged.connect(
            lambda *_args: self.changed.emit())
        self._sem_positions_model = SemCandidatePositionsModel(self)
        self._sem_calculator = SEMGeometryCalculator()
        self._sem_status_text = _SEM_INSUFFICIENT_TEXT
        # Worker lifecycle (all the single-shot workers share the
        # single-slot refs — every action is gated on _idle, so at
        # most one SDK-touching worker exists at any moment).
        self._worker = None
        self._thread: Optional[QThread] = None
        self._shutting_down = False

    # --- Outputs (bound by QML) -----------------------------------------

    def _idle(self) -> bool:
        """True when no worker may be touching the microscope.

        The single source for every busy guard — add new worker states
        here, not at each call site. It serialises hardware access (at
        most one SDK-touching worker exists at any moment) and blocks
        Clear for every worker's whole flight. Slot numbers are stable
        by construction, so the one residual mid-flight hazard — the
        slot count shrinking under an in-flight readback — is handled
        at landing (see _on_readback_finished) rather than here. The
        QML's `actionsEnabled` tracks only `isRunning`, so this check —
        not the greyed-out menu item — is the real guard.
        """
        return (self._run_state == _RUN_IDLE and not self._confirming
                and not self._updating and not self._going_to)

    def is_busy(self) -> bool:
        """True while any worker may touch the microscope (a run, a
        Confirm or Re-confirm readback, a Go To move, or an Update
        capture). Plain method — the microscope controller's disconnect
        guard reads it from Python, not QML."""
        return not self._idle()

    @Property(bool, notify=changed)
    def isRunning(self) -> bool:
        return self._run_state != _RUN_IDLE

    @Property(bool, notify=changed)
    def canStop(self) -> bool:
        return self._run_state == _RUN_RUNNING

    @Property(bool, notify=changed)
    def canConfirm(self) -> bool:
        """A position is under review (a verified run, or an Update
        re-capture) and a pending active slot exists to receive it.

        With every active slot recorded this goes false while
        ``canReconfirm`` stays true — replacing a recorded slot is then
        the only way to consume the review.
        """
        return (self._aligned_ready and self._idle()
                and self._positions_model.first_pending_active_slot()
                is not None)

    @Property(bool, notify=changed)
    def canUpdate(self) -> bool:
        """Re-capture the live instrument state into the review view.

        Deliberately requires no reviewed alignment: the whole point is
        to record a position the operator adjusted by hand, so Update is
        available from a cold idle as well as after a run.
        """
        return self._idle()

    @Property(bool, notify=changed)
    def canReconfirm(self) -> bool:
        """An armed review may be recorded onto a specific row.

        Consumes the same armed review as Confirm — it just lands on an
        explicit slot (Re-confirm on a recorded one, Confirm-here on a
        pending one) instead of the lowest pending slot. Gating it on
        the arm preserves the page's review-before-commit rule: a slot
        is only ever written with a capture the operator has already
        seen in the viewer. Deliberately not gated on a pending slot
        existing — with a full table this stays true while
        ``canConfirm`` goes false.
        """
        return self._aligned_ready and self._idle()

    @Property(bool, notify=changed)
    def canClear(self) -> bool:
        """At least one slot holds a recorded position.

        The table's row count is no longer the signal (slot rows always
        exist), so the Clear button gates on recorded data instead.
        """
        return self._positions_model.filled_count() > 0

    @Property(bool, notify=changed)
    def hasAverageMillingAngle(self) -> bool:
        """True when at least one active slot carries a measured angle."""
        return bool(self._positions_model.active_measured_angles())

    @Property(float, notify=changed)
    def averageMillingAngle(self) -> float:
        """Mean measured milling angle across the active recorded slots.

        A mean, deliberately unlike AlignmentSequence._verify's median:
        that outvotes noisy repeat frames of one site, while these are
        independent measurements of different sites. Unmeasured ("NA")
        rows and slots beyond the current position count are excluded,
        not counted as zero. Returns 0.0 when nothing is measured; QML
        gates on ``hasAverageMillingAngle`` instead.
        """
        angles = self._positions_model.active_measured_angles()
        if not angles:
            return 0.0
        return sum(angles) / len(angles)

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
    def semStatusText(self) -> str:
        """Outcome of the last SEM candidate calculation — the Calculated
        SEM Positions card's empty-state text. The minimum-rows hint
        before three positions exist, the calculator's own status line
        afterwards, so a non-OK verdict shows on the card rather than
        only in the console."""
        return self._sem_status_text

    @Property(str, notify=changed)
    def statusLog(self) -> str:
        """Session scrollback for the Status Log card (newest last)."""
        return "\n".join(self._status_log_lines)

    @Property("QVariantList", notify=changed)
    def lastRunWarnings(self) -> list:
        """Advisories from the last finished run (width mismatch,
        mid-run re-anchor, ...) — the viewer's advisory chip."""
        return self._last_run_warnings

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

    @Property(int, notify=changed)
    def numberOfPositions(self) -> int:
        """The Number of Spin Mill Positions (N) set in ASV — the active
        slot count. Session-only, like aoiDiameter; the model owns the
        value because every slot policy derives from it."""
        return self._positions_model.slot_count()

    @numberOfPositions.setter
    def numberOfPositions(self, value: int) -> None:
        if value == self._positions_model.slot_count():
            return
        self._positions_model.set_slot_count(value)
        # The active set changed: SEM candidates and the header average
        # must re-derive (the targetMillingAngle setter's live-recompute
        # idiom).
        self._recompute_sem(announce=False)
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
        if not self._idle():
            logger.warning("Start requested while busy; ignoring")
            return
        ops = self._require_ops()
        if ops is None:
            return
        params = AlignmentParams(
            target_milling_angle_deg=self._target_milling_angle,
            use_beam_shift=self._use_beam_shift,
            aoi_diameter_um=self._aoi_diameter_um,
        )
        logger.info("Starting alignment: target %.1f deg, AOI %.0f um, "
                    "beam shift %s", params.target_milling_angle_deg,
                    params.aoi_diameter_um, params.use_beam_shift)
        config = self._run_config()
        sequence = self._sequence_factory(ops, params, config)
        worker = _AlignmentWorker(sequence, self._provider)
        worker.statusUpdated.connect(self._on_worker_status)
        worker.frameReady.connect(self._on_frame_ready)
        worker.finished.connect(self._on_worker_finished)

        self._aligned_ready = False  # a new run consumes the review state
        self._last_run_warnings = []
        self._run_state = _RUN_RUNNING
        self._viewer_state = STATE_RUNNING
        self._status_text = "Starting alignment..."
        if self._status_log_lines:
            self._log(_RUN_SEPARATOR)  # thin rule between runs
        self._log(self._status_text)
        self.changed.emit()
        self._launch_worker(worker)

    def _run_config(self) -> AlignmentConfig:
        """The config for one run: defaults plus the injected providers.

        Both providers are read once here, at each Start, so a
        mid-session Settings change applies to the next run and can
        never mutate a run already in flight.

        The tuning overrides are validated by ``__post_init__``, which
        ``replace()`` re-runs and which raises on any of its cross-field
        invariants. A rejected combination must not brick Start, so it
        is logged and the run falls back to the un-tuned config: the
        alignment still happens, at the defaults.
        """
        config = self._config
        if self._debug_dir_provider is not None:
            # Frozen dataclass: replace() re-runs __post_init__ validation,
            # which is inert here (debug_frames_dir is not validated).
            config = dataclasses.replace(
                config, debug_frames_dir=self._debug_dir_provider())
        if self._tuning_provider is None:
            return config
        overrides = self._tuning_provider() or {}
        if not overrides:
            return config
        try:
            tuned = dataclasses.replace(config, **overrides)
        except (ValueError, TypeError):
            logger.exception(
                "Alignment tuning from Settings is invalid (%r); running "
                "with the built-in defaults instead", overrides)
            self._log("Settings tuning rejected — running with defaults "
                      "(see console log)")
            return config
        logger.info("Alignment tuning from Settings: %s",
                    ", ".join(f"{k}={v}" for k, v in sorted(
                        overrides.items())))
        return tuned

    def _launch_worker(self, worker) -> None:
        """Canonical single-shot worker-thread wiring (connect-worker
        pattern), including the identity-guarded ref cleanup — runs
        repeat, and an old thread's late finish must not null a new
        run's refs. Shared by every single-shot worker."""
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
        thread and land them in the lowest pending active slot.

        The slot is resolved when the readback lands, not here — see
        ``_target_slot``.
        """
        if not self.canConfirm:
            logger.warning("Confirm requested without a reviewed "
                           "position; ignoring")
            return
        ops = self._require_ops()
        if ops is None:
            return
        self._confirming = True
        self._target_slot = None
        self._status_text = "Recording the position..."
        self._log(self._status_text)
        self.changed.emit()
        worker = _ReadbackWorker(ops)
        worker.finished.connect(self._on_readback_finished)
        self._launch_worker(worker)

    @Slot()
    def updatePosition(self) -> None:
        """Re-capture the live instrument state into the review view.

        Grabs one FIB image and re-reads the stage/beam/scan values, then
        arms Confirm — the operator's path after adjusting the microscope
        by hand, with no alignment run and no stage motion of our own.
        """
        if not self.canUpdate:
            logger.warning("Update requested while busy; ignoring")
            return
        ops = self._require_ops()
        if ops is None:
            return
        self._updating = True
        self._status_text = "Re-capturing the current position..."
        self._log(self._status_text)
        self.changed.emit()
        worker = _UpdateWorker(ops, self._provider, self._config,
                               self._aoi_diameter_um, self._detector())
        worker.frameReady.connect(self._on_frame_ready)
        worker.finished.connect(self._on_update_finished)
        self._launch_worker(worker)

    @Slot(int)
    def goToPosition(self, position_number: int) -> None:
        """Drive back to a confirmed position (stage + beam + scan rot).

        Only a recorded, active slot may be driven to: a pending slot
        has no record, and a slot beyond the current position count is
        out of the workflow until the count is raised. The QML menu
        disables both cases; these checks are the real guard.

        Actuates, so it is refused while any other worker may touch the
        microscope and the tilt floor is checked before the worker
        exists — the same user requirement the alignment sequence
        enforces pre-flight. A stored position was within limits when it
        was confirmed, but the floor may have been lowered since.
        """
        if not self._idle():
            logger.warning("Go To requested while busy; ignoring")
            return
        if position_number > self._positions_model.slot_count():
            logger.warning(
                "Go To requested for inactive position %d; ignoring",
                position_number)
            return
        record = self._positions_model.record_for_position(position_number)
        if record is None:
            logger.warning(
                "Go To requested for a pending or out-of-range position "
                "%d; ignoring", position_number)
            return
        tilt_deg = math.degrees(record.stage_t_rad)
        if tilt_deg <= self._config.tilt_floor_deg:
            message = (f"Position {position_number} refused: stored tilt "
                       f"{tilt_deg:.2f}° is at or below the "
                       f"{self._config.tilt_floor_deg:.2f}° floor")
            logger.warning("%s", message)
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        ops = self._require_ops()
        if ops is None:
            return
        self._going_to = True
        self._status_text = f"Driving to position {position_number}..."
        self._log(self._status_text)
        self.changed.emit()
        worker = _GoToWorker(ops, record, position_number)
        worker.finished.connect(self._on_goto_finished)
        self._launch_worker(worker)

    @Slot(int)
    def reconfirmPosition(self, position_number: int) -> None:
        """Record the reviewed position into a specific slot.

        The slot-specific twin of Confirm: same armed review, same
        readback worker, but the result lands on the named slot — the
        QML menu's Re-confirm on a recorded row, or Confirm-here on a
        pending one. The slot keeps its number by construction, which
        is what lets a bad capture be fixed (or ASV's position 4 be
        recorded before 1) without sliding the list against ASV's own
        numbering.
        """
        if not self.canReconfirm:
            logger.warning("Re-confirm requested without a reviewed "
                           "position; ignoring")
            return
        if position_number > self._positions_model.slot_count():
            logger.warning("Re-confirm requested for inactive position "
                           "%d; ignoring", position_number)
            return
        if self._positions_model.index_of_position(position_number) < 0:
            logger.warning("Re-confirm requested for out-of-range position "
                           "%d; ignoring", position_number)
            return
        ops = self._require_ops()
        if ops is None:
            return
        self._confirming = True
        self._target_slot = position_number
        # Neutral wording: this path serves both Re-confirm (recorded
        # slot) and Confirm-here (pending slot).
        self._status_text = f"Recording position {position_number}..."
        self._log(self._status_text)
        self.changed.emit()
        worker = _ReadbackWorker(ops)
        worker.finished.connect(self._on_readback_finished)
        self._launch_worker(worker)

    def _detector(self) -> Callable[..., tuple]:
        """The Update button's detection callable (test seam), resolved
        lazily so constructing a controller never builds a detector."""
        if self._detect is None:
            self._detect = FiducialEllipseDetector(
                self._config.detector).detect_all
        return self._detect

    def _require_ops(self) -> Optional[MicroscopeOps]:
        """The live ops bundle, or None with the not-connected message
        already surfaced (status line, log, and toast)."""
        ops = self._ops_provider() if self._ops_provider else None
        if ops is None:
            message = "Connect to the microscope first"
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
        return ops

    @Slot()
    def clearPositions(self) -> None:
        """Reset every slot to pending and clear the SEM table.

        The Number of Spin Mill Positions is kept — Clear discards
        recorded data, not the declared workflow shape.
        """
        if not self._idle():
            logger.warning("Clear requested while busy; ignoring")
            return
        if self._positions_model.filled_count() == 0:
            return
        cleared = self._positions_model.filled_count()
        self._positions_model.clear()
        self._recompute_sem(announce=False)
        message = (f"Cleared {cleared} confirmed "
                   f"position{'s' if cleared != 1 else ''}")
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
        # On ALIGNED, final_fit is the median verification fit — the
        # run's authoritative angle, not the last frame published to the
        # viewer. Arm it so Confirm/Re-confirm can record it.
        self._armed_angle_deg = (
            result.final_fit.milling_angle_deg
            if self._aligned_ready and result.final_fit is not None
            else None)
        self._status_text = result.message
        self._last_run_warnings = list(result.warnings)
        self._log(result.message)
        # The Status Log is the advisories' only surface — there is no
        # viewer chip — so log each one (same indent idiom as _log_sem).
        for warning in result.warnings:
            self._log(f"  - {warning}")
        self.changed.emit()
        self.statusUpdated.emit(result.message)
        if result.outcome == AlignmentOutcome.TILT_LIMIT:
            self.tiltLimitExceeded.emit(result.message)

    @Slot(object)
    def _on_goto_finished(self, position_number: Optional[int]) -> None:
        if self._shutting_down:
            return
        self._going_to = False
        if position_number is None:
            message = "Go To failed (see console log)"
            self._viewer_state = STATE_EXCEPTION
        else:
            message = (f"At position {position_number} — press Update to "
                       "re-capture the view")
        self._status_text = message
        self._log(message)
        self.changed.emit()
        self.statusUpdated.emit(message)

    @Slot(object)
    def _on_readback_finished(self,
                              record: Optional[PositionRecord]) -> None:
        if self._shutting_down:
            return
        self._confirming = False
        target = self._target_slot
        self._target_slot = None
        if record is None:
            # No slot is written; the review state survives so Confirm or
            # Re-confirm can be retried.
            message = "Position readback failed (see console log)"
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        angle_deg = self._armed_angle_deg
        if target is None:
            # Confirm: resolve the lowest pending active slot now, at
            # landing — not at click time — so an N lowered mid-flight
            # can never land the capture on a slot that no longer
            # qualifies.
            target = self._positions_model.first_pending_active_slot()
            if target is None:
                # N shrank under the readback and no pending active slot
                # remains. Nothing was recorded, so the arm survives; the
                # operator can Re-confirm onto a row instead.
                message = ("No pending position slot — use Re-confirm on "
                           "a row")
                self._status_text = message
                self._log(message)
                self.changed.emit()
                self.statusUpdated.emit(message)
                return
        was_filled = self._positions_model.is_filled(target)
        if not self._positions_model.fill_slot(target, record, angle_deg):
            # The explicit target slot was trimmed while the readback
            # flew (N lowered past a pending slot beyond the new count).
            # Failing loudly here — rather than writing a row nobody can
            # see — keeps the arm so the operator can record it again.
            message = (f"Position {target} no longer exists; "
                       "nothing recorded")
            self._status_text = message
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        message = (f"Position {target} re-recorded" if was_filled
                   else f"Position {target} recorded")
        if angle_deg is None:
            message += " (no measured angle)"
        # The review is consumed either way: one armed capture writes to
        # exactly one slot.
        self._aligned_ready = False
        self._armed_angle_deg = None
        self._viewer_state = STATE_IDLE  # ready for the next position
        self._status_text = message
        self._log(message)
        # After the row announcement, so the log reads
        # "Position 3 recorded" then the SEM verdict it produced.
        self._recompute_sem(announce=True)
        self.changed.emit()
        self.statusUpdated.emit(message)

    @Slot(object)
    def _on_update_finished(self, capture: UpdateCapture) -> None:
        if self._shutting_down:
            return
        self._updating = False
        if capture.record is None:
            # Rows and the review state are untouched: Update is
            # retryable, and a failed capture must not disarm a Confirm
            # the operator had already earned.
            message = "Update failed (see console log)"
            self._status_text = message
            self._viewer_state = STATE_EXCEPTION
            self._log(message)
            self.changed.emit()
            self.statusUpdated.emit(message)
            return
        # The re-capture is now the reviewed position: arm Confirm, but
        # in the "updated" state — green is reserved for an alignment the
        # routine verified, this one the operator set up by hand.
        self._aligned_ready = True
        self._armed_angle_deg = (None if capture.fit is None
                                 else capture.fit.milling_angle_deg)
        self._viewer_state = STATE_UPDATED
        message = ("Position re-captured — press Confirm to record it, or "
                   "Re-confirm on a row to replace it")
        if capture.fit is None:
            message += " (no ellipse detected)"
        self._status_text = message
        self._log(message)
        if capture.fit is not None:
            self._log(self._describe_fit(capture.fit, capture.pixel_size_m))
        self.changed.emit()
        self.statusUpdated.emit(message)

    @staticmethod
    def _describe_fit(fit: EllipseFit, pixel_size_m: float) -> str:
        """One-line measurement summary for the Status Log."""
        width_um = 2 * fit.semi_major_px * pixel_size_m * 1e6
        height_um = 2 * fit.semi_minor_px * pixel_size_m * 1e6
        return (f"Update: ellipse {width_um:.0f} x {height_um:.1f} µm, "
                f"milling angle {fit.milling_angle_deg:.2f}°, "
                f"tilt {fit.tilt_deg:+.2f}°")

    # --- SEM candidates from the active recorded slots --------------------

    def _recompute_sem(self, announce: bool) -> None:
        """Rebuild the SEM candidates whenever the recorded slots, the
        position count, or the target angle change. Mirrors the SEM
        page's `_recompute` (fitted candidates only on OK, measured
        candidates regardless of fit status; the formatter's log block
        is the audit trail), fed from the active recorded slots instead
        of image metadata.

        The calculation runs at any count — the calculator reports
        INSUFFICIENT_DATA below its minimum — so the card always shows
        why it is empty, and a measured (already-perpendicular) position
        can surface before three slots are recorded.
        """
        numbered = self._positions_model.active_records()
        records = [record for _number, record in numbered]
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
        # Numbers and records come from the one active_records() walk,
        # so under sparse fills the provenance stays truthful: slot 4
        # recorded while 2-3 are pending is labeled "Position 4", and
        # the details list stays parallel with the inputs by
        # construction. Inactive overhang slots are excluded from both.
        rows.extend(measured_perpendicular_candidates_from_inputs(
            inputs,
            details=[f"Position {number}" for number, _record in numbered]))
        self._sem_positions_model.update_or_replace(rows)
        self._sem_status_text = self._compose_sem_status(result)
        if announce:
            self._log_sem(result)
        logger.log(logging.INFO if announce else logging.DEBUG,
                   "%s", formatter.log_block(result))

    @staticmethod
    def _compose_sem_status(result) -> str:
        """The card's empty-state / verdict line."""
        if result.status == SEMGeometryStatus.INSUFFICIENT_DATA:
            return _SEM_INSUFFICIENT_TEXT
        return formatter.status_line(result)

    def _log_sem(self, result) -> None:
        """Put the SEM verdict and its advisories in the Status Log.

        Silent on INSUFFICIENT_DATA: the card already says so, and a line
        per Confirm would bury the run's own status. Warnings (rotation
        span, cross-fit consistency) are logged so they reach the
        operator, not only the console.
        """
        if result.status == SEMGeometryStatus.INSUFFICIENT_DATA:
            return
        self._log(f"SEM positions: {formatter.status_line(result)}")
        for warning in result.warnings:
            self._log(f"  - {warning}")
