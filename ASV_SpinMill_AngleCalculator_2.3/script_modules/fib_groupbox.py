"""
Module handles the elements in the FIB group box.
"""
from PySide6.QtWidgets import (QGroupBox, QGridLayout, QLabel, QSpinBox,
                               QDoubleSpinBox)
from PySide6.QtCore import Qt, Signal
from script_modules.app_styles import AppStyles
from script_modules.fib_geometry_calculator import FIBGeometryCalculator


class FIBGroupBox(QGroupBox):

    values_changed: Signal = Signal(dict)  # geometry dict with all plot data

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(AppStyles.GroupBox.default())
        # create widgets
        self._create_widgets()
        # set up the layout
        self._setup_layout()
        # connect signals
        self._connect_signals()
        # perform initial calculation
        self._update_calculations()

    def _create_widgets(self):
        # target milling angle
        self.target_milling_angle_label = QLabel("Target Milling Angle (deg.)")
        self.target_milling_angle_label.setToolTip(AppStyles.AppToolTips.TARGET_MILLING_ANGLE_LABEL)
        self.target_milling_angle_label.setStyleSheet(AppStyles.Label.default())
        self.target_milling_angle_spinbox = QDoubleSpinBox()
        self.target_milling_angle_spinbox.setDecimals(1)
        self.target_milling_angle_spinbox.setRange(0.1, 90.0)
        self.target_milling_angle_spinbox.setSingleStep(0.1)
        self.target_milling_angle_spinbox.setValue(4.0)
        self.target_milling_angle_spinbox.setFixedWidth(100)
        self.target_milling_angle_spinbox.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.target_milling_angle_spinbox.setStyleSheet(AppStyles.SpinBox.default())
        # AOI diameter
        self.aoi_diameter_label = QLabel("AOI Diameter (µm)")
        self.aoi_diameter_label.setToolTip(AppStyles.AppToolTips.AOI_DIAMETER_LABEL)
        self.aoi_diameter_label.setStyleSheet(AppStyles.Label.default())
        self.aoi_diameter_spinbox = QSpinBox()
        self.aoi_diameter_spinbox.setRange(50, 2000)
        self.aoi_diameter_spinbox.setSingleStep(5)
        self.aoi_diameter_spinbox.setValue(800)
        self.aoi_diameter_spinbox.setFixedWidth(100)
        self.aoi_diameter_spinbox.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.aoi_diameter_spinbox.setStyleSheet(AppStyles.SpinBox.default())
        # measured ellipse height
        self.measured_ellipse_height_label = QLabel("Measured Ellipse Height (µm)")
        self.measured_ellipse_height_label.setToolTip(AppStyles.AppToolTips.MEASURED_HEIGHT_ELLIPSE_LABEL)
        self.measured_ellipse_height_label.setStyleSheet(AppStyles.Label.default())
        self.measured_ellipse_height_spinbox = QDoubleSpinBox()
        self.measured_ellipse_height_spinbox.setDecimals(1)
        self.measured_ellipse_height_spinbox.setRange(0.1, self.aoi_diameter_spinbox.value() - 0.1)
        self.measured_ellipse_height_spinbox.setSingleStep(0.1)
        self.measured_ellipse_height_spinbox.setValue(55.8)
        self.measured_ellipse_height_spinbox.setFixedWidth(100)
        self.measured_ellipse_height_spinbox.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.measured_ellipse_height_spinbox.setStyleSheet(AppStyles.SpinBox.default())
        # calculated milling angle
        self.calculated_milling_angle_label = QLabel("Calculated Milling Angle (deg.)")
        self.calculated_milling_angle_label.setStyleSheet(AppStyles.Label.default())
        self.calculated_milling_angle_result = QLabel("--")
        self.calculated_milling_angle_result.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.calculated_milling_angle_result.setStyleSheet(AppStyles.Label.result())
        # tilt stage by
        self.tilt_stage_by_label = QLabel("Tilt Stage By (deg.)")
        self.tilt_stage_by_label.setStyleSheet(AppStyles.Label.default())
        self.tilt_stage_by_result = QLabel("--")
        self.tilt_stage_by_result.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.tilt_stage_by_result.setStyleSheet(AppStyles.Label.result())

    def _connect_signals(self):
        """Connect spinbox signals to update calculations."""
        self.aoi_diameter_spinbox.valueChanged.connect(self._update_ellipse_height_range)
        self.aoi_diameter_spinbox.valueChanged.connect(self._update_calculations)
        self.measured_ellipse_height_spinbox.valueChanged.connect(self._update_calculations)
        self.target_milling_angle_spinbox.valueChanged.connect(self._update_calculations)

    def _update_ellipse_height_range(self, new_diameter):
        current_value = self.measured_ellipse_height_spinbox.value()
        new_max = new_diameter - 0.1
        self.measured_ellipse_height_spinbox.setMaximum(new_max)
        if current_value > new_max:
            self.measured_ellipse_height_spinbox.setValue(new_max)

    def _update_calculations(self):
        """Recalculate milling angle and stage tilt."""
        diameter = self.aoi_diameter_spinbox.value()
        measured_minor = self.measured_ellipse_height_spinbox.value()
        target_angle = self.target_milling_angle_spinbox.value()
        # Calculate geometry
        geometry = FIBGeometryCalculator.calculate_milling_geometry(
            diameter=diameter,
            measured_minor=measured_minor
        )
        # Update calculated angle display
        calculated_angle = geometry['plane_angle']
        self.calculated_milling_angle_result.setText(f"{calculated_angle:.2f}")
        # Calculate and update stage tilt
        stage_tilt = FIBGeometryCalculator.calculate_stage_tilt(
            target_angle, calculated_angle
        )
        self.tilt_stage_by_result.setText(f"{stage_tilt:.2f}")
        # Emit geometry dict with everything the plots need
        geometry['diameter'] = diameter
        geometry['measured_minor'] = measured_minor
        self.values_changed.emit(geometry)

    def _setup_layout(self):
        layout = QGridLayout()
        # target milling angle
        layout.addWidget(self.target_milling_angle_label, 0, 0)
        layout.addWidget(self.target_milling_angle_spinbox, 0, 1)
        # AOI diameter
        layout.addWidget(self.aoi_diameter_label, 1, 0)
        layout.addWidget(self.aoi_diameter_spinbox, 1, 1)
        # measured ellipse height
        layout.addWidget(self.measured_ellipse_height_label, 2, 0)
        layout.addWidget(self.measured_ellipse_height_spinbox, 2, 1)
        # spacer row between inputs and results
        layout.setRowMinimumHeight(3, 16)
        # calculated milling angle
        layout.addWidget(self.calculated_milling_angle_label, 4, 0)
        layout.addWidget(self.calculated_milling_angle_result, 4, 1)
        # tilt stage by
        layout.addWidget(self.tilt_stage_by_label, 5, 0)
        layout.addWidget(self.tilt_stage_by_result, 5, 1)
        self.setLayout(layout)