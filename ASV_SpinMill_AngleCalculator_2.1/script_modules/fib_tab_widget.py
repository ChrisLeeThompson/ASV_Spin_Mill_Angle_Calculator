"""
Module creates the FIB tab widget containing input controls and visualizations.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from script_modules.fib_groupbox import FIBGroupBox
from script_modules.three_dim_plot_groupbox import ThreeDimPlotGroupBox
from script_modules.ccd_view_plot_groupbox import CcdViewPlotGroupBox
from script_modules.fib_view_plot_groupbox import FibViewPlotGroupBox
from script_modules.fib_geometry_calculator import FIBGeometryCalculator
from script_modules.script_styles import AppStyles


class FIBTabWidget(QWidget):
    """Widget containing the complete FIB workflow with inputs and visualizations."""

    def __init__(self):
        super().__init__()
        self._setup_layout()
        # Trigger initial update
        self._initialize_plots()

    def _setup_layout(self):
        """Set up the layout with input groupbox and plot tabs."""
        main_layout = QVBoxLayout()
        # FIB input groupbox at the top
        self.fib_groupbox = FIBGroupBox()
        main_layout.addWidget(self.fib_groupbox)
        # Tab widget with three separate plot groupboxes
        self.plot_tabs = QTabWidget()
        self.plot_tabs.setStyleSheet(AppStyles.Tab.tabs())
        # Create the three plot groupboxes
        self.three_dim_plot_groupbox = ThreeDimPlotGroupBox()
        self.ccd_view_plot_groupbox = CcdViewPlotGroupBox()
        self.fib_view_plot_groupbox = FibViewPlotGroupBox()
        # Add them as separate tabs
        self.plot_tabs.addTab(self.three_dim_plot_groupbox, "3D View")
        self.plot_tabs.addTab(self.ccd_view_plot_groupbox, "CCD View")
        self.plot_tabs.addTab(self.fib_view_plot_groupbox, "FIB View")
        main_layout.addWidget(self.plot_tabs)
        # Connect FIB groupbox changes to update all plot groupboxes
        self.fib_groupbox.values_changed.connect(self._update_plots)
        # set main layout
        self.setLayout(main_layout)

    def _initialize_plots(self):
        """Initialize all plots with default values from FIB groupbox."""
        diameter = self.fib_groupbox.aoi_diameter_spinbox.value()
        measured_minor = self.fib_groupbox.measured_ellipse_height_spinbox.value()
        calculated_angle = float(self.fib_groupbox.calculated_milling_angle_result.text())
        self._update_plots(diameter, measured_minor, calculated_angle)

    def _update_plots(self, diameter, measured_minor, calculated_angle):
        """
        Update all plot groupboxes when FIB values change.

        Args:
            diameter: AOI circle diameter in micrometers
            measured_minor: Measured ellipse height in micrometers
            calculated_angle: Calculated milling angle in degrees
        """
        # Calculate geometry once
        geometry = FIBGeometryCalculator.calculate_milling_geometry(
            diameter=diameter,
            measured_minor=measured_minor
        )

        # Update 3D plot groupbox
        self.three_dim_plot_groupbox.update_plot(
            radius=geometry['radius'],
            ellipse=geometry['ellipse'],
            fib_unit=geometry['fib_unit']
        )

        # Update CCD view plot groupbox
        self.ccd_view_plot_groupbox.update_plot(
            calculated_angle=calculated_angle,
            diameter=diameter
        )

        # Update FIB view plot groupbox
        self.fib_view_plot_groupbox.update_plot(
            diameter=diameter,
            measured_minor=measured_minor
        )
