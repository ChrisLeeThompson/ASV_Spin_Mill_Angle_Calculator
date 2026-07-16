"""QObject controller for the SEM Angle Calc page.

Thin Qt orchestration over the Qt-free modules: image_metadata (parse),
sem_geometry_calculator (math), sem_geometry_result_formatter (strings).
Caches the parsed records so changing the target milling angle recomputes
without re-reading files (2.3 never recomputed on target change).

Idioms mirror the sibling FibAngleController: functional ``Signal`` class
attribute, ``@Property`` getters/setters with no-op-on-equal setters,
``camelCase`` for the QML surface, ``_snake_case`` backing fields.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from PySide6.QtCore import (
    Property,
    QObject,
    QStandardPaths,
    QUrl,
    Signal,
    Slot,
)

from asv_spin_mill_angle_calc import image_metadata
from asv_spin_mill_angle_calc import sem_geometry_result_formatter as formatter
from asv_spin_mill_angle_calc.image_metadata import SpinMillImageMetadata
from asv_spin_mill_angle_calc.sem_geometry_calculator import (
    SEMGeometryCalculator,
    SEMGeometryInputs,
    SEMGeometryStatus,
    SemPositionCandidate,
    SOURCE_ALTERNATE,
    SOURCE_CALCULATED,
    measured_perpendicular_candidates,
)
from asv_spin_mill_angle_calc.sem_positions_models import (
    SemCandidatePositionsModel,
    SpinMillPositionsModel,
)

logger = logging.getLogger(__name__)

# Mirrors the SEM page's spin-box default so results are correct before
# the user touches anything.
_DEFAULT_TARGET_MILLING_ANGLE_DEG = 4.0


def _default_directory() -> str:
    pictures = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.PicturesLocation)
    return pictures or str(Path.home())


class SemAngleController(QObject):
    """SEM perpendicular-position calculation for the SEM Angle Calc page."""

    # Single notify signal: the inputs feed the status text, so any
    # change refreshes all output bindings (models notify themselves).
    changed = Signal()

    # Transient status messages for the StatusBar (Hydra pattern:
    # Connections in main.qml routes these to statusBar.showMessage).
    statusUpdated = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._target_milling_angle = _DEFAULT_TARGET_MILLING_ANGLE_DEG
        self._status_text = ""
        # Results card scrollback: the per-load audit that also goes to the
        # console. A snapshot, not a session log — each load replaces it.
        self._results_text = ""
        self._last_load_summary = ""
        self._last_directory = _default_directory()
        self._records: List[SpinMillImageMetadata] = []
        self._parse_errors: List[str] = []
        self._calculator = SEMGeometryCalculator()
        self._positions_model = SpinMillPositionsModel(self)
        self._sem_positions_model = SemCandidatePositionsModel(self)

    # --- Models (constant QObject properties) ------------------------------
    @Property(QObject, constant=True)
    def positionsModel(self) -> SpinMillPositionsModel:
        return self._positions_model

    @Property(QObject, constant=True)
    def semPositionsModel(self) -> SemCandidatePositionsModel:
        return self._sem_positions_model

    # --- Inputs (written from QML) ------------------------------------------
    @Property(float, notify=changed)
    def targetMillingAngle(self) -> float:
        return self._target_milling_angle

    @targetMillingAngle.setter
    def targetMillingAngle(self, value: float) -> None:
        value = float(value)
        if value == self._target_milling_angle:
            return
        self._target_milling_angle = value
        if self._records or self._parse_errors:
            # Recompute from the cached parse — no file I/O (2.3 never
            # refreshed its results when the target angle changed).
            # announce=False: spin-box sweeps would otherwise fire a log
            # block and a status toast per 0.1-degree tick.
            self._recompute(announce=False)
        else:
            self.changed.emit()

    # --- Outputs (bound by QML) ----------------------------------------------
    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status_text

    @Property(str, notify=changed)
    def resultsText(self) -> str:
        """Full per-load audit for the Results card (statusText's long form)."""
        return self._results_text

    @Property(QUrl, notify=changed)
    def lastDirectoryUrl(self) -> QUrl:
        return QUrl.fromLocalFile(self._last_directory)

    # --- Actions ----------------------------------------------------------------
    @Slot("QVariantList")
    def loadImages(self, urls: list) -> None:
        """FileDialog accept path: QUrl list -> parse batch -> recompute."""
        paths: List[str] = []
        for url in urls:
            local = url.toLocalFile() if isinstance(url, QUrl) else str(url)
            if local:
                paths.append(local)
        if not paths:
            logger.debug("loadImages called with no files; ignoring.")
            return
        self._records, self._parse_errors = \
            image_metadata.parse_spin_mill_images(paths)
        self._last_directory = str(Path(paths[0]).parent)
        self._positions_model.replace_all(self._records)
        # Composed once: the console line and the Results card header are the
        # same string, so they can never drift apart.
        self._last_load_summary = (
            f"Loaded {len(self._records)} of {len(paths)} "
            f"spin mill image(s) from {self._last_directory}")
        logger.info("%s", self._last_load_summary)
        self._recompute()

    @Slot()
    def clearPositions(self) -> None:
        """Reset the calculator: drop the cached parse and both tables."""
        self._records = []
        self._parse_errors = []
        self._positions_model.replace_all([])
        self._sem_positions_model.replace_all([])
        self._status_text = ""
        self._results_text = ""
        self._last_load_summary = ""
        logger.info("Spin mill positions cleared.")
        self.changed.emit()
        self.statusUpdated.emit("Positions cleared.")

    # --- Shared recompute path ------------------------------------------------
    def _recompute(self, announce: bool = True) -> None:
        """Single calculation path for both loadImages and target changes.

        ``announce`` gates the INFO log block and the status toast: True
        for user actions (a load), False for target-angle ticks — the fit
        quality and status are alpha-invariant, so re-announcing per tick
        only buries the per-load audit entry and restarts the toast timer.
        """
        inputs = SEMGeometryInputs.from_records(
            self._records, self._target_milling_angle)
        result = self._calculator.calculate(inputs)

        rows: List[SemPositionCandidate] = []
        # Fitted candidates only on OK — 2.3's contract: an AMBIGUOUS
        # fit's numbers are diagnostics for the log, never UI rows the
        # user might drive the stage to.
        if result.status == SEMGeometryStatus.OK:
            rows.append(SemPositionCandidate(
                SOURCE_CALCULATED,
                result.target_stage_rotation_rad,
                result.target_stage_tilt_rad))
            rows.append(SemPositionCandidate(
                SOURCE_ALTERNATE,
                result.alternate_stage_rotation_rad,
                result.alternate_stage_tilt_rad))
        # Measured candidates come from the raw data, not the fit, so
        # they are reported regardless of fit status.
        rows.extend(measured_perpendicular_candidates(
            self._records, self._target_milling_angle))
        self._sem_positions_model.update_or_replace(rows)

        self._status_text = self._compose_status(result)
        # Rebuilt on every recompute (loads and target ticks alike) so the
        # card never disagrees with the tables beside it.
        self._results_text = self._compose_results(result)
        if announce:
            logger.info("%s", formatter.log_block(result))
        else:
            logger.debug("%s", formatter.log_block(result))
        self.changed.emit()
        if announce:
            self.statusUpdated.emit(self._status_text)

    def _compose_status(self, result) -> str:
        """Terse one-liner for the StatusBar; the detail lives in resultsText.

        The bar elides, so it carries only the outcome plus a count of any
        files that failed to parse. Per-file reasons and fit warnings are
        the Results card's job. Insufficient data is phrased to match the
        Position Alignment page's table placeholder rather than the
        calculator's own (longer) status_message, which the card still shows.
        """
        if result.status == SEMGeometryStatus.INSUFFICIENT_DATA:
            message = "3 or more positions required."
        else:
            message = formatter.status_line(result)
        if self._parse_errors:
            message += f" ({len(self._parse_errors)} skipped)"
        return message

    def _compose_results(self, result) -> str:
        """The Results card's text: what the console log carries, in the UI.

        Load summary, then the per-file parse failures, then the same audit
        block emitted to the logger. The summary and errors persist across
        target-angle ticks (they describe the load, not the calculation).
        """
        sections: List[str] = []
        if self._last_load_summary:
            sections.append(self._last_load_summary)
        if self._parse_errors:
            lines = [f"{len(self._parse_errors)} file(s) could not be parsed:"]
            lines += [f"  - {error}" for error in self._parse_errors]
            sections.append("\n".join(lines))
        sections.append(formatter.log_block(result))
        return "\n\n".join(sections)
