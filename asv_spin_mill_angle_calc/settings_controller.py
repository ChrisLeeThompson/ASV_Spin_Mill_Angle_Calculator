"""User-preference controller, exposed to QML as ``appController.settings``.

Wraps ``QSettings`` and presents each preference as a PySide ``Property``
with a notify signal. QML two-way bindings work because each setter is a no-op
when the incoming value matches the stored value — this breaks the
QML→Python→QML feedback loop that would otherwise occur when a control
echoes a value back to its source.

Every property is persisted on assignment, so user edits survive a restart
without an explicit save step. The default ``QSettings()`` resolves through
the Organization/Application names the entry point sets on the application
object (Windows: the registry); ``settings_factory`` is the test seam for
substituting an INI-file-backed store, so tests need no QApplication.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Property, QObject, QSettings, Signal

from asv_spin_mill_angle_calc.alignment_config import DEFAULT_ALIGNMENT_CONFIG

logger = logging.getLogger(__name__)

# Settings-key namespace for this version of the app. Bumping it (e.g. to
# "v4/") partitions new keys from old ones during a future breaking change
# without forcing a migration. Kept here with the factory defaults below;
# promote them to a shared defaults module when a second consumer appears.
_SCHEMA_PREFIX = "v3/"
_K_SAVE_DEBUG_IMAGES = _SCHEMA_PREFIX + "saveDebugImages"
_K_TILT_TOLERANCE_DEG = _SCHEMA_PREFIX + "tiltToleranceDeg"
_K_LEVEL_TOLERANCE_DEG = _SCHEMA_PREFIX + "levelToleranceDeg"
_K_VERIFY_FRAMES = _SCHEMA_PREFIX + "verifyFrames"
_K_SWEEP_COUNT = _SCHEMA_PREFIX + "sweepCount"

SAVE_DEBUG_IMAGES_DEFAULT = False

# The alignment-tuning defaults are the dataclass's own values, never
# re-typed here: a default that drifted from AlignmentConfig would show
# the operator one number on the Settings page and run another.
TILT_TOLERANCE_DEG_DEFAULT = DEFAULT_ALIGNMENT_CONFIG.tilt_tolerance_deg
LEVEL_TOLERANCE_DEG_DEFAULT = DEFAULT_ALIGNMENT_CONFIG.level_tolerance_deg
VERIFY_FRAMES_DEFAULT = DEFAULT_ALIGNMENT_CONFIG.verify_frames
SWEEP_COUNT_DEFAULT = DEFAULT_ALIGNMENT_CONFIG.sweep_count

# Bounds mirrored from AlignmentConfig.__post_init__. The QML spin boxes
# are the primary guard; these are the second line, so a hand-edited
# registry value cannot push an invalid config into a run. The lower
# tilt bound is the config's own floor — the tolerance can only be
# raised, because anything under the measurement noise oscillates.
TILT_TOLERANCE_DEG_RANGE = (
    DEFAULT_ALIGNMENT_CONFIG.tilt_tolerance_floor_deg, 0.50)
# Leveling must stay at or above the noise floor that latches leveling.
LEVEL_TOLERANCE_DEG_RANGE = (
    DEFAULT_ALIGNMENT_CONFIG.level_noise_floor_deg, 1.00)
VERIFY_FRAMES_RANGE = (1, 7)      # odd only; see _coerce_odd
SWEEP_COUNT_RANGE = (1, 4)


class SettingsController(QObject):
    """User preferences, persisted via :class:`QSettings`."""

    saveDebugImagesChanged = Signal()
    tiltToleranceDegChanged = Signal()
    levelToleranceDegChanged = Signal()
    verifyFramesChanged = Signal()
    sweepCountChanged = Signal()

    def __init__(self, parent: QObject | None = None, *,
                 settings_factory: Callable[[], QSettings] = QSettings,
                 ) -> None:
        super().__init__(parent)
        self._qs = settings_factory()
        # Load current values into private fields without emitting change
        # signals — no consumers are bound yet during construction.
        self._save_debug_images = self._read_bool(
            _K_SAVE_DEBUG_IMAGES, SAVE_DEBUG_IMAGES_DEFAULT)
        self._tilt_tolerance_deg = self._clamp_float(
            self._read_float(_K_TILT_TOLERANCE_DEG,
                             TILT_TOLERANCE_DEG_DEFAULT),
            TILT_TOLERANCE_DEG_RANGE)
        self._level_tolerance_deg = self._clamp_float(
            self._read_float(_K_LEVEL_TOLERANCE_DEG,
                             LEVEL_TOLERANCE_DEG_DEFAULT),
            LEVEL_TOLERANCE_DEG_RANGE)
        self._verify_frames = self._coerce_odd(
            self._read_int(_K_VERIFY_FRAMES, VERIFY_FRAMES_DEFAULT),
            VERIFY_FRAMES_RANGE, VERIFY_FRAMES_DEFAULT)
        self._sweep_count = self._clamp_int(
            self._read_int(_K_SWEEP_COUNT, SWEEP_COUNT_DEFAULT),
            SWEEP_COUNT_RANGE)

    # --- Alignment tuning ---------------------------------------------------
    #
    # Read once at each alignment Start via AppController's
    # tuning_provider, so a mid-run edit applies to the next run. Every
    # value here maps onto one AlignmentConfig field; the controller
    # re-runs the dataclass's own validation and falls back to defaults
    # if a combination is rejected.

    def alignment_overrides(self) -> dict:
        """AlignmentConfig field overrides for the next run.

        Plain method, not a Property: this is the Python-side wiring
        contract (AppController reads it), not something QML binds.
        """
        return {
            "tilt_tolerance_deg": self._tilt_tolerance_deg,
            "level_tolerance_deg": self._level_tolerance_deg,
            "verify_frames": self._verify_frames,
            "sweep_count": self._sweep_count,
        }

    @Property(float, notify=tiltToleranceDegChanged)
    def tiltToleranceDeg(self) -> float:
        return self._tilt_tolerance_deg

    @tiltToleranceDeg.setter
    def tiltToleranceDeg(self, value: float) -> None:
        value = self._clamp_float(float(value), TILT_TOLERANCE_DEG_RANGE)
        if value == self._tilt_tolerance_deg:
            return
        self._tilt_tolerance_deg = value
        self._qs.setValue(_K_TILT_TOLERANCE_DEG, value)
        self.tiltToleranceDegChanged.emit()

    @Property(float, notify=levelToleranceDegChanged)
    def levelToleranceDeg(self) -> float:
        return self._level_tolerance_deg

    @levelToleranceDeg.setter
    def levelToleranceDeg(self, value: float) -> None:
        value = self._clamp_float(float(value), LEVEL_TOLERANCE_DEG_RANGE)
        if value == self._level_tolerance_deg:
            return
        self._level_tolerance_deg = value
        self._qs.setValue(_K_LEVEL_TOLERANCE_DEG, value)
        self.levelToleranceDegChanged.emit()

    @Property(int, notify=verifyFramesChanged)
    def verifyFrames(self) -> int:
        return self._verify_frames

    @verifyFrames.setter
    def verifyFrames(self, value: int) -> None:
        value = self._coerce_odd(int(value), VERIFY_FRAMES_RANGE,
                                 self._verify_frames)
        if value == self._verify_frames:
            return
        self._verify_frames = value
        self._qs.setValue(_K_VERIFY_FRAMES, value)
        self.verifyFramesChanged.emit()

    @Property(int, notify=sweepCountChanged)
    def sweepCount(self) -> int:
        return self._sweep_count

    @sweepCount.setter
    def sweepCount(self, value: int) -> None:
        value = self._clamp_int(int(value), SWEEP_COUNT_RANGE)
        if value == self._sweep_count:
            return
        self._sweep_count = value
        self._qs.setValue(_K_SWEEP_COUNT, value)
        self.sweepCountChanged.emit()

    # --- Save Debug Images --------------------------------------------------
    #
    # Read once at each alignment Start (AppController's debug_dir_provider
    # wiring), so a mid-run toggle affects the next run, never the current
    # one. The ASV_DEBUG_FRAMES_DIR environment variable overrides the
    # resulting directory inside AlignmentSequence.

    @Property(bool, notify=saveDebugImagesChanged)
    def saveDebugImages(self) -> bool:
        return self._save_debug_images

    @saveDebugImages.setter
    def saveDebugImages(self, value: bool) -> None:
        value = bool(value)
        if value == self._save_debug_images:
            return
        self._save_debug_images = value
        self._qs.setValue(_K_SAVE_DEBUG_IMAGES, value)
        self.saveDebugImagesChanged.emit()

    # --- QSettings type-coercion helpers ------------------------------------
    #
    # QSettings on Windows (the deployment target) stores everything through
    # the registry, which round-trips numbers and bools as strings. This
    # normalizes them back to Python types and applies the default when a
    # key is missing or unparseable.

    def _read_bool(self, key: str, default: bool) -> bool:
        raw = self._qs.value(key)
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        # A bool persisted as a plain int (0/1) — accept it. Must come
        # after the bool check: bool is a subclass of int, so testing int
        # first would swallow genuine bools and lose their identity.
        if isinstance(raw, int):
            return bool(raw)
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
        logger.warning(
            "Could not parse bool from QSettings key %r (got %r); "
            "using default %r", key, raw, default)
        return default

    def _read_int(self, key: str, default: int) -> int:
        raw = self._qs.value(key)
        if raw is None:
            return default
        try:
            # str() first so a registry string ("3") and a native int
            # take the same path; float() before int() because a value
            # round-tripped through a double arrives as "3.0", which
            # int() alone rejects.
            return int(float(str(raw)))
        except (TypeError, ValueError):
            logger.warning(
                "Could not parse int from QSettings key %r (got %r); "
                "using default %r", key, raw, default)
            return default

    def _read_float(self, key: str, default: float) -> float:
        raw = self._qs.value(key)
        if raw is None:
            return default
        try:
            return float(str(raw))
        except (TypeError, ValueError):
            logger.warning(
                "Could not parse float from QSettings key %r (got %r); "
                "using default %r", key, raw, default)
            return default

    # --- Range helpers ------------------------------------------------------
    #
    # Applied on both read and write: a stored value predating a range
    # change, or a hand-edited registry entry, must not reach a run.

    @staticmethod
    def _clamp_float(value: float, bounds: tuple) -> float:
        low, high = bounds
        # Round to the spin box's precision so a float that arrived via
        # the QML realValue idiom compares equal to itself on the next
        # write and the no-op guard actually fires.
        return round(min(max(value, low), high), 3)

    @staticmethod
    def _clamp_int(value: int, bounds: tuple) -> int:
        low, high = bounds
        return min(max(value, low), high)

    @classmethod
    def _coerce_odd(cls, value: int, bounds: tuple, fallback: int) -> int:
        """Clamp to range and force odd.

        AlignmentConfig rejects an even verify_frames outright: with an
        even count the "median" is the upper-middle frame, so one noisy
        fit decides the verdict. Rounding down to the nearest odd keeps
        the value inside the range at the top of the band.
        """
        value = cls._clamp_int(value, bounds)
        if value % 2 == 1:
            return value
        value -= 1
        low, _ = bounds
        return value if value >= low else fallback
