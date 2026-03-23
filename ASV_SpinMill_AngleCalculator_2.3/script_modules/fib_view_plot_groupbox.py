"""
Module handles the FIB view visualization group box.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                               QLabel)
from script_modules.two_dim_canvas import TwoDimCanvas
from script_modules.app_styles import AppStyles


class FibViewPlotGroupBox(QGroupBox):
    """Groupbox containing the FIB view visualization."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(AppStyles.GroupBox.plot())
        # Create components
        self._create_components()
        # set component styles
        self._set_component_styles()
        # Set up layout
        self._setup_layout()

    def _create_components(self):
        # Create FIB view canvas - larger size for single plot
        self.fib_view_canvas = TwoDimCanvas(parent=self, width=12, height=12, dpi=100)
        # create legend labels
        self.legend_aoi_line = QLabel("■ ")
        self.legend_aoi = QLabel("Tilted AOI Circle")

    def _set_component_styles(self):
        # legend styles
        self.legend_aoi_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR}; font-size: 16px;")
        self.legend_aoi.setStyleSheet(AppStyles.Label.legend())

    def _setup_layout(self):
        """Set up the layout of the group box."""
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.fib_view_canvas)
        # legend layout
        legend_layout = QHBoxLayout()
        # add legend to layout
        legend_layout.addWidget(self.legend_aoi_line)
        legend_layout.addWidget(self.legend_aoi)
        legend_layout.addStretch()
        # add legend layout to main layout
        main_layout.addLayout(legend_layout)
        # set layout
        self.setLayout(main_layout)

    def update_plot(self, diameter, measured_minor):
        """
        Update the FIB view plot with new geometry.
        Args:
            diameter: AOI diameter
            measured_minor: Measured ellipse height
        """
        self.fib_view_canvas.plot_fib_view(diameter, measured_minor)