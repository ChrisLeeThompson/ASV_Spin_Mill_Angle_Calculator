import sys
import logging
from PySide6.QtWidgets import (QMainWindow, QApplication, QWidget,
                               QVBoxLayout, QTabWidget)
from pathlib import Path
from script_modules.fib_tab_widget import FIBTabWidget
from script_modules.sem_tab_widget import SEMTabWidget
from script_modules.script_styles import AppStyles


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        # window title
        self.setWindowTitle("ASV Spin Mill Angle Calculator 2.2")
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
        # set layout
        self._setup_layout()

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        # create main tab widget
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet(AppStyles.Tab.tabs())
        # create FIB and SEM tab widgets
        self.fib_tab = FIBTabWidget()
        self.sem_tab = SEMTabWidget()
        # add tabs
        self.main_tabs.addTab(self.fib_tab, "FIB Angle Calculator")
        self.main_tabs.addTab(self.sem_tab, "SEM Angle Calculator")
        # set up layout
        main_layout.addWidget(self.main_tabs)
        # set layout
        self.setLayout(main_layout)


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
