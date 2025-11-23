"""
Module handles the CCD view visualization group box.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                               QLabel)
from script_modules.two_dim_canvas import TwoDimCanvas
from script_modules.script_styles import AppStyles


class CcdViewPlotGroupBox(QGroupBox):
    """Groupbox containing the CCD view (side view) visualization."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(AppStyles.GroupBox.plot_gb())
        # Create components
        self._create_components()
        # set component styles
        self._set_component_styles()
        # Set up layout
        self._setup_layout()

    def _create_components(self):
        # Create CCD view canvas - larger size for single plot
        self.ccd_view_canvas = TwoDimCanvas(parent=self, width=10, height=10, dpi=100)
        # Create legend labels
        self.legend_sem_line = QLabel("■ ")
        self.legend_sem = QLabel("SEM")
        self.legend_fib_line = QLabel("■ ")
        self.legend_fib = QLabel("FIB")
        self.legend_aoi_line = QLabel("■ ")
        self.legend_aoi = QLabel("Tilted AOI Circle")

    def _set_component_styles(self):
        # legend styles
        self.legend_sem_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_SEM_COLOR}; font-size: 16px;")
        self.legend_sem.setStyleSheet(AppStyles.Label.legend())
        self.legend_fib_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_FIB_COLOR}; font-size: 16px;")
        self.legend_fib.setStyleSheet(AppStyles.Label.legend())
        self.legend_aoi_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR}; font-size: 16px;")
        self.legend_aoi.setStyleSheet(AppStyles.Label.legend())

    def _setup_layout(self):
        """Set up the layout of the group box."""
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.ccd_view_canvas)
        # legend layout
        legend_layout = QHBoxLayout()
        # add legend to layout
        legend_layout.addWidget(self.legend_sem_line)
        legend_layout.addWidget(self.legend_sem)
        legend_layout.addWidget(self.legend_fib_line)
        legend_layout.addWidget(self.legend_fib)
        legend_layout.addWidget(self.legend_aoi_line)
        legend_layout.addWidget(self.legend_aoi)
        legend_layout.addStretch()
        # add legend layout to main layout
        main_layout.addLayout(legend_layout)
        # set layout
        self.setLayout(main_layout)

    def update_plot(self, calculated_angle, diameter):
        """
        Update the CCD view plot with new geometry.
        Args:
            calculated_angle: Calculated milling angle in degrees
            diameter: AOI diameter
        """
        self.ccd_view_canvas.plot_ccd_view(calculated_angle, diameter)
