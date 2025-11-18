from PySide6.QtWidgets import QLineEdit, QApplication
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator, QKeyEvent
import sys


class NumericLineEdit(QLineEdit):
    """
    A QLineEdit that behaves like a spinbox with up/down arrow key support.
    Supports both integer and float values with configurable step size and decimal places.
    """

    valueChanged = Signal(float)  # Emits the new value when it changes

    def __init__(self, parent=None):
        super().__init__(parent)

        # Default configuration
        self._value = 0.0
        self._minimum = float('-inf')
        self._maximum = float('inf')
        self._step = 1.0
        self._decimals = 0  # 0 means integer mode
        self._is_float_mode = False

        # Set up validator
        self._setup_validator()

        # Initialize display
        self.setText(self._format_value(self._value))

        # Connect signals
        self.editingFinished.connect(self._on_editing_finished)

    def _setup_validator(self):
        """Configure the appropriate validator based on integer or float mode."""
        if self._is_float_mode:
            validator = QDoubleValidator(self._minimum, self._maximum, self._decimals, self)
            validator.setNotation(QDoubleValidator.StandardNotation)
        else:
            # Handle infinity values for integer validator
            min_val = int(self._minimum) if self._minimum != float('-inf') else -2147483648
            max_val = int(self._maximum) if self._maximum != float('inf') else 2147483647
            validator = QIntValidator(min_val, max_val, self)

        self.setValidator(validator)

    def _format_value(self, value):
        """Format the value according to decimal places."""
        if self._is_float_mode:
            return f"{value:.{self._decimals}f}"
        else:
            return str(int(value))

    def _clamp_value(self, value):
        """Ensure value is within min/max bounds."""
        return max(self._minimum, min(self._maximum, value))

    def keyPressEvent(self, event: QKeyEvent):
        """Handle up/down arrow keys to increment/decrement value."""
        if event.key() == Qt.Key_Up:
            self._increment_value()
            event.accept()
        elif event.key() == Qt.Key_Down:
            self._decrement_value()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _increment_value(self):
        """Increase the value by the step amount."""
        new_value = self._clamp_value(self._value + self._step)
        self.setValue(new_value)

    def _decrement_value(self):
        """Decrease the value by the step amount."""
        new_value = self._clamp_value(self._value - self._step)
        self.setValue(new_value)

    def _on_editing_finished(self):
        """Handle when user finishes editing the text."""
        text = self.text()
        try:
            if self._is_float_mode:
                value = float(text)
            else:
                value = int(float(text))  # Allow float input but convert to int

            self.setValue(value)
        except ValueError:
            # Reset to current value if invalid input
            self.setText(self._format_value(self._value))

    # Public API methods

    def setValue(self, value):
        """Set the current value."""
        clamped_value = self._clamp_value(float(value))

        if clamped_value != self._value:
            self._value = clamped_value
            self.setText(self._format_value(self._value))
            self.valueChanged.emit(self._value)
        else:
            # Update display even if value didn't change (for formatting)
            self.setText(self._format_value(self._value))

    def value(self):
        """Get the current value."""
        return self._value

    def setMinimum(self, minimum):
        """Set the minimum allowed value."""
        self._minimum = float(minimum)
        self._setup_validator()
        self.setValue(self._value)  # Re-clamp if needed

    def minimum(self):
        """Get the minimum allowed value."""
        return self._minimum

    def setMaximum(self, maximum):
        """Set the maximum allowed value."""
        self._maximum = float(maximum)
        self._setup_validator()
        self.setValue(self._value)  # Re-clamp if needed

    def maximum(self):
        """Get the maximum allowed value."""
        return self._maximum

    def setRange(self, minimum, maximum):
        """Set both minimum and maximum values."""
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._setup_validator()
        self.setValue(self._value)  # Re-clamp if needed

    def setSingleStep(self, step):
        """Set the step size for increment/decrement."""
        self._step = float(step)

    def singleStep(self):
        """Get the step size."""
        return self._step

    def setDecimals(self, decimals):
        """Set the number of decimal places (0 for integer mode)."""
        self._decimals = max(0, int(decimals))
        self._is_float_mode = self._decimals > 0
        self._setup_validator()
        self.setText(self._format_value(self._value))

    def decimals(self):
        """Get the number of decimal places."""
        return self._decimals


# Demo application
if __name__ == '__main__':
    app = QApplication(sys.argv)

    from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout

    window = QWidget()
    window.setWindowTitle('NumericLineEdit Demo')
    layout = QVBoxLayout(window)

    # Integer example
    int_layout = QHBoxLayout()
    int_label = QLabel('Integer (0-100, step 5):')
    int_edit = NumericLineEdit()
    int_edit.setRange(0, 100)
    int_edit.setSingleStep(5)
    int_edit.setValue(50)
    int_edit.setDecimals(0)  # Integer mode
    int_result = QLabel('Value: 50')
    int_edit.valueChanged.connect(lambda v: int_result.setText(f'Value: {int(v)}'))
    int_layout.addWidget(int_label)
    int_layout.addWidget(int_edit)
    int_layout.addWidget(int_result)
    layout.addLayout(int_layout)

    # Float example with 2 decimals
    float2_layout = QHBoxLayout()
    float2_label = QLabel('Float (0-10, step 0.25, 2 decimals):')
    float2_edit = NumericLineEdit()
    float2_edit.setRange(0, 10)
    float2_edit.setSingleStep(0.25)
    float2_edit.setValue(5.0)
    float2_edit.setDecimals(2)
    float2_result = QLabel('Value: 5.00')
    float2_edit.valueChanged.connect(lambda v: float2_result.setText(f'Value: {v:.2f}'))
    float2_layout.addWidget(float2_label)
    float2_layout.addWidget(float2_edit)
    float2_layout.addWidget(float2_result)
    layout.addLayout(float2_layout)

    # Float example with 4 decimals
    float4_layout = QHBoxLayout()
    float4_label = QLabel('Float (-1 to 1, step 0.0001, 4 decimals):')
    float4_edit = NumericLineEdit()
    float4_edit.setRange(-1, 1)
    float4_edit.setSingleStep(0.0001)
    float4_edit.setValue(0.0)
    float4_edit.setDecimals(4)
    float4_result = QLabel('Value: 0.0000')
    float4_edit.valueChanged.connect(lambda v: float4_result.setText(f'Value: {v:.4f}'))
    float4_layout.addWidget(float4_label)
    float4_layout.addWidget(float4_edit)
    float4_layout.addWidget(float4_result)
    layout.addLayout(float4_layout)

    # Instructions
    instructions = QLabel('\nUse Up/Down arrow keys to adjust values\nOr type directly')
    instructions.setStyleSheet('color: gray; font-style: italic;')
    layout.addWidget(instructions)

    window.show()
    sys.exit(app.exec())