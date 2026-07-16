"""Root application controller exposed to QML as ``appController``.

The single context-property (mirroring Hydra's ``AppController``).
It owns one sub-controller per page-feature and exposes each as a constant
``QObject`` property, so QML reaches page logic namespaced -- e.g.
``appController.fib.calculatedMillingAngle`` -- and per-page calculators stay
isolated instead of colliding on names at the top level.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, Slot

from asv_spin_mill_angle_calc.fib_angle_controller import FibAngleController
from asv_spin_mill_angle_calc.frame_image_provider import FrameImageProvider
from asv_spin_mill_angle_calc.microscope_controller import MicroscopeController
from asv_spin_mill_angle_calc.position_alignment_controller import (
    PositionAlignmentController,
)
from asv_spin_mill_angle_calc.sem_angle_controller import SemAngleController


class AppController(QObject):
    """Top-level controller wired to the QML root context."""

    def __init__(self, parent: QObject | None = None, *,
                 frame_provider: FrameImageProvider | None = None) -> None:
        super().__init__(parent)
        self._fib = FibAngleController(self)
        self._sem = SemAngleController(self)
        self._microscope = MicroscopeController(self)
        self._position_alignment = PositionAlignmentController(
            self, frame_provider=frame_provider,
            ops_provider=self._microscope.current_ops)
        # Defensive backstop: user disconnects are refused while the
        # alignment automation holds the client (QML also disables the
        # switch, but a guard in the controller cannot be raced).
        self._microscope.set_busy_guard(self._position_alignment.is_busy)

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
