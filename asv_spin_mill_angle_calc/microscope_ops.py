"""Qt-free microscope operation seams for the Position Alignment backend.

This module is the app's single unit-conversion boundary with AutoScript:
every SDK call the alignment feature makes lives here (or in the simulated
twin, :mod:`asv_spin_mill_angle_calc.simulated_microscope`). The SDK works
in base SI — meters everywhere and **radians** for stage rotation/tilt and
scan rotation — while the rest of the application reasons in degrees, so
the conversion happens in exactly this file and nowhere else. Everything
crossing the seam carries a unit suffix (``_deg``, ``_rad``, ``_m``,
``_s``).

The one radians DTO is :class:`PositionRecord`: it is the Confirm-button
readback destined for the results table model, whose QML role contract is
SI radians/meters (delegates convert for display) — so it passes SDK
values through unconverted, matching :class:`SpinMillImageMetadata`.

Three narrow Protocols (stage, FIB imaging, ion beam) keep the alignment
sequence hardware-agnostic and unit-testable with plain fakes. The real
implementations are deliberately thin: no policy (clamping, retries,
tolerances belong to the sequence), no exception handling (the worker is
the single logging point), and lazy SDK imports inside methods so the app
loads on machines without AutoScript.

Two AutoScript traps this module encapsulates:

* Stage moves must never default unspecified axes to 0.0 — a zeroed Z is
  a chamber-collision bug. ``None`` means "don't move that axis" and the
  ``StagePosition`` is built only from the axes provided.
* ``beam_shift.value.x = ...`` is a documented silent no-op; beam shift
  is only ever written as a whole ``Point``.

Every move passes an explicit ``MoveSettings()`` and the run asserts the
Specimen coordinate system up front, because AutoScript's move settings
and default coordinate system are sticky, client-global state that another
script may have changed.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Tuple, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)

# ImagingDevice enum value for the FIB (AutoScript passes enums as plain
# ints; using the literal avoids importing the SDK at module scope).
ION_BEAM_DEVICE: int = 2


# -----------------------------------------------------------------
# Value types crossing the seam
# -----------------------------------------------------------------

@dataclass(frozen=True)
class StageSnapshot:
    """Stage position readback. Degrees for R/T (converted from SDK rad)."""
    x_m: float
    y_m: float
    z_m: float
    r_deg: float
    t_deg: float


@dataclass(frozen=True)
class FibFrame:
    """One grabbed FIB frame plus the scale needed to act on it."""
    data: np.ndarray        # 2D grayscale copy (safe to pass across threads)
    pixel_size_m: float     # meters per pixel (x)
    hfw_m: float            # horizontal field width at grab time


@dataclass(frozen=True)
class ScanConditions:
    """The operator's current FIB scan setup, snapshotted at run start."""
    resolution: str         # e.g. "768x512"
    dwell_s: float
    hfw_m: float
    scan_rotation_deg: float


@dataclass(frozen=True)
class PositionRecord:
    """Confirm readback — SI radians/meters (the results-model contract)."""
    stage_r_rad: float
    stage_t_rad: float
    stage_x_m: float
    stage_y_m: float
    beam_x_m: float
    beam_y_m: float
    scan_r_rad: float
    wd_m: float


# -----------------------------------------------------------------
# Protocols (what the alignment sequence is written against)
# -----------------------------------------------------------------

@runtime_checkable
class StageOps(Protocol):
    def use_specimen_coordinates(self) -> None: ...

    def current_position(self) -> StageSnapshot: ...

    def absolute_move(self, *, x_m: Optional[float] = None,
                      y_m: Optional[float] = None,
                      z_m: Optional[float] = None,
                      r_deg: Optional[float] = None,
                      t_deg: Optional[float] = None) -> None: ...

    def relative_move(self, *, x_m: Optional[float] = None,
                      y_m: Optional[float] = None,
                      t_deg: Optional[float] = None) -> None: ...

    def tilt_limits_deg(self) -> Tuple[float, float]: ...


