"""
Module creates the FIB tab widget containing input controls and visualizations.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget)
from script_modules.fib_groupbox import FIBGroupBox
from script_modules.three_dim_plot_groupbox import ThreeDimPlotGroupBox
from script_modules.ccd_view_plot_groupbox import CcdViewPlotGroupBox
from script_modules.fib_view_plot_groupbox import FibViewPlotGroupBox
from script_modules.app_styles import AppStyles


class FIBTabWidget(QWidget):
    """Widget containing the complete FIB workflow with inputs and visualizations."""

    def __init__(self):
        super().__init__()
        self._create_components()
        self._setup_layout()
        self._connect_signals()

    def _create_components(self):
        # FIB input groupbox at the top
        self.fib_groupbox = FIBGroupBox()
        # Tab widget with three separate plot groupboxes
        self.plot_tabs = QTabWidget()
        self.plot_tabs.setStyleSheet(AppStyles.Tab.tabs())
        # Create the three plot groupboxes
        self.three_dim_plot_groupbox = ThreeDimPlotGroupBox()
        self.ccd_view_plot_groupbox = CcdViewPlotGroupBox()
        self.fib_view_plot_groupbox = FibViewPlotGroupBox()

    def _setup_layout(self):
        """Set up the layout with input groupbox and plot tabs."""
        # main layout
        main_layout = QVBoxLayout()
        # add FIB groupbox at the top
        main_layout.addWidget(self.fib_groupbox)
        # Add plot tabs
        self.plot_tabs.addTab(self.three_dim_plot_groupbox, "3D View")
        self.plot_tabs.addTab(self.ccd_view_plot_groupbox, "CCD View")
        self.plot_tabs.addTab(self.fib_view_plot_groupbox, "FIB View")
        main_layout.addWidget(self.plot_tabs)
        # set main layout
        self.setLayout(main_layout)

    def _connect_signals(self):
        # Connect FIB groupbox changes to update all plot groupboxes.
        # FIBGroupBox.__init__ calls _update_calculations() which emits
        # values_changed before this connection is made, so we trigger
        # the first plot update explicitly here after connecting.
        self.fib_groupbox.values_changed.connect(self._update_plots)
        self.fib_groupbox._update_calculations()

    def _update_plots(self, geometry):
        """
        Update all plot groupboxes when FIB values change.

        Args:
            geometry: Dict from FIBGeometryCalculator containing:
                radius, ellipse, fib_unit, plane_angle,
                diameter, measured_minor
        """
        # Update 3D plot groupbox
        self.three_dim_plot_groupbox.update_plot(
            radius=geometry['radius'],
            ellipse=geometry['ellipse'],
            fib_unit=geometry['fib_unit']
        )

        # Update CCD view plot groupbox
        self.ccd_view_plot_groupbox.update_plot(
            calculated_angle=geometry['plane_angle'],
            diameter=geometry['diameter']
        )

        # Update FIB view plot groupbox
        self.fib_view_plot_groupbox.update_plot(
            diameter=geometry['diameter'],
            measured_minor=geometry['measured_minor']
        )