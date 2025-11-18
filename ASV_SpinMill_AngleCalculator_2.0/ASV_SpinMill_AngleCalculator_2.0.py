import sys
import logging
from PySide6.QtWidgets import (QMainWindow, QApplication, QWidget, QVBoxLayout,
                               QHBoxLayout, QGroupBox, QGridLayout, QLabel, QSpinBox, QLayout)
from pathlib import Path
from script_modules.fib_groupbox import FIBGroupBox
from script_modules.fib_plot_groupbox import FIBPlotGroupBox
from script_modules.script_styles import AppStyles


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        # window title
        self.setWindowTitle("ASV Spin Mill Angle Calculator 2.0")
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

    def _create_fib_column(self) -> QLayout:
        layout = QVBoxLayout()
        self.fib_groupbox = FIBGroupBox()
        self.fib_plot_groupbox = FIBPlotGroupBox()
        self.fib_groupbox.values_changed.connect(
            lambda diameter, measured_minor, _: self.fib_plot_groupbox.update_plot(
                diameter, measured_minor
            )
        )
        layout.addWidget(self.fib_groupbox)
        layout.addWidget(self.fib_plot_groupbox)
        return layout

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
