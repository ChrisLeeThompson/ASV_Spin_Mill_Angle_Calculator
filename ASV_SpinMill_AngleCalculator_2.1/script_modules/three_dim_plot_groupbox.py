"""
Module handles the 3D FIB visualization group box.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel)
from script_modules.visualization_canvas import VisualizationCanvas
from script_modules.script_styles import AppStyles


class ThreeDimPlotGroupBox(QGroupBox):
    """Groupbox containing the 3D FIB geometry visualization."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(AppStyles.GroupBox.plot_gb())
        # Create components
        self._create_components()
        # set component styles
        self._set_component_styles()
        # Set up layout
        self._setup_layout()
        # connect signals
        self._connect_signals()

    def _create_components(self):
        # create plot canvas
        self.canvas = VisualizationCanvas(parent=self, width=8, height=8, dpi=100)
        # Create legend labels
        self.legend_sem_line = QLabel("■ ")
        self.legend_sem = QLabel("SEM")
        self.legend_fib_line = QLabel("■ ")
        self.legend_fib = QLabel("FIB")
        self.legend_aoi_line = QLabel("■ ")
        self.legend_aoi = QLabel("Tilted AOI Circle")
        # create view buttons
        self.ccd_button = QPushButton("CCD View")
        self.fib_button = QPushButton("FIB View")

    def _set_component_styles(self):
        # legend styles
        self.legend_sem_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_SEM_COLOR}; font-size: 16px;")
        self.legend_sem.setStyleSheet(AppStyles.Label.legend())
        self.legend_fib_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_FIB_COLOR}; font-size: 16px;")
        self.legend_fib.setStyleSheet(AppStyles.Label.legend())
        self.legend_aoi_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR}; font-size: 16px;")
        self.legend_aoi.setStyleSheet(AppStyles.Label.legend())
        # button styles
        self.ccd_button.setStyleSheet(AppStyles.Button.default())
        self.fib_button.setStyleSheet(AppStyles.Button.default())

    def _setup_layout(self):
        """Set up the layout of the group box."""
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.canvas)
        # button layout
        button_layout = QHBoxLayout()
        # add legend and buttons to layout
        button_layout.addWidget(self.legend_sem_line)
        button_layout.addWidget(self.legend_sem)
        button_layout.addWidget(self.legend_fib_line)
        button_layout.addWidget(self.legend_fib)
        button_layout.addWidget(self.legend_aoi_line)
        button_layout.addWidget(self.legend_aoi)
        button_layout.addStretch()
        button_layout.addWidget(self.ccd_button)
        button_layout.addWidget(self.fib_button)
        # add button layout to main layout
        main_layout.addLayout(button_layout)
        # set layout
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.ccd_button.clicked.connect(self.canvas.view_ccd)
        self.fib_button.clicked.connect(self.canvas.view_fib)

    def update_plot(self, radius, ellipse, fib_unit):
        """
        Update the 3D plot with new geometry.
        Args:
            radius: Circle radius
            ellipse: Nx3 array of ellipse coordinates
            fib_unit: Unit vector for FIB direction
        """
        self.canvas.plot_fib_geometry(
            radius=radius,
            ellipse=ellipse,
            fib_unit=fib_unit
        )