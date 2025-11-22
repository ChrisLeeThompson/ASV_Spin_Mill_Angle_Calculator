"""
Module handles the 2D FIB visualization group box.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLabel)
from script_modules.script_styles import AppStyles


class TwoDimPlotGroupBox(QGroupBox):
    """Group box containing 2D FIB visualization plots."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(AppStyles.GroupBox.plot_gb())
        # create components
        self._create_components()
        # set up layout
        self._setup_layout()

    def _create_components(self):
        # Placeholder for 2D plots - we'll implement these next
        self.side_view_label = QLabel("Side View (Coming Soon)")
        self.side_view_label.setStyleSheet(AppStyles.Label.default())
        self.fib_view_label = QLabel("FIB View (Coming Soon)")
        self.fib_view_label.setStyleSheet(AppStyles.Label.default())

    def _setup_layout(self):
        """Set up the layout of the group box."""
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.side_view_label)
        main_layout.addWidget(self.fib_view_label)
        self.setLayout(main_layout)

    def update_plot(self, radius, ellipse, fib_unit):
        """
        Update the 2D plots with new geometry.
        Args:
            radius: Circle radius
            ellipse: Nx3 array of ellipse coordinates
            fib_unit: Unit vector for FIB direction
        """
        # Placeholder - will implement 2D plotting logic
        pass

