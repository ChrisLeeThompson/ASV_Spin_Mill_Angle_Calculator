"""
Module handles the elements in the SEM group box.
"""
import logging
import numpy as np
from pathlib import Path
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel, QDoubleSpinBox)
from PySide6.QtCore import Qt, Signal, Slot
from script_modules.image_drop_widget import ImageDropLabel, ImageFileValidator
from script_modules.fib_reference_image_parser import FIBImageParser
from script_modules.sem_geometry_calculator import SEMGeometryCalculator
from script_modules.app_styles import AppStyles


class SEMGroupBox(QGroupBox):

    calculated_angles: Signal = Signal(dict, dict)  # (current_orientation, corrected_orientation)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.ClickFocus)
        # image label asset paths
        base_path = Path(__file__).parent.parent / "script_assets"
        self.color_path = base_path / "catbug_color_2.png"
        self.grayscale_path = base_path / "catbug_grayscale_2.png"
        # default status label text
        self.default_status_label_text = ("Drag and drop a .png milling angle reference image onto Catbug to calculate SEM angles.\n"
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
        # milling angle spinbox and label
        self.milling_angle_label = QLabel("Milling Angle (deg.)")
        self.milling_angle_label_spinbox = QDoubleSpinBox()
        self.milling_angle_label_spinbox.setRange(0.1, 90.0)
        self.milling_angle_label_spinbox.setSingleStep(0.1)
        self.milling_angle_label_spinbox.setValue(4.0)
        self.milling_angle_label_spinbox.setFixedWidth(100)
        self.milling_angle_label.setStyleSheet(AppStyles.Label.default())
        self.milling_angle_label_spinbox.setStyleSheet(AppStyles.SpinBox.default())
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
        # grid angle layout
        grid_layout = QGridLayout()
        grid_layout.addWidget(self.milling_angle_label, 0, 0, Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(self.milling_angle_label_spinbox, 0, 1, Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(self.calculated_rotation_angle_label, 1, 0, Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(self.calculated_rotation_angle_result, 1, 1, Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(self.calculated_tilt_angle_label, 2, 0, Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(self.calculated_tilt_angle_result, 2, 1, Qt.AlignmentFlag.AlignRight)
        grid_layout.setContentsMargins(10, 4, 4, 4)
        # populate top layout
        top_layout.addWidget(self.image_drop_label)
        top_layout.addLayout(grid_layout)
        # populate main layout
        main_layout.addLayout(top_layout)
        main_layout.addWidget(QLabel(""))
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
        """
        Extract metadata from FIB images and calculate SEM alignment angles.
        Uses user-input milling angle. AOI width is not needed for these calculations.
        """
        reference_image_metadata = self.fib_image_parser.gather_metadata_from_image(file_path_list)
        if not reference_image_metadata:
            return

        # log metadata
        for key, value in reference_image_metadata.items():
            logging.info(f"fib metadata: {key}, {value}")

        try:
            # Extract metadata from first image (all images should have same stage position)
            # The structure is: {filename: {metadata_dict}}
            first_image_data = next(iter(reference_image_metadata.values()))

            # Extract required values from metadata
            stage_r_rad = first_image_data.get('Stage R', 0.0)  # radians
            stage_t_rad = first_image_data.get('Stage T', 0.0)  # radians
            scan_rotation_rad = first_image_data.get('Scan Rotation', 0.0)  # radians

            # Use milling angle from user input (independent of FIB tab)
            milling_angle_deg = self.milling_angle_label_spinbox.value()

            logging.info(f"Stage R: {stage_r_rad} rad ({np.degrees(stage_r_rad):.2f}°)")
            logging.info(f"Stage T: {stage_t_rad} rad ({np.degrees(stage_t_rad):.2f}°)")
            logging.info(f"Scan Rotation: {scan_rotation_rad} rad ({np.degrees(scan_rotation_rad):.2f}°)")
            logging.info(f"Using milling angle: {milling_angle_deg}°")

            # Step 1: Calculate true sample normal from FIB metadata
            sample_normal = SEMGeometryCalculator.calculate_sample_normal_from_fib_metadata(
                stage_r_rad, stage_t_rad, scan_rotation_rad, milling_angle_deg
            )
            logging.info(f"Calculated sample normal: {sample_normal}")

            # Step 2: Calculate current orientation
            current_orientation = SEMGeometryCalculator.calculate_current_orientation(
                sample_normal, stage_r_rad, stage_t_rad, scan_rotation_rad
            )
            logging.info(f"Current deviation from SEM: {current_orientation['deviation_deg']:.2f}°")

            # Step 3: Calculate SEM alignment corrections
            corrections = SEMGeometryCalculator.calculate_sem_alignment_corrections(
                sample_normal, scan_rotation_rad
            )
            logging.info(f"Target Stage R: {corrections['target_r_deg']:.2f}°")
            logging.info(f"Target Stage T: {corrections['target_t_deg']:.2f}°")
            logging.info(f"Final deviation: {corrections['deviation_deg']:.2f}°")

            # Step 4: Calculate corrected orientation (for visualization)
            corrected_orientation = SEMGeometryCalculator.calculate_current_orientation(
                sample_normal,
                corrections['target_r_rad'],
                corrections['target_t_rad'],
                scan_rotation_rad
            )

            # Update result labels with 2 decimal places for 0.01° precision
            self.calculated_rotation_angle_result.setText(f"{corrections['target_r_deg']:.2f}")
            self.calculated_tilt_angle_result.setText(f"{corrections['target_t_deg']:.2f}")

            # Update status
            improvement = current_orientation['deviation_deg'] - corrections['deviation_deg']
            self.status_label.setText(
                f"{Path(file_path_list[-1]).name}\n"
                f"Set Stage R={corrections['target_r_deg']:.2f}°,\n"
                f"T={corrections['target_t_deg']:.2f}° for SEM alignment.\n"
                f"Current deviation: {current_orientation['deviation_deg']:.2f}°\n"
                f"Final deviation: {corrections['deviation_deg']:.2f}°"
            )

            # Emit signal with both orientations for plotting
            self.calculated_angles.emit(current_orientation, corrected_orientation)

        except KeyError as e:
            error_msg = f"Missing metadata key: {e}. Check FIBImageParser output format."
            logging.error(error_msg)
            self.status_label.setText(error_msg)
        except Exception as e:
            error_msg = f"Error calculating SEM alignment: {e}"
            logging.error(error_msg)
            self.status_label.setText(error_msg)