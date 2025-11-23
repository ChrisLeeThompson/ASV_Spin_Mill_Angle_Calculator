import sys
import logging
from PySide6.QtWidgets import (QMainWindow, QApplication, QWidget,
                               QVBoxLayout, QHBoxLayout, QTabWidget)
from pathlib import Path
from script_modules.fib_groupbox import FIBGroupBox
from script_modules.three_dim_plot_groupbox import ThreeDimPlotGroupBox
from script_modules.ccd_view_plot_groupbox import CcdViewPlotGroupBox
from script_modules.fib_view_plot_groupbox import FibViewPlotGroupBox
from script_modules.fib_geometry_calculator import FIBGeometryCalculator
from script_modules.script_styles import AppStyles


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        # window title
        self.setWindowTitle("ASV Spin Mill Angle Calculator 2.1")
        # set initial window size based on screen size
        screen_size = QApplication.primaryScreen().availableGeometry()
        if int(screen_size.width()) <= 1536:  # laptop, for example
            self.setGeometry(50, 50, int(screen_size.width() * 0.7), int(screen_size.height() * 0.85))
        else:
            self.setGeometry(100, 100, 1000, 800)  # desktop
        # create and set main widget
        self.main_widget = MainWidget()
        self.setCentralWidget(self.main_widget)
        # set style
        self.setStyleSheet(AppStyles.MainWindow.window())


class MainWidget(QWidget):

    def __init__(self):
        super().__init__()
        # ui asset paths
        base_path = Path(__file__).parent / "script_assets"
        self.color_path = base_path / "catbug_color_2.png"
        self.grayscale_path = base_path / "catbug_grayscale_2.png"
        # set layout
        self._setup_layout()

    def _setup_layout(self):
        main_layout = QHBoxLayout()
        main_layout.addLayout(self._create_fib_column())
        self.setLayout(main_layout)

    def _create_fib_column(self):
        """Create the FIB column with input groupbox and three separate plot view tabs."""
        layout = QVBoxLayout()

        # FIB input groupbox at the top
        self.fib_groupbox = FIBGroupBox()
        layout.addWidget(self.fib_groupbox)

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

        layout.addWidget(self.plot_tabs)

        # Connect FIB groupbox changes to update all plot groupboxes
        self.fib_groupbox.values_changed.connect(self._update_all_plots)

        # Trigger initial update manually to ensure all plots are initialized
        # Get the current calculated angle from the FIB groupbox
        diameter = self.fib_groupbox.aoi_diameter_spinbox.value()
        measured_minor = self.fib_groupbox.measured_ellipse_height_spinbox.value()

        # Parse the calculated angle from the result label
        try:
            calculated_angle = float(self.fib_groupbox.calculated_milling_angle_result.text())
        except (ValueError, AttributeError):
            calculated_angle = 4.0  # Default fallback

        self._update_all_plots(diameter, measured_minor, calculated_angle)

        return layout

    def _update_all_plots(self, diameter, measured_minor, calculated_angle):
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

    def _create_sem_column(self):
        pass


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(format="%(asctime)s:\t%(levelname)s:\t%(funcName)s:\t%(message)s", level=logging.DEBUG)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.INFO)


def main():
    setup_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
