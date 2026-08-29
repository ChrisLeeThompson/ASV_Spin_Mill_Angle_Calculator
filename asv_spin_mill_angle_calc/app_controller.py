"""Root application controller exposed to QML as ``appController``.

The single context property. It owns one sub-controller per page
feature and exposes each as a constant ``QObject`` property, so QML
reaches page logic namespaced — e.g.
``appController.fib.calculatedMillingAngle`` — and per-page calculators
stay isolated instead of colliding on names at the top level.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Property, QObject, QSettings, Slot

from asv_spin_mill_angle_calc.alignment_config import DEFAULT_DEBUG_FRAMES_DIR
from asv_spin_mill_angle_calc.fib_angle_controller import FibAngleController
from asv_spin_mill_angle_calc.frame_image_provider import FrameImageProvider
from asv_spin_mill_angle_calc.microscope_controller import MicroscopeController
from asv_spin_mill_angle_calc.position_alignment_controller import (
    PositionAlignmentController,
)
from asv_spin_mill_angle_calc.sem_angle_controller import SemAngleController
from asv_spin_mill_angle_calc.settings_controller import SettingsController


class AppController(QObject):
    """Top-level controller wired to the QML root context."""

    def __init__(self, parent: QObject | None = None, *,
                 frame_provider: FrameImageProvider | None = None,
                 settings_factory: Callable[[], QSettings] = QSettings,
                 ) -> None:
        """Create the per-page sub-controllers and wire them together.

        ``settings_factory`` is a test seam, passed through to
        SettingsController so tests can swap the registry-backed default
        store for a throwaway INI file.
        """
        super().__init__(parent)
        self._settings = SettingsController(
            self, settings_factory=settings_factory)
        self._fib = FibAngleController(self)
        self._sem = SemAngleController(self)
        self._microscope = MicroscopeController(self)
        self._position_alignment = PositionAlignmentController(
            self, frame_provider=frame_provider,
            ops_provider=self._microscope.current_ops,
            debug_dir_provider=self._debug_frames_dir_setting,
            tuning_provider=self._alignment_tuning_setting)
        # Defensive backstop: user disconnects are refused while the
        # alignment automation holds the client (QML also disables the
        # switch, but a guard in the controller cannot be raced).
        self._microscope.set_busy_guard(self._position_alignment.is_busy)

    def _debug_frames_dir_setting(self) -> str:
        """Map the Save Debug Images setting to its capture directory.

        The canonical on-repo folder when enabled, empty (capture off)
        otherwise. Read by the alignment controller once at each Start.
        """
        return (DEFAULT_DEBUG_FRAMES_DIR
                if self._settings.saveDebugImages else "")

    def _alignment_tuning_setting(self) -> dict:
        """Return the Settings page's AlignmentConfig field overrides.

        Read by the alignment controller once at each Start, so a
        mid-run edit applies to the next run. The settings→config field
        mapping lives in SettingsController (one place that knows both
        names); this hop exists so the alignment controller depends on a
        plain callable rather than on the settings object, matching
        debug_dir_provider.
        """
        return self._settings.alignment_overrides()

    @Property(QObject, constant=True)
    def settings(self) -> SettingsController:
        """User preferences (Settings page), persisted via QSettings."""
        return self._settings

    @Property(QObject, constant=True)
    def fib(self) -> FibAngleController:
        """FIB Angle Calculator page logic."""
        return self._fib

    @Property(QObject, constant=True)
    def sem(self) -> SemAngleController:
        """SEM Angle Calculator page logic."""
        return self._sem

    @Property(QObject, constant=True)
    def microscope(self) -> MicroscopeController:
        """Microscope connection state and lifecycle (Position Alignment page)."""
        return self._microscope

    @Property(QObject, constant=True)
    def positionAlignment(self) -> PositionAlignmentController:
        """Position Alignment automation (image viewer, Start/Stop/Confirm)."""
        return self._position_alignment

    @Slot()
    def shutdown(self) -> None:
        """App-quit teardown. Wired to app.aboutToQuit by the entry point.

        Alignment first: its worker must stop using the client before the
        microscope controller disconnects it.
        """
        self._position_alignment.shutdown()
        self._microscope.shutdown()
