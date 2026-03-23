"""
ASV Spin Mill Angle Calculator 2.3

Application for calculating FIB milling angles and SEM alignment
corrections for dual-beam microscopy workflows.

The code was written with assistance from Claude AI.

Chris Thompson
"""
import sys
import logging
from PySide6.QtWidgets import (QMainWindow, QApplication, QWidget,
                               QVBoxLayout, QTabWidget)
from PySide6.QtGui import QIcon, QFont
from script_modules.fib_tab_widget import FIBTabWidget
from script_modules.sem_tab_widget import SEMTabWidget
from script_modules.app_styles import AppStyles, ICON_PATH


logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        # Set window title and size
        self.setWindowTitle(AppStyles.AppText.WINDOW_TITLE)
        screen_size = QApplication.primaryScreen().availableGeometry()
        if int(screen_size.width()) <= 1536:  # laptop, for example
            self.setGeometry(50, 50, int(screen_size.width() * 0.8), int(screen_size.height() * 0.85))
        else:
            self.setGeometry(50, 50, AppStyles.Dimensions.WINDOW_WIDTH, AppStyles.Dimensions.WINDOW_HEIGHT)
        # Set window icon
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        # Set main window style
        self.setStyleSheet(AppStyles.Window.window())
        # Set main window margins
        self.setContentsMargins(
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN,
            AppStyles.Dimensions.MAIN_WINDOW_MARGIN
        )
        # Create components
        self._create_components()
        # Setup layout
        self._setup_layout()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def _create_components(self):
        """Create the main tab widget and tab content widgets."""
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet(AppStyles.Tab.tabs())
        self.fib_tab = FIBTabWidget()
        self.sem_tab = SEMTabWidget()

    def _setup_layout(self):
        """Set up the central widget and main layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # Add tabs
        self.main_tabs.addTab(self.fib_tab, "FIB Angle Calculator")
        self.main_tabs.addTab(self.sem_tab, "SEM Angle Calculator")
        main_layout.addWidget(self.main_tabs)


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        format="%(asctime)s:\t%(levelname)s:\t%(name)s\t%(funcName)s:\t%(message)s",
        level=logging.INFO,
        force=True
    )
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.INFO)


def main():
    """Main function to run the application."""

    setup_logging()

    app = QApplication(sys.argv)
    font = app.font()
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()