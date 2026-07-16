"""Frame image provider for the Position Alignment live view.

Holds the single most-recent ``QImage`` (latest-frame-wins). The alignment
worker writes from its thread; QML's render thread reads via
``requestImage`` — the swap is guarded by a lock so a half-written frame
is never read. Ported from the sibling Direct Adjustments Analyzer's
``backend/image_provider.py``.

Registered on the QML engine as ``"fibAlignment"`` by the entry point;
QML consumes it as ``Image { source: "image://fibAlignment/frame?seq=N" }``
where the ``seq`` query string (a controller property bump) forces the
``Image`` element to re-request — the provider itself ignores the id.
"""
from __future__ import annotations

import threading

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


def numpy_to_qimage(array: np.ndarray) -> QImage:
    """Convert a 2D grayscale numpy array to a QImage.

    Handles 8- and 16-bit grayscale (the depths AutoScript produces).
    The result is ``.copy()``-d so it owns its memory and the source
    array can be freed by the worker.
    """
    array = np.ascontiguousarray(array)
    height, width = array.shape[:2]

    if array.dtype == np.uint8:
        image_format = QImage.Format.Format_Grayscale8
        bytes_per_line = width
    elif array.dtype == np.uint16:
        image_format = QImage.Format.Format_Grayscale16
        bytes_per_line = width * 2
    else:
        # Defensive fallback: normalize anything unexpected to 8-bit.
        lo, hi = float(array.min()), float(array.max())
        scaled = (array.astype(np.float32) - lo) / (hi - lo + 1e-9) * 255.0
        array = np.ascontiguousarray(scaled.astype(np.uint8))
        image_format = QImage.Format.Format_Grayscale8
        bytes_per_line = width

    image = QImage(array.data, width, height, bytes_per_line, image_format)
    return image.copy()


class FrameImageProvider(QQuickImageProvider):
    """Lock-guarded latest-frame-wins image provider."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._image = QImage()
        self._lock = threading.Lock()

    def set_image(self, image: QImage) -> None:
        """Store the latest frame (called from the worker thread)."""
        with self._lock:
            self._image = image

    def requestImage(self, image_id, size, requested_size) -> QImage:
        """Return the latest frame (called from QML's render thread)."""
        with self._lock:
            return QImage(self._image)
