# ASV Spin Mill Angle Calculator

<!-- Full documentation: https://<site>/scripts/asv_spin_mill_angle_calculator/ (enable this link when the site is live) -->

A PySide6/QML desktop utility that assists setup of Thermo Scientific Auto Slice and View (ASV) spin milling on the Hydra Bio plasma FIB-SEM. It calculates the stage tilt and rotation needed for a target milling angle, analyzes FIB spin-mill position images, and can align a position automatically through the Thermo Scientific AutoScript SDK.

## Features

- **FIB Angle Calculator** page for spin-mill geometry: enter the target milling angle and related inputs, read off the stage angles.
- **SEM Angle Calc** page that reads the metadata of a set of FIB spin-mill position images and fits the stage tilt and rotation for the target milling angle.
- **Position Alignment** automation that connects to the microscope, detects the milled fiducial ellipse in grazing-incidence FIB images, and iterates the stage to the target angle with Start, Stop, and Confirm controls.
- **Settings** page for user preferences and alignment tuning, persisted between sessions.
- **Simulation Mode** with a simulated microscope for running the Position Alignment page without hardware; simulated sessions are badged "(sim)" in the UI.

## Requirements

- Python 3.11+
- PySide6 6.7.1+
- NumPy 2.2.5+
- OpenCV 4.8.1+ (`opencv-python`)
- Thermo Scientific AutoScript 4.14+ (required only for the Position Alignment page, which connects to the microscope; the FIB Angle Calc and SEM Angle Calc pages and simulation mode run without it)

Versions are those in the AutoScript 4.14 Python environment, where the script is developed and tested alongside ASV 5.13.

## Installation

1. Download the latest release ZIP from the [Releases page](https://github.com/ChrisLeeThompson/ASV_Spin_Mill_Angle_Calculator/releases).
2. Extract it and copy the script folder to your desired location. Scripts that control a microscope are best installed on the Support PC (SPC) or Microscope PC (MPC).
3. If you run the script with the AutoScript Python environment, no packages need to be installed. Otherwise, install them into a fresh virtual environment with:

   ```
   pip install -r requirements.txt
   ```

   Do not pip-install into the AutoScript environment; it already provides these packages, and pip would replace the vendor OpenCV build.

## Running

Run the main module from the script folder:

```
python asv_spin_mill_angle_calculator.py
```

The script also runs from the AutoScript Python interpreter or AutoScript Runner.

### Simulation Mode

To open the UI with a simulated microscope, set the `ASV_SIMULATED_MICROSCOPE` environment variable before launching:

```
set ASV_SIMULATED_MICROSCOPE=1
python asv_spin_mill_angle_calculator.py
```

In simulation mode the UI is fully navigable but cannot control a microscope. Simulation is never a silent fallback; it is selected only by this variable or by setting `DEV_FORCE_SIMULATION` at the bottom of `asv_spin_mill_angle_calc/alignment_config.py`.

## Updating

Replace the script folder with the new release. Settings are stored in the Windows registry and persist between sessions and updates.

## License

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Christopher Thompson.

The Catbug artwork in `qml_resources/assets/` is not covered by the MIT license; see [LICENSE](LICENSE). PySide6 (Qt for Python) is licensed under the LGPLv3 and is used as an unmodified runtime dependency installed from PyPI; it is not distributed with this source.

## Contact

Developed by Chris Thompson with assistance from Anthropic's Claude. Questions and suggestions are welcome: [@ChrisLeeThompson](https://github.com/ChrisLeeThompson) on GitHub.
