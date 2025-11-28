"""
Module creates the SEM tab widget containing input controls and visualizations.
"""
import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Slot
from script_modules.sem_groupbox import SEMGroupBox
from script_modules.sem_plot_groupbox import SEMPlotGroupBox
from script_modules.script_styles import AppStyles


class SEMTabWidget(QWidget):
    """Widget containing the complete SEM workflow with inputs and visualizations."""

    def __init__(self):
        super().__init__()
        self._create_components()
        self._setup_layout()
        self._connect_signals()

    def _create_components(self):
        self.sem_groupbox = SEMGroupBox()
        self.sem_groupbox.setStyleSheet(AppStyles.GroupBox.default())
        self.sem_plot_groupbox = SEMPlotGroupBox()
        self.sem_plot_groupbox.setStyleSheet(AppStyles.GroupBox.plot_gb())

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.sem_groupbox)
        main_layout.addWidget(self.sem_plot_groupbox)
        # set layout
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.sem_groupbox.calculated_angles.connect(self._on_angles_calculated)

    @Slot(dict, dict)
    def _on_angles_calculated(self, current_orientation, corrected_orientation):
        """
        Handle the angles_calculated signal and update the 3D plot.
        Args:
            current_orientation: Dict with 'current_normal', 'current_u', 'current_v', 'deviation_deg'
            corrected_orientation: Dict with 'current_normal', 'current_u', 'current_v', 'deviation_deg'
        """
        logging.info("Updating SEM alignment plot...")

        # Extract vectors from orientation dicts
        current_normal = current_orientation['current_normal']
        current_u = current_orientation['current_u']
        current_v = current_orientation['current_v']

        corrected_normal = corrected_orientation['current_normal']
        corrected_u = corrected_orientation['current_u']
        corrected_v = corrected_orientation['current_v']

        # Update the plot
        self.sem_plot_groupbox.update_plot(
            current_normal=current_normal,
            current_u=current_u,
            current_v=current_v,
            corrected_normal=corrected_normal,
            corrected_u=corrected_u,
            corrected_v=corrected_v
        )
        logging.info(f"Plot updated. Current deviation: {current_orientation['deviation_deg']:.2f}°, "
                     f"Corrected deviation: {corrected_orientation['deviation_deg']:.2f}°")

