"""
Module creates the SEM tab widget containing input controls and visualizations.
"""
import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from script_modules.sem_groupbox import SEMGroupBox
from script_modules.script_styles import AppStyles


class SEMTabWidget(QWidget):
    """Widget containing the complete SEM workflow with inputs and visualizations."""

    def __init__(self):
        super().__init__()
        self._create_components()
        self._setup_layout()

    def _create_components(self):
        self.sem_groupbox = SEMGroupBox()
        self.sem_groupbox.setStyleSheet(AppStyles.GroupBox.default())

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.sem_groupbox)
        # set layout
        self.setLayout(main_layout)
