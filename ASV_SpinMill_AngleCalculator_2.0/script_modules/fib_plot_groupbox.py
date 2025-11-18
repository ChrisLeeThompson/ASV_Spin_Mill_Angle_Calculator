"""
Module handles the FIB visualization group box with 3D plot.
"""
from PySide6.QtWidgets import QGroupBox, QVBoxLayout
from script_modules.mpl_canvas import MplCanvas
from script_modules.fib_geometry_calculator import FIBGeometryCalculator
from script_modules.script_styles import AppStyles


class FIBPlotGroupBox(QGroupBox):
    """Groupbox containing the 3D FIB geometry visualization."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(AppStyles.GroupBox.plot_gb())
        # Create the matplotlib canvas
        self.canvas = MplCanvas(parent=self, width=5, height=5, dpi=100)
        # Add view control buttons
        self.canvas.add_fib_ccd_view_buttons()
        # Set up layout
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        # Initialize with default values
        self.update_plot(diameter=800, measured_minor=55.8)

    def update_plot(self, diameter, measured_minor):
        """
        Update the 3D plot with new geometry.
        Args:
            diameter: AOI circle diameter in micrometers
            measured_minor: Measured ellipse height in micrometers
        """
        # Calculate geometry
        geometry = FIBGeometryCalculator.calculate_milling_geometry(
            diameter=diameter,
            measured_minor=measured_minor
        )
        # Update plot
        self.canvas.plot_fib_geometry(
            radius=geometry['radius'],
            ellipse=geometry['ellipse'],
            fib_unit=geometry['fib_unit']
        )
