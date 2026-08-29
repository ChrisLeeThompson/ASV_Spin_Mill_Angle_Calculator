# ASV Spin Mill Angle Calculator 3

A PySide6/QML desktop utility that assists setup of Thermo Fisher Auto Slice And View (ASV) spin milling on the Hydra Bio dual-beam FIB-SEM (AutoScript 4.13 or newer).

## Running

Launch the main module from the app folder:

```
python asv_spin_mill_angle_calculator.py
```

To open the UI without a microscope connection, set the simulation environment variable:

```
set ASV_SIMULATED_MICROSCOPE=1
python asv_spin_mill_angle_calculator.py
```

In simulation mode the UI is fully navigable but cannot control a microscope.

## Requirements

The application runs inside the AutoScript Python environment, or standalone with the dependencies in `requirements.txt` (PySide6, NumPy, OpenCV). Controlling a microscope requires AutoScript; simulation mode does not.

## Notes

- Settings are stored in the Windows registry and persist between sessions and updates.
- The Catbug artwork in `qml_resources/assets/` is not covered by the MIT license. See `LICENSE`.
- PySide6 (Qt for Python) is licensed under the LGPLv3 and is used as an unmodified runtime dependency installed from PyPI; it is not distributed with this source.
