"""
Module handles the FIB visualization group box with tabbed 2D and 3D plots.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QTabWidget, QWidget)
from script_modules.three_dim_canvas import ThreeDimCanvas
from script_modules.fib_geometry_calculator import FIBGeometryCalculator
from script_modules.script_styles import AppStyles


class ThreeDimTab(QWidget):
    """Widget containing the 3D visualization with controls."""

    def __init__(self):
        super().__init__()
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
        self.canvas = ThreeDimCanvas(parent=self, width=12, height=12, dpi=100)
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
        """Set up the layout of the 3D tab."""
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


class TwoDimTab(QWidget):
    """Widget containing the 2D side-by-side visualizations."""

    def __init__(self):
        super().__init__()
        # Create components
        self._create_components()
        # Set up layout
        self._setup_layout()

    def _create_components(self):
        # Placeholder for 2D plots - we'll implement these next
        self.side_view_label = QLabel("Side View (Coming Soon)")
        self.side_view_label.setStyleSheet(AppStyles.Label.default())
        self.fib_view_label = QLabel("FIB View (Coming Soon)")
        self.fib_view_label.setStyleSheet(AppStyles.Label.default())

    def _setup_layout(self):
        """Set up the layout of the 2D tab."""
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


class FIBPlotGroupBox(QGroupBox):
    """Groupbox containing tabbed 2D and 3D FIB geometry visualizations."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(AppStyles.GroupBox.plot_gb())
        # Create tab widget
        self._create_tabs()
        # Set up layout
        self._setup_layout()
        # Initialize with default values
        self.update_plot(diameter=800, measured_minor=55.8)

    def _create_tabs(self):
        """Create the tab widget and individual tabs."""
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(AppStyles.Tab.tabs())

        # Create tab instances
        self.three_dim_tab = ThreeDimTab()
        self.two_dim_tab = TwoDimTab()

        # Add tabs to widget
        self.tab_widget.addTab(self.three_dim_tab, "3D View")
        self.tab_widget.addTab(self.two_dim_tab, "2D Views")

    def _setup_layout(self):
        """Set up the layout of the group box."""
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

    def update_plot(self, diameter, measured_minor):
        """
        Update all plots with new geometry.
        Args:
            diameter: AOI circle diameter in micrometers
            measured_minor: Measured ellipse height in micrometers
        """
        # Calculate geometry
        geometry = FIBGeometryCalculator.calculate_milling_geometry(
            diameter=diameter,
            measured_minor=measured_minor
        )

        # Update both tabs with the same geometry
        self.three_dim_tab.update_plot(
            radius=geometry['radius'],
            ellipse=geometry['ellipse'],
            fib_unit=geometry['fib_unit']
        )

        self.two_dim_tab.update_plot(
            radius=geometry['radius'],
            ellipse=geometry['ellipse'],
            fib_unit=geometry['fib_unit']
        )