@runtime_checkable
class FibImagingOps(Protocol):
    def prepare_fib_view(self, view: int) -> None: ...

    def grab_frame(self) -> FibFrame: ...

    def run_auto_cb(self) -> None: ...


@runtime_checkable
class IonBeamOps(Protocol):
    def is_on(self) -> bool: ...

    def is_blanked(self) -> bool: ...

    def unblank(self) -> None: ...

    def beam_shift_m(self) -> Tuple[float, float]: ...

    def set_beam_shift_m(self, x_m: float, y_m: float) -> None: ...

    def beam_shift_limits_m(
        self) -> Tuple[Tuple[float, float], Tuple[float, float]]: ...

    def scan_rotation_deg(self) -> float: ...

    def set_scan_rotation_deg(self, value_deg: float) -> None: ...

    def horizontal_field_width_m(self) -> float: ...

    def set_horizontal_field_width_m(self, value_m: float) -> None: ...

    def working_distance_m(self) -> float: ...

    def scan_conditions(self) -> ScanConditions: ...


@dataclass(frozen=True)
class MicroscopeOps:
    """The bundle handed to the alignment sequence and Confirm readback."""
    stage: StageOps
    imaging: FibImagingOps
    ion_beam: IonBeamOps


def read_position_record(ops: MicroscopeOps) -> PositionRecord:
    """Confirm's readback: one results-table row from live values."""
    snapshot = ops.stage.current_position()
    beam_x_m, beam_y_m = ops.ion_beam.beam_shift_m()
    return PositionRecord(
        stage_r_rad=math.radians(snapshot.r_deg),
        stage_t_rad=math.radians(snapshot.t_deg),
        stage_x_m=snapshot.x_m,
        stage_y_m=snapshot.y_m,
        beam_x_m=beam_x_m,
        beam_y_m=beam_y_m,
        scan_r_rad=math.radians(ops.ion_beam.scan_rotation_deg()),
        wd_m=ops.ion_beam.working_distance_m(),
    )


# -----------------------------------------------------------------
# Real AutoScript implementations
# -----------------------------------------------------------------

class AutoscriptStageOps:
    """StageOps over a connected SdbMicroscopeClient."""

    def __init__(self, sdb: Any) -> None:
        self._stage = sdb.specimen.stage

    def use_specimen_coordinates(self) -> None:
        self._stage.set_default_coordinate_system("Specimen")

    def current_position(self) -> StageSnapshot:
        position = self._stage.current_position
        return StageSnapshot(
            x_m=float(position.x),
            y_m=float(position.y),
            z_m=float(position.z),
            r_deg=math.degrees(float(position.r)),
            t_deg=math.degrees(float(position.t)),
        )

    def absolute_move(self, *, x_m=None, y_m=None, z_m=None,
                      r_deg=None, t_deg=None) -> None:
        from autoscript_sdb_microscope_client.structures import (
            MoveSettings,
            StagePosition,
        )
        axes = self._axes(x=x_m, y=y_m, z=z_m,
                          r=None if r_deg is None else math.radians(r_deg),
                          t=None if t_deg is None else math.radians(t_deg))
        self._stage.absolute_move(StagePosition(**axes), MoveSettings())

    def relative_move(self, *, x_m=None, y_m=None, t_deg=None) -> None:
        from autoscript_sdb_microscope_client.structures import (
            MoveSettings,
            StagePosition,
        )
        axes = self._axes(x=x_m, y=y_m,
                          t=None if t_deg is None else math.radians(t_deg))
        self._stage.relative_move(StagePosition(**axes), MoveSettings())

    def tilt_limits_deg(self) -> Tuple[float, float]:
        limits = self._stage.get_axis_limits("t")
        return (math.degrees(float(limits.min)),
                math.degrees(float(limits.max)))

    @staticmethod
    def _axes(**axes: Optional[float]) -> dict:
        """Drop unspecified axes so they are not moved (never default 0)."""
        return {name: value for name, value in axes.items()
                if value is not None}


