"""Qt-free simulated microscope for offline development and tests.

Activated explicitly at connect time (see ``create_client`` in
:mod:`asv_spin_mill_angle_calc.microscope_client`) — never a silent
fallback. The simulator is a *closed-loop physics twin*, not a canned
frame player: one shared :class:`SimulatedMicroscopeState` backs all
three ops, and ``grab_frame`` renders the fiducial ring from that state
using the application's own forward model:

* milling angle = stage tilt + 38 (``spin_mill_geometry`` inverse), so
  the ellipse flattens as tilt approaches -38 and disappears past it;
* ellipse center tracks (fiducial - stage - beam shift), rotated into
  the image by the scan rotation, so centering moves genuinely converge;
* the drawn ellipse's rotation is (fiducial plane rotation - scan
  rotation), so the scan-rotation leveling loop genuinely levels it;
* the ring renders dark-on-light or bright-on-dark per state, covering
  both detector polarities.

The same simulator (with zero delays) is the pytest integration fixture.
An optional ``frames_dir`` replaces the renderer with an open-loop replay
of real capture PNGs (e.g. the Spin-mill_Development logs) for detector
realism; the closed loops cannot converge in that mode.

Axis conventions are the application's assumed defaults (identity signs);
real instruments may flip them, which is what the alignment config's sign
constants are for — the simulator ships the convention the defaults
assume, and hardware shakedown tunes only the config.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from asv_spin_mill_angle_calc.microscope_ops import (
    FibFrame,
    MicroscopeOps,
    ScanConditions,
    StageSnapshot,
)
from asv_spin_mill_angle_calc.spin_mill_geometry import (
    FIB_ANGLE_FROM_STAGE_PLANE_DEG,
)

logger = logging.getLogger(__name__)


@dataclass
class SimulatedMicroscopeState:
    """Shared mutable instrument state; guard access with ``lock``."""
    # Stage (degrees / meters, matching the ops seam)
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 5.0e-3
    r_deg: float = 0.0
    t_deg: float = -34.0            # ASV parks at the milling-angle tilt
    # Ion beam / scanning
    beam_shift_x_m: float = 0.0
    beam_shift_y_m: float = 0.0
    scan_rotation_deg: float = 0.0
    hfw_m: float = 800.0e-6
    wd_m: float = 4.0e-3
    resolution: str = "768x512"
    dwell_s: float = 1.0e-6
    beam_on: bool = True
    blanked: bool = False
    # The sample "truth" the loops must discover
    fiducial_x_m: float = 15.0e-6
    fiducial_y_m: float = -10.0e-6
    # Matches the UI's default AOI Diameter (800 um), so a default sim
    # session passes the AOI width gate out of the box.
    fiducial_diameter_m: float = 800.0e-6
    fiducial_plane_rotation_deg: float = 3.0
    # Local surface tilt (sample planarity error): the measured milling
    # angle is stage tilt + 38 + this, so the closed tilt loop has real
    # work to do — the corrected stage tilt differs from (target - 38).
    fiducial_plane_tilt_offset_deg: float = 0.0
    ring_bright: bool = False       # False: dark ring on light surface
    # Below this milling angle the ring is not rendered — models the
    # contrast loss that makes near-grazing rings invisible (the drawn
    # line's 2 px thickness would otherwise keep flat rings detectable).
    # Tests raise it to force the "not found at current tilt" sweep case.
    ring_visible_above_angle_deg: float = 1.0
    # Behavior knobs
    move_delay_s: float = 0.0       # per-move settle (app: small, tests: 0)
    connect_delay_s: float = 0.0
    # Internals
    frame_counter: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock,
                                 repr=False)

    def frame_size(self) -> Tuple[int, int]:
        width, height = self.resolution.split("x")
        return int(width), int(height)


def _rotate_deg(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    return (c * x - s * y, s * x + c * y)


class SimulatedStageOps:
    def __init__(self, state: SimulatedMicroscopeState) -> None:
        self._state = state

    def use_specimen_coordinates(self) -> None:
        pass

    def current_position(self) -> StageSnapshot:
        st = self._state
        with st.lock:
            return StageSnapshot(x_m=st.x_m, y_m=st.y_m, z_m=st.z_m,
                                 r_deg=st.r_deg, t_deg=st.t_deg)

    def absolute_move(self, *, x_m=None, y_m=None, z_m=None,
                      r_deg=None, t_deg=None) -> None:
        st = self._state
        with st.lock:
            if x_m is not None:
                st.x_m = x_m
            if y_m is not None:
                st.y_m = y_m
            if z_m is not None:
                st.z_m = z_m
            if r_deg is not None:
                st.r_deg = r_deg
            if t_deg is not None:
                st.t_deg = t_deg
            delay = st.move_delay_s
        if delay:
            time.sleep(delay)

    def relative_move(self, *, x_m=None, y_m=None, t_deg=None) -> None:
        st = self._state
        with st.lock:
            if x_m is not None:
                st.x_m += x_m
            if y_m is not None:
                st.y_m += y_m
            if t_deg is not None:
                st.t_deg += t_deg
            delay = st.move_delay_s
        if delay:
            time.sleep(delay)

    def tilt_limits_deg(self) -> Tuple[float, float]:
        return (-60.0, 60.0)


class SimulatedFibImagingOps:
    """Renders frames from state, or replays a folder of real captures."""

    def __init__(self, state: SimulatedMicroscopeState,
                 frames_dir: Optional[str] = None) -> None:
        self._state = state
        self.active_view: Optional[int] = None
        self.auto_cb_runs: int = 0
        self._replay_paths: List[Path] = []
        if frames_dir:
            self._replay_paths = sorted(Path(frames_dir).glob("*.png"))
            logger.info("Simulated imaging: replaying %d frames from %s",
                        len(self._replay_paths), frames_dir)

    def prepare_fib_view(self, view: int) -> None:
        self.active_view = view

    def run_auto_cb(self) -> None:
        self.auto_cb_runs += 1

    def grab_frame(self) -> FibFrame:
        st = self._state
        with st.lock:
            st.frame_counter += 1
            if self._replay_paths:
                path = self._replay_paths[
                    (st.frame_counter - 1) % len(self._replay_paths)]
                data = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                return FibFrame(data=data,
                                pixel_size_m=st.hfw_m / data.shape[1],
                                hfw_m=st.hfw_m)
            return self._render_locked()

    def _render_locked(self) -> FibFrame:
        """Render the fiducial from state. Caller holds the lock."""
        st = self._state
        width, height = st.frame_size()
        pixel_size_m = st.hfw_m / width
        if st.ring_bright:
            background_level, ring_level = 60, 200
        else:
            background_level, ring_level = 140, 60

        rng = np.random.default_rng(st.frame_counter)
        image = np.full((height, width), background_level, dtype=np.float32)
        image += rng.normal(0.0, 6.0, size=image.shape)

        if not st.blanked and st.beam_on:
            milling_angle_deg = (st.t_deg + FIB_ANGLE_FROM_STAGE_PLANE_DEG
                                 + st.fiducial_plane_tilt_offset_deg)
            if milling_angle_deg > st.ring_visible_above_angle_deg:
                offset_x_m = st.fiducial_x_m - st.x_m - st.beam_shift_x_m
                offset_y_m = st.fiducial_y_m - st.y_m - st.beam_shift_y_m
                image_dx_m, image_dy_m = _rotate_deg(
                    offset_x_m, offset_y_m, st.scan_rotation_deg)
                center = (int(round(width / 2 + image_dx_m / pixel_size_m)),
                          int(round(height / 2 + image_dy_m / pixel_size_m)))
                semi_major_px = (st.fiducial_diameter_m / 2.0) / pixel_size_m
                semi_minor_px = semi_major_px * math.sin(
                    math.radians(milling_angle_deg))
                ellipse_rotation_deg = (st.fiducial_plane_rotation_deg
                                        - st.scan_rotation_deg)
                cv2.ellipse(image, center,
                            (int(round(semi_major_px)),
                             max(1, int(round(semi_minor_px)))),
                            ellipse_rotation_deg, 0, 360, ring_level, 2)
        image = cv2.GaussianBlur(image, (0, 0), 1.0)
        data = np.clip(image, 0, 255).astype(np.uint8)
        return FibFrame(data=data, pixel_size_m=pixel_size_m, hfw_m=st.hfw_m)


class SimulatedIonBeamOps:
    def __init__(self, state: SimulatedMicroscopeState) -> None:
        self._state = state

    def is_on(self) -> bool:
        with self._state.lock:
            return self._state.beam_on

    def is_blanked(self) -> bool:
        with self._state.lock:
            return self._state.blanked

    def unblank(self) -> None:
        with self._state.lock:
            self._state.blanked = False

    def beam_shift_m(self) -> Tuple[float, float]:
        with self._state.lock:
            return (self._state.beam_shift_x_m, self._state.beam_shift_y_m)

    def set_beam_shift_m(self, x_m: float, y_m: float) -> None:
        with self._state.lock:
            self._state.beam_shift_x_m = x_m
            self._state.beam_shift_y_m = y_m

    def beam_shift_limits_m(self):
        return ((-50.0e-6, 50.0e-6), (-50.0e-6, 50.0e-6))

    def scan_rotation_deg(self) -> float:
        with self._state.lock:
            return self._state.scan_rotation_deg

    def set_scan_rotation_deg(self, value_deg: float) -> None:
        with self._state.lock:
            self._state.scan_rotation_deg = value_deg

    def horizontal_field_width_m(self) -> float:
        with self._state.lock:
            return self._state.hfw_m

    def set_horizontal_field_width_m(self, value_m: float) -> None:
        with self._state.lock:
            self._state.hfw_m = value_m

    def working_distance_m(self) -> float:
        with self._state.lock:
            return self._state.wd_m

    def scan_conditions(self) -> ScanConditions:
        with self._state.lock:
            return ScanConditions(
                resolution=self._state.resolution,
                dwell_s=self._state.dwell_s,
                hfw_m=self._state.hfw_m,
                scan_rotation_deg=self._state.scan_rotation_deg,
            )


class SimulatedMicroscopeClient:
    """Duck-types MicroscopeClient (connect lifecycle + ops bundle)."""

    is_simulated: bool = True

    def __init__(self, frames_dir: Optional[str] = None,
                 state: Optional[SimulatedMicroscopeState] = None) -> None:
        self.state = state or SimulatedMicroscopeState()
        self._frames_dir = frames_dir
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def server_host(self) -> str:
        return "simulated" if self._connected else ""

    def connect(self) -> None:
        if self._connected:
            logger.warning("Already connected; ignoring connect() call")
            return
        if self.state.connect_delay_s:
            time.sleep(self.state.connect_delay_s)
        self._connected = True
        logger.info("Connected to SIMULATED microscope")

    def disconnect(self) -> None:
        if not self._connected:
            return
        self._connected = False
        logger.info("Disconnected from SIMULATED microscope")

    def ops(self) -> MicroscopeOps:
        if not self._connected:
            raise RuntimeError("Simulated microscope is not connected")
        return MicroscopeOps(
            stage=SimulatedStageOps(self.state),
            imaging=SimulatedFibImagingOps(self.state, self._frames_dir),
            ion_beam=SimulatedIonBeamOps(self.state),
        )
