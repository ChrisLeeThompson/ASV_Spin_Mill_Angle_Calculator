"""
Central repository for application styles.
"""


class StyleColors:

    MAIN_BG = "#273945"
    GROUPBOX_GB = "#34454f"
    BUTTON_BG = "#476273"
    BUTTON_HOVER = "#2980b9"
    BUTTON_PRESSED = "#1c5985"
    BUTTON_DISABLED = "#3d5462"
    TEXT_PRIMARY = "#ffffff"
    TEXT_DISABLED = "#808f99"
    INPUT_BG = "#3d5462"
    INPUT_BORDER = "#476273"
    INPUT_FOCUS = "#2980b9"


class StyleDimensions:

    BORDER_RADIUS_LARGE = "8.0px"
    BORDER_RADIUS_SMALL = "4.0px"
    MARGIN = "4px"
    PADDING = "8px"
    FONT_SIZE_NORMAL = "11pt"
    FONT_SIZE_LARGE = "14pt"


class MainWindowStyles:

    @staticmethod
    def window() -> str:
        return f"""
            QMainWindow {{
                background-color: {StyleColors.MAIN_BG};
            }}
        """


class GroupBoxStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QGroupBox {{
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.GROUPBOX_GB};
                padding: {StyleDimensions.PADDING};
                margin: {StyleDimensions.MARGIN};
            }}
        """

    @staticmethod
    def plot_gb() -> str:
        return f"""
            QGroupBox {{
                border: 4px solid {StyleColors.GROUPBOX_GB};
                border-radius: {StyleDimensions.BORDER_RADIUS_LARGE};
                background-color: {StyleColors.MAIN_BG};
                padding: {StyleDimensions.PADDING};
                margin: {StyleDimensions.MARGIN};
            }}
        """


class SpinBoxStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: {StyleColors.GROUPBOX_GB};
                border: 2px solid {StyleColors.INPUT_BORDER};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                color: {StyleColors.TEXT_PRIMARY};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                selection-background-color: {StyleColors.BUTTON_HOVER};
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 2px solid {StyleColors.INPUT_FOCUS};
            }}
            QSpinBox:disabled, QDoubleSpinBox:disabled {{
                background-color: {StyleColors.BUTTON_DISABLED};
                color: {StyleColors.TEXT_DISABLED};
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                width: 0px;
                height: 0px;
                border: none;
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                width: 0px;
                height: 0px;
                border: none;
            }}
        """


class LabelStyles:

    @staticmethod
    def default() -> str:
        return f"""
            QLabel {{
                color: {StyleColors.TEXT_PRIMARY};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                background: transparent;
            }}
            QToolTip {{
                background-color: {StyleColors.BUTTON_BG};
                color: {StyleColors.TEXT_PRIMARY};
                /*border: 1px solid #ffffff;*/
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
            }}
        """

    @staticmethod
    def result() -> str:
        return f"""
            QLabel {{
                color: {StyleColors.TEXT_PRIMARY};
                font-size: {StyleDimensions.FONT_SIZE_NORMAL};
                background-color: {StyleColors.GROUPBOX_GB};
                border: 2px solid {StyleColors.GROUPBOX_GB};
                border-radius: {StyleDimensions.BORDER_RADIUS_SMALL};
                padding: {StyleDimensions.PADDING};
            }}
        """


class AppStyles:

    Colors = StyleColors
    Dimensions = StyleDimensions
    MainWindow = MainWindowStyles
    GroupBox = GroupBoxStyles
    SpinBox = SpinBoxStyles
    Label = LabelStyles