class AutoscriptFibImagingOps:
    """FibImagingOps over a connected SdbMicroscopeClient.

    ``grab_frame`` takes no settings on purpose: the feature images with
    whatever scan conditions the operator set up in ASV (user decision),
    and a bare ``grab_frame()`` uses the current presets.
    """

    def __init__(self, sdb: Any) -> None:
        self._sdb = sdb

    def prepare_fib_view(self, view: int) -> None:
        self._sdb.imaging.set_active_view(view)
        self._sdb.imaging.set_active_device(ION_BEAM_DEVICE)

    def grab_frame(self) -> FibFrame:
        image = self._sdb.imaging.grab_frame()
        data = np.array(image.data)  # decouple from SDK buffer lifetime
        hfw_m = self._hfw_of(image)
        return FibFrame(
            data=data,
            pixel_size_m=self._pixel_size_of(image, hfw_m),
            hfw_m=hfw_m,
        )

    def run_auto_cb(self) -> None:
        self._sdb.auto_functions.run_auto_cb()

    def _hfw_of(self, image: Any) -> float:
        try:
            value = image.metadata.optics.horizontal_field_width
            if value:
                return float(value)
        except Exception:  # metadata section absent on some formats
            pass
        return float(
            self._sdb.beams.ion_beam.horizontal_field_width.value)

    def _pixel_size_of(self, image: Any, hfw_m: float) -> float:
        try:
            value = image.metadata.binary_result.pixel_size.x
            if value:
                return float(value)
        except Exception:
            pass
        logger.warning("Frame metadata lacks pixel size; deriving from "
                       "HFW / image width")
        return hfw_m / float(image.data.shape[1])


class AutoscriptIonBeamOps:
    """IonBeamOps over a connected SdbMicroscopeClient."""

    def __init__(self, sdb: Any) -> None:
        self._beam = sdb.beams.ion_beam

    def is_on(self) -> bool:
        return bool(self._beam.is_on)

    def is_blanked(self) -> bool:
        return bool(self._beam.is_blanked)

    def unblank(self) -> None:
        self._beam.unblank()

    def beam_shift_m(self) -> Tuple[float, float]:
        value = self._beam.beam_shift.value
        return (float(value.x), float(value.y))

    def set_beam_shift_m(self, x_m: float, y_m: float) -> None:
        from autoscript_sdb_microscope_client.structures import Point
        # Whole-Point assignment only: member writes on .value are a
        # documented silent no-op.
        self._beam.beam_shift.value = Point(x_m, y_m)

    def beam_shift_limits_m(self):
        limits = self._beam.beam_shift.limits
        return ((float(limits.limits_x.min), float(limits.limits_x.max)),
                (float(limits.limits_y.min), float(limits.limits_y.max)))

    def scan_rotation_deg(self) -> float:
        return math.degrees(float(self._beam.scanning.rotation.value))

    def set_scan_rotation_deg(self, value_deg: float) -> None:
        self._beam.scanning.rotation.value = math.radians(value_deg)

    def horizontal_field_width_m(self) -> float:
        return float(self._beam.horizontal_field_width.value)

    def set_horizontal_field_width_m(self, value_m: float) -> None:
        self._beam.horizontal_field_width.value = value_m

    def working_distance_m(self) -> float:
        return float(self._beam.working_distance.value)

    def scan_conditions(self) -> ScanConditions:
        return ScanConditions(
            resolution=str(self._beam.scanning.resolution.value),
            dwell_s=float(self._beam.scanning.dwell_time.value),
            hfw_m=self.horizontal_field_width_m(),
            scan_rotation_deg=self.scan_rotation_deg(),
        )


def build_autoscript_ops(sdb: Any) -> MicroscopeOps:
    """The ops bundle over a connected raw SDK handle."""
    return MicroscopeOps(
        stage=AutoscriptStageOps(sdb),
        imaging=AutoscriptFibImagingOps(sdb),
        ion_beam=AutoscriptIonBeamOps(sdb),
    )
