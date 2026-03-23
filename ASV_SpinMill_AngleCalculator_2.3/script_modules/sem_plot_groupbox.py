"""
Module handles the SEM visualization group box.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel)
from PySide6.QtCore import Qt
from script_modules.three_dim_plot_groupbox import ThreeDimCanvas
from script_modules.app_styles import AppStyles


class SEMPlotGroupBox(QGroupBox):

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.ClickFocus)
        self.setStyleSheet(AppStyles.GroupBox.plot())
        # create components
        self._create_components()
        # set component styles
        self._set_component_styles()
        # set up layout
        self._setup_layout()
        # connect signals
        self._connect_signals()

    def _create_components(self):
        # create plot canvas
        self.canvas = ThreeDimCanvas(parent=self, width=10, height=10, dpi=100)
        # create legend labels for rotation plot
        self.legend_sem_line = QLabel("■ ")
        self.legend_sem = QLabel("SEM")
        self.legend_fib_line = QLabel("■ ")
        self.legend_fib = QLabel("FIB")
        self.legend_current_line = QLabel("■ ")
        self.legend_current = QLabel("Current Plane")
        self.legend_corrected_line = QLabel("■ ")
        self.legend_corrected = QLabel("Corrected Plane")
        # create view buttons
        self.default_button = QPushButton("Default View")
        self.sem_button = QPushButton("SEM View")

    def _set_component_styles(self):
        # legend styles
        self.legend_sem_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_SEM_COLOR}; font-size: 16px;")
        self.legend_sem.setStyleSheet(AppStyles.Label.legend())
        self.legend_fib_line.setStyleSheet(f"color: {AppStyles.Colors.THREE_DIM_FIB_COLOR}; font-size: 16px;")
        self.legend_fib.setStyleSheet(AppStyles.Label.legend())
        self.legend_current_line.setStyleSheet("color: #FF6B6B; font-size: 16px;")  # red-ish
        self.legend_current.setStyleSheet(AppStyles.Label.legend())
        self.legend_corrected_line.setStyleSheet("color: #4ECDC4; font-size: 16px;")  # teal-ish
        self.legend_corrected.setStyleSheet(AppStyles.Label.legend())
        # button styles
        self.default_button.setStyleSheet(AppStyles.Button.default())
        self.sem_button.setStyleSheet(AppStyles.Button.default())

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.canvas)
        # button layout
        button_layout = QHBoxLayout()
        # add legend and buttons
        button_layout.addWidget(self.legend_sem_line)
        button_layout.addWidget(self.legend_sem)
        button_layout.addWidget(self.legend_fib_line)
        button_layout.addWidget(self.legend_fib)
        button_layout.addWidget(self.legend_current_line)
        button_layout.addWidget(self.legend_current)
        button_layout.addWidget(self.legend_corrected_line)
        button_layout.addWidget(self.legend_corrected)
        button_layout.addStretch()
        button_layout.addWidget(self.sem_button)
        # add button layout to main layout
        main_layout.addLayout(button_layout)
        # set layout
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.sem_button.clicked.connect(self.canvas.view_sem)

    def update_plot(self, current_normal, current_u, current_v,
                    corrected_normal, corrected_u, corrected_v):
        """
        Update the 3D plot with current and corrected plane orientations.

        Args:
            current_normal: Current plane normal vector
            current_u: Current U basis vector
            current_v: Current V basis vector
            corrected_normal: Corrected plane normal vector
            corrected_u: Corrected U basis vector
            corrected_v: Corrected V basis vector
        """
        self.canvas.plot_sem_alignment(
            current_normal=current_normal,
            current_u=current_u,
            current_v=current_v,
            corrected_normal=corrected_normal,
            corrected_u=corrected_u,
            corrected_v=corrected_v
        )