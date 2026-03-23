"""
Module handles the image drop area.
"""
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, Signal


class ImageFileValidator:

    def __init__(self, allowed_extension=None):
        self.allowed_extension = allowed_extension or [".png"]

    def is_valid(self, file_path: str) -> bool:
        return any(file_path.lower().endswith(ext) for ext in self.allowed_extension)


class ImageDropLabel(QLabel):
    # signal emitted when files are dropped. A list of file paths is sent.
    file_path_list_signal: Signal = Signal(list)

    def __init__(self, color_path, grayscale_path, validator: ImageFileValidator = None):
        super().__init__()
        self.scale_factor: float = 1.6  # adjust scale of image in drop area groupbox
        self.validator = validator or ImageFileValidator()
        self.setAcceptDrops(True)
        self.color_path = str(color_path)
        self.grayscale_path = str(grayscale_path)
        # set default pix map
        self.pix = QPixmap(self.grayscale_path)
        self.setPixmap(self.pix)
        # set default label size
        self.setScaledContents(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(int(self.pix.width() // self.scale_factor),
                          int(self.pix.height() // self.scale_factor))
        self.setMargin(4)

    def set_image_grayscale(self):
        """
        Method sets the image drop zone to grayscale (default/inactive state).
        :return:
        """
        self.pix = QPixmap(self.grayscale_path)
        self.setPixmap(self.pix)

    def set_image_color(self):
        """
        Method sets the image drop zone to color (active/hover state).
        :return:
        """
        self.pix = QPixmap(self.color_path)
        self.setPixmap(self.pix)

    def set_accepts_drops(self, state: bool):
        """
        Method sets accepts drops.
        :param state: True or False
        """
        self.setAcceptDrops(state)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """
        Method checks if all dragged files have valide extensions.
        If the file extensions are valid, the drop zone changes color.
        :param event:
        :return:
        """
        if event.mimeData().hasUrls():
            file_paths = [str(url.toLocalFile()) for url in event.mimeData().urls()]
            if all(self.validator.is_valid(path) for path in file_paths):
                event.acceptProposedAction()
                self.set_image_color()
            else:
                event.ignore()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragEnterEvent):
        """
        Method handles the leave event. Drop zone is reset.
        :param event:
        :return:
        """
        self.set_image_grayscale()

    def dropEvent(self, event: QDropEvent):
        """
        Method handles dropped images. File paths are gathered and emmitted as a list.
        :param event:
        :return:
        """
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            file_paths = [url.toLocalFile() for url in urls]
            # emit the file path list
            self.file_path_list_signal.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()