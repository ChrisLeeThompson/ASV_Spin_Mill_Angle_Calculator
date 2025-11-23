"""
Module handles the elements in the SEM group box.
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel)
from PySide6.QtCore import Qt, Slot
from script_modules.image_drop_widget import ImageDropLabel, ImageFileValidator
from script_modules.fib_reference_image_parser import FIBImageParser
from script_modules.script_styles import AppStyles


class SEMGroupBox(QGroupBox):

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.ClickFocus)
        # image label asset paths
        base_path = Path(__file__).parent.parent / "script_assets"
        self.color_path = base_path / "catbug_color_2.png"
        self.grayscale_path = base_path / "catbug_grayscale_2.png"
        # default status label text
        self.default_status_label_text = ("Drag and drop .png milling angle reference images onto Catbug to calculate SEM angles.\n"
                                          "Reference images can be found in the ASV SpinMillPositioningService directory.")
        # create FIB mill angle reference image parser
        self.fib_image_parser = FIBImageParser(file_path_list=[])
        # create widgets
        self._create_widgets()
        # set up layout
        self._setup_layout()
        # connect signals
        self._connect_signals()

    def _create_widgets(self):
        # image drop label
        self.image_drop_label = ImageDropLabel(color_path=self.color_path, grayscale_path=self.grayscale_path,
                                               validator=ImageFileValidator(allowed_extension=[".png"]))
        # calculated angle labels
        self.calculated_rotation_angle_label = QLabel("Calculated Rotation Angle (deg.)")
        self.calculated_rotation_angle_label.setStyleSheet(AppStyles.Label.default())
        self.calculated_rotation_angle_result = QLabel("--")
        self.calculated_rotation_angle_result.setStyleSheet(AppStyles.Label.result())
        self.calculated_tilt_angle_label = QLabel("Calculated Tilt Angle (deg.)")
        self.calculated_tilt_angle_label.setStyleSheet(AppStyles.Label.default())
        self.calculated_tilt_angle_result = QLabel("--")
        self.calculated_tilt_angle_result.setStyleSheet(AppStyles.Label.result())
        # status label
        self.status_label = QLabel(self.default_status_label_text)
        self.status_label.setStyleSheet(AppStyles.Label.default())

    def _setup_layout(self):
        # main layout
        main_layout = QVBoxLayout()
        # top layout containing image label and calculated angle gridlayout
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        # calculated angle layout
        calculated_angle_layout = QGridLayout()
        calculated_angle_layout.addWidget(self.calculated_rotation_angle_label, 0, 0, Qt.AlignmentFlag.AlignLeft)
        calculated_angle_layout.addWidget(self.calculated_rotation_angle_result, 0, 1, Qt.AlignmentFlag.AlignRight)
        calculated_angle_layout.addWidget(self.calculated_tilt_angle_label, 1, 0, Qt.AlignmentFlag.AlignLeft)
        calculated_angle_layout.addWidget(self.calculated_tilt_angle_result, 1, 1, Qt.AlignmentFlag.AlignRight)
        calculated_angle_layout.setRowStretch(2, 1)
        calculated_angle_layout.setContentsMargins(10, 4, 4, 4)
        # populate top layout
        top_layout.addWidget(self.image_drop_label)
        top_layout.addLayout(calculated_angle_layout)
        # populate main layout
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addStretch()
        # set main layout
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.image_drop_label.file_path_list_signal.connect(self._on_files_dropped)
        self.fib_image_parser.error_signal.connect(self._on_fib_image_parser_error_port)

    @Slot(list)
    def _on_files_dropped(self, file_path_list: list):
        # log dropped and sorted file paths
        sorted_file_path_list = sorted(file_path_list)
        for file_path in sorted_file_path_list:
            logging.info(f"dropped file path: {file_path}")
        # send file path list to _get_image_metadata
        self._get_image_metadata(sorted_file_path_list)
        # reset image drop label when complete
        self.image_drop_label.set_image_grayscale()

    @Slot(str)
    def _on_fib_image_parser_error_port(self, signal: str):
        self.status_label.setText(signal)

    def _get_image_metadata(self, file_path_list: list):
        reference_image_metadata = self.fib_image_parser.gather_metadata_from_image(file_path_list)
        if reference_image_metadata:
            for key, value in reference_image_metadata.items():
                logging.info(f"grand metadata: {key}, {value}")
        else:
            return
