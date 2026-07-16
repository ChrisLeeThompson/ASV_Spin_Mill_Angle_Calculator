# This Python file uses the following encoding: utf-8
"""
ASV Spin Mill Angle Calculator
.
A PySide6/QML desktop UI that assists setup of Thermo Fisher Auto Slice
And View (ASV) spin milling on the Hydra Bio dual-beam FIB-SEM
(AutoScript >= 4.13).
.
Authors: Chris Thompson (GitHub: ChrisLeeThompson) and Anthropic's Claude
.
Copyright (c) 2026 Christopher Thompson.
Released under the MIT License.
.
Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:
.
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from asv_spin_mill_angle_calc import __version__
from asv_spin_mill_angle_calc.app_controller import AppController
from asv_spin_mill_angle_calc.frame_image_provider import FrameImageProvider
from asv_spin_mill_angle_calc.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    setup_logging()
    logger.info("Starting ASV Spin Mill Angle Calculator v%s", __version__)

    base_dir = Path(__file__).resolve().parent

    app = QGuiApplication(argv)
    app.setOrganizationName("TFS_AutoScript")
    app.setApplicationName("TFS_AutoScript_ASVSpinMillAngleCalculator_v3")

    # Apply the Qt Quick Controls "Universal" style before the engine loads,
    # so the ApplicationWindow's Universal.* theme bindings in main.qml
    # (sourced from Config/AppConfig.qml) resolve on the first paint.
    QQuickStyle.setStyle("Universal")

    # OS window / taskbar icon. The same asset is exposed to QML as
    # AppConfig.catbugWaitingIcon, so the Python window icon and any in-window
    # catbug graphics reference a single file on disk.
    app.setWindowIcon(
        QIcon(str(base_dir / "qml_resources" / "assets" / "catbug_waiting_color.svg"))
    )

    engine = QQmlApplicationEngine()
    engine.quit.connect(app.quit)
    engine.addImportPath(str(base_dir / "qml_resources"))

    # The FIB live-view image provider: the alignment backend writes frames
    # into it; QML reads them as image://fibAlignment/... . Constructed
    # before the controller (which keeps the writing reference) and handed
    # to the engine, which takes ownership on registration.
    frame_provider = FrameImageProvider()

    # Expose the root controller to QML before loading, so the pages' bindings
    # to `appController.*` resolve on first evaluation.
    app_controller = AppController(frame_provider=frame_provider)
    engine.rootContext().setContextProperty("appController", app_controller)
    engine.addImageProvider("fibAlignment", frame_provider)

    # Clean microscope disconnect at quit — including the connect-thread
    # race (see MicroscopeController.shutdown).
    app.aboutToQuit.connect(app_controller.shutdown)

    engine.load(str(base_dir / "qml_resources" / "main.qml"))
    if not engine.rootObjects():
        logger.error("Failed to load QML file")
        return -1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())