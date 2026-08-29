"""QObject controller for the FIB Angle Calculator page.

Thin Qt wrapper around the Qt-free :mod:`asv_spin_mill_angle_calc.spin_mill_geometry`.
QML writes the three inputs (writable properties) and binds the two result
labels to the computed output properties; every value change re-evaluates the
bindings via the single ``changed`` notify signal.

Controller idioms used throughout the app: functional ``Signal`` class
attribute, ``@Property`` getters/setters where each setter is a no-op when the
value is unchanged (breaking the QML->Python->QML echo loop), ``camelCase``
for the QML surface, ``_snake_case`` backing fields.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal

from asv_spin_mill_angle_calc import spin_mill_geometry as geometry

# Domain defaults — mirror the FIB page's spin-box defaults so the results are
# correct before the user touches anything (asin(55.8/800) = 4.0, tilt = 0.0).
_DEFAULT_TARGET_MILLING_ANGLE_DEG = 4.0
_DEFAULT_AOI_DIAMETER_UM = 800.0
_DEFAULT_MEASURED_ELLIPSE_HEIGHT_UM = 55.8


class FibAngleController(QObject):
    """Live FIB milling-angle calculation for the FIB Angle Calculator page."""

    # Single notify signal: the two inputs feed the two computed outputs, so
    # any input change refreshes both output bindings.
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._target_milling_angle = _DEFAULT_TARGET_MILLING_ANGLE_DEG
        self._aoi_diameter = _DEFAULT_AOI_DIAMETER_UM
        self._measured_ellipse_height = _DEFAULT_MEASURED_ELLIPSE_HEIGHT_UM

    # --- Inputs (written from QML) ---------------------------------------
    @Property(float, notify=changed)
    def targetMillingAngle(self) -> float:
        return self._target_milling_angle

    @targetMillingAngle.setter
    def targetMillingAngle(self, value: float) -> None:
        value = float(value)
        if value == self._target_milling_angle:
            return
        self._target_milling_angle = value
        self.changed.emit()

    @Property(float, notify=changed)
    def aoiDiameter(self) -> float:
        return self._aoi_diameter

    @aoiDiameter.setter
    def aoiDiameter(self, value: float) -> None:
        value = float(value)
        if value == self._aoi_diameter:
            return
        self._aoi_diameter = value
        self.changed.emit()

    @Property(float, notify=changed)
    def measuredEllipseHeight(self) -> float:
        return self._measured_ellipse_height

    @measuredEllipseHeight.setter
    def measuredEllipseHeight(self, value: float) -> None:
        value = float(value)
        if value == self._measured_ellipse_height:
            return
        self._measured_ellipse_height = value
        self.changed.emit()

    # --- Outputs (bound by QML) ------------------------------------------
    @Property(float, notify=changed)
    def calculatedMillingAngle(self) -> float:
        return geometry.calculated_milling_angle_deg(
            self._aoi_diameter, self._measured_ellipse_height
        )

    @Property(float, notify=changed)
    def tiltStageBy(self) -> float:
        return geometry.tilt_stage_by_deg(
            self._target_milling_angle, self.calculatedMillingAngle
        )
