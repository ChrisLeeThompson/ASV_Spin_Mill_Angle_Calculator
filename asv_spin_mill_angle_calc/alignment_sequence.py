"""The Position Alignment automation sequence (Qt-free).

One :class:`AlignmentSequence` instance runs ONE position's alignment,
driven entirely through the :mod:`microscope_ops` Protocols so the same
logic runs against real AutoScript, the simulator, or plain test fakes.

Flow (see .claude/position_alignment_design.md for the requirements):

1.  CHECKS   — target angle window, beam on (refuse) / blanked (auto
    unblank), tilt limits, Specimen coordinate system.
2.  SETUP    — FIB into the active view; snapshot the operator's scan
    conditions (the run images with whatever ASV set up).
3.  SEARCH   — detect at the current tilt (ASV already tilted to the
    milling angle); if not found, walk tilt toward 0 in small steps
    (a fatter ellipse is easier to detect; never more negative),
    capped at the detector's angle ceiling. A failed sweep gets one
    auto-C/B + HFW-escalation rescue and a second sweep; both failing
    is NOT_FOUND.
4.  CONVERGE — center (stage x/y), level (FIB scan rotation until the
    ellipse is horizontal), walk tilt to the target and close the loop
    on the measured angle (correcting sample planarity), re-center,
    and optionally trim with ion-beam shift.
5.  RESTORE  — walk HFW back if the search escalated it. Scan rotation
    is deliberately NOT restored: it is the product ASV logs.
6.  VERIFY   — two consecutive fresh frames with angle, centering and
    level all inside tolerance; a failure re-enters CONVERGE once.

Safety posture: ``run()`` never raises; every hardware call is preceded
by a cooperative stop check (SDK calls block and cannot be interrupted —
Stop lands at the next boundary); no fit may command hardware without
passing quality + plausibility gates; every actuation is clamped and
capped; each loop direction-probes its sign once and aborts on a second
wrong-way response; commanded tilt at or below the -37.9 deg floor
aborts with TILT_LIMIT (the UI raises a dialog); move read-backs detect
external interference.
"""
from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Tuple

import numpy as np

from asv_spin_mill_angle_calc.alignment_config import (
    DEFAULT_ALIGNMENT_CONFIG,
    AlignmentConfig,
)
from asv_spin_mill_angle_calc.ellipse_detector import (
    EllipseFit,
    FiducialEllipseDetector,
)
from asv_spin_mill_angle_calc.microscope_ops import FibFrame, MicroscopeOps
from asv_spin_mill_angle_calc.spin_mill_geometry import (
    FIB_ANGLE_FROM_STAGE_PLANE_DEG,
    stage_tilt_for_milling_angle_deg,
)

logger = logging.getLogger(__name__)

# on_frame callback: (image, fit or None, pixel_size_m) per grabbed frame.
FrameCallback = Callable[[np.ndarray, Optional[EllipseFit], float], None]
StatusCallback = Callable[[str], None]


class AlignmentOutcome(str, Enum):
    ALIGNED = "aligned"
    STOPPED = "stopped"
    REFUSED = "refused"
    NOT_FOUND = "not_found"
    TILT_LIMIT = "tilt_limit"
    NOT_CONVERGED = "not_converged"
    ERROR = "error"


@dataclass(frozen=True)
class AlignmentParams:
    """Per-run user inputs, snapshotted at Start."""
    target_milling_angle_deg: float
    use_beam_shift: bool
    # ASV's AOI circle diameter; enables the fit-width gate and the
    # field-of-view fit check. 0 = unknown (checks disabled).
    aoi_diameter_um: float = 0.0


@dataclass(frozen=True)
class AlignmentResult:
    outcome: AlignmentOutcome
    message: str
    final_fit: Optional[EllipseFit] = None
    frames_grabbed: int = 0
    tilt_moves: int = 0
    center_moves: int = 0


# --- Internal control-flow exceptions (never escape run()) -----------------

class _Stop(Exception):
    pass


class _Refused(Exception):
    pass


class _NotFound(Exception):
    pass


class _TiltLimit(Exception):
    pass


class _NotConverged(Exception):
    pass


class _SignProbe:
    """Direction probe: flip a loop's sign once on a grew-worse response;
    a second grew-worse response means an inconsistent instrument
    response (or a false detection) and the loop must abort."""

    def __init__(self, name: str, sign: float) -> None:
        self.name = name
        self.sign = sign
        self._flipped = False

    def check(self, previous_error: Optional[float],
              new_error: float, slack: float) -> None:
        if previous_error is None or new_error <= previous_error + slack:
            return
        if not self._flipped:
            self._flipped = True
            self.sign = -self.sign
            logger.warning("%s response went the wrong way "
                           "(%.3f -> %.3f); reversing the correction sign",
                           self.name, previous_error, new_error)
            return
        raise _NotConverged(
            f"{self.name} response is inconsistent — possible false "
            "detection or mechanical anomaly (see console log)")


class AlignmentSequence:
    """Single-use runner for one position's alignment."""

    def __init__(self, ops: MicroscopeOps, params: AlignmentParams,
                 config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG,
                 detect: Optional[
                     Callable[[np.ndarray], Optional[EllipseFit]]] = None,
                 ) -> None:
        self._ops = ops
        self._params = params
        self._cfg = config
        self._detect = detect or FiducialEllipseDetector(
            config.detector).detect
        # Run state
        self._stop_event: threading.Event = threading.Event()
        self._on_status: StatusCallback = lambda text: None
        self._on_frame: FrameCallback = lambda image, fit, px: None
        self._phase_label = "Alignment"
        self._tilt_deg = 0.0            # tracked commanded tilt
        self._initial_hfw_m = 0.0
        self._expected_hfw_m = 0.0
        self._hfw_escalated = False
        self._last_pixel_size_m = 0.0
        self._last_frame_shape: Tuple[int, int] = (0, 0)  # (h, w)
        self._frames = 0
        self._tilt_moves = 0
        self._center_moves = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, stop_event: threading.Event,
            on_status: StatusCallback,
            on_frame: FrameCallback) -> AlignmentResult:
        """Run to a terminal outcome. Never raises."""
        self._stop_event = stop_event
        self._on_status = on_status
        self._on_frame = on_frame
        try:
            return self._run_inner()
        except _Stop:
            return self._result(AlignmentOutcome.STOPPED,
                                "Alignment stopped")
        except _Refused as refusal:
            return self._result(AlignmentOutcome.REFUSED, str(refusal))
        except _NotFound as not_found:
            return self._result(AlignmentOutcome.NOT_FOUND, str(not_found))
        except _TiltLimit as limit:
            return self._result(AlignmentOutcome.TILT_LIMIT, str(limit))
        except _NotConverged as not_converged:
            return self._result(AlignmentOutcome.NOT_CONVERGED,
                                str(not_converged))
        except Exception:
            logger.exception("Alignment failed during: %s",
                             self._phase_label)
            return self._result(
                AlignmentOutcome.ERROR,
                f"{self._phase_label} failed (see console log)")
        finally:
            self._restore_hfw_best_effort()

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def _run_inner(self) -> AlignmentResult:
        target_deg = self._params.target_milling_angle_deg
        self._checks(target_deg)
        self._setup()
        fit = self._search()
        for round_index in range(1, self._cfg.verify_rounds + 1):
            fit = self._converge(fit, target_deg)
            verified, fit, detail = self._verify(target_deg)
            if verified:
                return self._result(
                    AlignmentOutcome.ALIGNED,
                    f"Aligned: {fit.milling_angle_deg:.2f}° milling "
                    "angle, centered and level",
                    fit)
            logger.info("Verification round %d failed: %s",
                        round_index, detail)
        raise _NotConverged(
            f"Alignment did not verify ({detail}) — see console log")

    def _checks(self, target_deg: float) -> None:
        self._phase("Pre-checks", "Checking microscope state...")
        cfg = self._cfg
        if not (cfg.min_target_angle_deg <= target_deg
                <= cfg.max_target_angle_deg):
            raise _Refused(
                f"Target milling angle {target_deg:.1f}° is outside "
                f"the measurable {cfg.min_target_angle_deg:.0f}–"
                f"{cfg.max_target_angle_deg:.0f}° window")
        if not self._ops.ion_beam.is_on():
            raise _Refused("Ion beam is off — turn it on in xT, then "
                           "press Start")
        if self._ops.ion_beam.is_blanked():
            logger.info("Ion beam is blanked; unblanking")
            self._ops.ion_beam.unblank()
        model_tilt_deg = stage_tilt_for_milling_angle_deg(target_deg)
        low_deg, high_deg = self._ops.stage.tilt_limits_deg()
        if not (low_deg <= model_tilt_deg <= high_deg):
            raise _Refused(
                f"Target tilt {model_tilt_deg:.1f}° is outside the "
                f"stage limits ({low_deg:.1f}–{high_deg:.1f}°)")
        if model_tilt_deg <= self._cfg.tilt_floor_deg:
            raise _Refused(
                f"Target tilt {model_tilt_deg:.1f}° is at or below "
                f"the {self._cfg.tilt_floor_deg}° tilt limit")
        self._ops.stage.use_specimen_coordinates()

    def _setup(self) -> None:
        self._phase("View setup", "Selecting the ion beam view...")
        self._ops.imaging.prepare_fib_view(self._cfg.fib_view)
        conditions = self._ops.ion_beam.scan_conditions()
        self._initial_hfw_m = conditions.hfw_m
        self._expected_hfw_m = conditions.hfw_m
        self._tilt_deg = self._ops.stage.current_position().t_deg
        logger.info(
            "Run setup: scan conditions %s @ %.2e s dwell, HFW %.1f um, "
            "scan rotation %.2f deg, stage tilt %.2f deg",
            conditions.resolution, conditions.dwell_s,
            conditions.hfw_m * 1e6, conditions.scan_rotation_deg,
            self._tilt_deg)
        self._fit_hfw_to_aoi()

    def _fit_hfw_to_aoi(self) -> None:
        """Adjust HFW when the AOI cannot sit in the detector's size
        band at the operator's field of view (ellipse larger than the
        frame, or too small to detect). Treated like an escalation, so
        the operator's HFW is restored at the end of the run."""
        cfg = self._cfg
        aoi_um = self._params.aoi_diameter_um
        if aoi_um <= 0:
            return
        aoi_m = aoi_um * 1e-6
        ratio = aoi_m / self._expected_hfw_m
        if cfg.aoi_hfw_fit_min <= ratio <= cfg.aoi_hfw_fit_max:
            return
        new_hfw_m = aoi_m / cfg.aoi_hfw_target_ratio
        self._status("Adjusting the field of view to fit the AOI...")
        logger.info(
            "AOI %.0f um does not fit the detection band at HFW "
            "%.1f um (ratio %.2f); adjusting HFW to %.1f um",
            aoi_um, self._expected_hfw_m * 1e6, ratio, new_hfw_m * 1e6)
        self._check_stop()
        self._ops.ion_beam.set_horizontal_field_width_m(new_hfw_m)
        self._expected_hfw_m = new_hfw_m
        self._hfw_escalated = True

    # --- Search --------------------------------------------------------

    def _search(self) -> EllipseFit:
        cfg = self._cfg
        self._phase("Ellipse search", "Searching for the AOI ellipse...")
        start_tilt_deg = self._tilt_deg
        for sweep in range(1, cfg.sweep_count + 1):
            if sweep > 1:
                self._status("Ellipse not found — adjusting contrast and "
                             "field of view for another search...")
                self._check_stop()
                self._ops.imaging.run_auto_cb()
                self._escalate_hfw()
                self._tilt_absolute(start_tilt_deg)
            fit = self._sweep_once(start_tilt_deg, sweep)
            if fit is not None:
                self._status(
                    f"Ellipse found at {fit.milling_angle_deg:.2f}° "
                    f"(stage tilt {self._tilt_deg:.1f}°)")
                return fit
        raise _NotFound(
            f"Ellipse not found after {cfg.sweep_count} search sweeps — "
            "check the FIB view, then press Start to retry")

    def _sweep_once(self, start_tilt_deg: float,
                    sweep: int) -> Optional[EllipseFit]:
        cfg = self._cfg
        tilt_deg = start_tilt_deg
        while True:
            self._status(f"Search sweep {sweep}/{cfg.sweep_count}: "
                         f"looking at stage tilt {tilt_deg:.1f}°...")
            fit = self._measure_once()
            if fit is not None:
                return fit
            next_tilt_deg = tilt_deg + cfg.sweep_step_deg
            next_angle_deg = (next_tilt_deg
                              + FIB_ANGLE_FROM_STAGE_PLANE_DEG)
            if next_angle_deg > cfg.sweep_max_milling_angle_deg:
                return None
            self._tilt_absolute(next_tilt_deg)
            tilt_deg = next_tilt_deg

    def _escalate_hfw(self) -> None:
        new_hfw_m = self._expected_hfw_m * self._cfg.hfw_escalation_factor
        logger.info("Escalating HFW %.1f um -> %.1f um for the next sweep",
                    self._expected_hfw_m * 1e6, new_hfw_m * 1e6)
        self._ops.ion_beam.set_horizontal_field_width_m(new_hfw_m)
        self._expected_hfw_m = new_hfw_m
        self._hfw_escalated = True

    def _restore_hfw_best_effort(self) -> None:
        if not self._hfw_escalated:
            return
        try:
            self._ops.ion_beam.set_horizontal_field_width_m(
                self._initial_hfw_m)
            self._expected_hfw_m = self._initial_hfw_m
            self._hfw_escalated = False
            logger.info("Restored the operator's HFW (%.1f um)",
                        self._initial_hfw_m * 1e6)
        except Exception:
            logger.exception("Could not restore the operator's HFW "
                             "(non-fatal)")

    # --- Converge -------------------------------------------------------

    def _converge(self, fit: EllipseFit, target_deg: float) -> EllipseFit:
        fit = self._center_loop(fit, self._stage_tolerance_m(),
                                "Centering")
        fit = self._level_loop(fit)
        fit = self._tilt_walk_and_refine(fit, target_deg)
        fit = self._center_loop(fit, self._stage_tolerance_m(),
                                "Fine centering")
        if self._params.use_beam_shift:
            fit = self._beam_trim(fit)
        self._restore_hfw_best_effort()
        return fit

    def _center_loop(self, fit: EllipseFit, tolerance_m: float,
                     label: str) -> EllipseFit:
        cfg = self._cfg
        self._phase(label, f"{label} the AOI ellipse...")
        probe_x = _SignProbe(f"{label} (x)", cfg.stage_sign_x)
        probe_y = _SignProbe(f"{label} (y)", cfg.stage_sign_y)
        previous: Optional[Tuple[float, float]] = None
        slack_m = max(2.0 * self._last_pixel_size_m, 0.5e-6)
        for _ in range(cfg.center_max_iterations):
            offset_x_m, offset_y_m = self._offset_m(fit)
            if math.hypot(offset_x_m, offset_y_m) <= tolerance_m:
                return fit
            if previous is not None:
                probe_x.check(abs(previous[0]), abs(offset_x_m), slack_m)
                probe_y.check(abs(previous[1]), abs(offset_y_m), slack_m)
            world_x_m, world_y_m = self._image_to_world(
                offset_x_m, offset_y_m)
            self._status(
                f"{label}: moving stage by ({world_x_m * 1e6:+.1f}, "
                f"{world_y_m * 1e6:+.1f}) µm...")
            self._stage_move_xy(probe_x.sign * world_x_m,
                                probe_y.sign * world_y_m)
            previous = (offset_x_m, offset_y_m)
            fit = self._measure_required()
        raise _NotConverged(
            f"{label} did not converge within "
            f"{cfg.center_max_iterations} moves")

    def _level_loop(self, fit: EllipseFit) -> EllipseFit:
        cfg = self._cfg
        self._phase("Scan-rotation leveling",
                    "Leveling the ellipse with FIB scan rotation...")
        probe = _SignProbe("Scan-rotation leveling", cfg.level_sign)
        previous: Optional[float] = None
        for _ in range(cfg.level_max_iterations):
            if abs(fit.tilt_deg) <= cfg.level_tolerance_deg:
                return fit
            probe.check(previous, abs(fit.tilt_deg), 0.1)
            delta_deg = _clamp(probe.sign * fit.tilt_deg,
                               cfg.level_step_clamp_deg)
            current_deg = self._ops.ion_beam.scan_rotation_deg()
            self._status(f"Leveling: adjusting FIB scan rotation by "
                         f"{delta_deg:+.2f}°...")
            self._check_stop()
            self._ops.ion_beam.set_scan_rotation_deg(
                current_deg + delta_deg)
            previous = abs(fit.tilt_deg)
            fit = self._measure_required()
        raise _NotConverged(
            f"Scan-rotation leveling did not converge within "
            f"{cfg.level_max_iterations} adjustments")

    def _tilt_walk_and_refine(self, fit: EllipseFit,
                              target_deg: float) -> EllipseFit:
        cfg = self._cfg
        self._phase("Tilt adjustment",
                    "Walking stage tilt to the target milling angle...")
        model_tilt_deg = stage_tilt_for_milling_angle_deg(target_deg)
        # Open-loop walk in bounded steps, keeping the ellipse in view.
        while abs(model_tilt_deg - self._tilt_deg) > 1e-6:
            step_deg = _clamp(model_tilt_deg - self._tilt_deg,
                              cfg.tilt_walk_step_deg)
            self._status(f"Tilting stage to "
                         f"{self._tilt_deg + step_deg:.1f}°...")
            self._tilt_absolute(self._tilt_deg + step_deg)
            fit = self._measure_required()
            fit = self._keep_in_view(fit)
        # Closed loop on the measured angle (sample planarity correction).
        probe = _SignProbe("Tilt correction", cfg.tilt_sign)
        previous: Optional[float] = None
        for _ in range(cfg.tilt_max_iterations):
            measured_deg = fit.milling_angle_deg
            error_deg = target_deg - measured_deg
            self._status(f"Measured milling angle {measured_deg:.2f}° "
                         f"(target {target_deg:.1f}°)")
            if abs(error_deg) <= cfg.tilt_tolerance_deg:
                return fit
            probe.check(previous, abs(error_deg), 0.05)
            delta_deg = _clamp(probe.sign * error_deg,
                               cfg.tilt_step_clamp_deg)
            self._status(f"Adjusting stage tilt by {delta_deg:+.2f}°...")
            self._tilt_absolute(self._tilt_deg + delta_deg)
            previous = abs(error_deg)
            fit = self._measure_required()
            fit = self._keep_in_view(fit)
        raise _NotConverged(
            f"Tilt did not converge (last error "
            f"{target_deg - fit.milling_angle_deg:+.2f}°) within "
            f"{cfg.tilt_max_iterations} adjustments")

    def _keep_in_view(self, fit: EllipseFit) -> EllipseFit:
        """One recenter move when tilting walks the ellipse off-center
        far enough to threaten the detector's centered-geometry priors."""
        offset_x_m, offset_y_m = self._offset_m(fit)
        threshold_m = self._cfg.keep_in_view_frac * self._expected_hfw_m
        if math.hypot(offset_x_m, offset_y_m) <= threshold_m:
            return fit
        world_x_m, world_y_m = self._image_to_world(offset_x_m, offset_y_m)
        self._status("Re-centering to keep the ellipse in view...")
        self._stage_move_xy(self._cfg.stage_sign_x * world_x_m,
                            self._cfg.stage_sign_y * world_y_m)
        return self._measure_required()

    def _beam_trim(self, fit: EllipseFit) -> EllipseFit:
        cfg = self._cfg
        self._phase("Beam-shift trim",
                    "Fine-centering with ion beam shift...")
        tolerance_m = self._beam_tolerance_m()
        offset_x_m, offset_y_m = self._offset_m(fit)
        if math.hypot(offset_x_m, offset_y_m) <= tolerance_m:
            return fit
        world_x_m, world_y_m = self._image_to_world(offset_x_m, offset_y_m)
        current_x_m, current_y_m = self._ops.ion_beam.beam_shift_m()
        desired_x_m = current_x_m + cfg.beam_shift_sign_x * world_x_m
        desired_y_m = current_y_m + cfg.beam_shift_sign_y * world_y_m
        (x_lo, x_hi), (y_lo, y_hi) = self._beam_limits_m()
        clamped_x_m = min(max(desired_x_m, x_lo), x_hi)
        clamped_y_m = min(max(desired_y_m, y_lo), y_hi)
        self._check_stop()
        self._ops.ion_beam.set_beam_shift_m(clamped_x_m, clamped_y_m)
        readback_x_m, readback_y_m = self._ops.ion_beam.beam_shift_m()
        if (abs(readback_x_m - clamped_x_m) > 1e-9
                or abs(readback_y_m - clamped_y_m) > 1e-9):
            raise RuntimeError("Beam shift write had no effect "
                               "(read-back mismatch)")
        spill_x_m = desired_x_m - clamped_x_m
        spill_y_m = desired_y_m - clamped_y_m
        if abs(spill_x_m) > 1e-9 or abs(spill_y_m) > 1e-9:
            logger.info("Beam shift clamped to limits; spilling "
                        "(%.2f, %.2f) um to a stage move",
                        spill_x_m * 1e6, spill_y_m * 1e6)
            self._stage_move_xy(cfg.stage_sign_x * spill_x_m
                                / cfg.beam_shift_sign_x,
                                cfg.stage_sign_y * spill_y_m
                                / cfg.beam_shift_sign_y)
        return self._measure_required()

    def _beam_limits_m(self):
        try:
            return self._ops.ion_beam.beam_shift_limits_m()
        except Exception:
            fallback_m = self._cfg.beam_shift_fallback_limit_m
            logger.warning("Beam shift limits unreadable; clamping to "
                           "+/-%.1f um", fallback_m * 1e6)
            return ((-fallback_m, fallback_m), (-fallback_m, fallback_m))

    # --- Verify ----------------------------------------------------------

    def _verify(self, target_deg: float):
        cfg = self._cfg
        self._phase("Verification", "Verifying alignment...")
        tolerance_m = (self._beam_tolerance_m()
                       if self._params.use_beam_shift
                       else self._stage_tolerance_m())
        fit = None
        for attempt in range(2):  # two consecutive confirming frames
            fit = self._measure_required()
            angle_error_deg = abs(target_deg - fit.milling_angle_deg)
            offset_m = math.hypot(*self._offset_m(fit))
            level_deg = abs(fit.tilt_deg)
            if angle_error_deg > cfg.tilt_tolerance_deg:
                return (False, fit,
                        f"angle off by {angle_error_deg:.2f}°")
            if offset_m > tolerance_m:
                return (False, fit,
                        f"off-center by {offset_m * 1e6:.1f} µm")
            if level_deg > cfg.level_tolerance_deg:
                return (False, fit,
                        f"ellipse tilted {level_deg:.2f}°")
        return (True, fit, "")

    # --- Measurement helpers ----------------------------------------------

    def _grab(self) -> FibFrame:
        self._check_stop()
        frame = self._ops.imaging.grab_frame()
        self._frames += 1
        if self._expected_hfw_m > 0:
            drift = abs(frame.hfw_m - self._expected_hfw_m)
            if drift > self._cfg.hfw_change_abort_frac * self._expected_hfw_m:
                raise RuntimeError(
                    "Imaging conditions changed mid-run (HFW "
                    f"{self._expected_hfw_m * 1e6:.1f} -> "
                    f"{frame.hfw_m * 1e6:.1f} um)")
        self._last_pixel_size_m = frame.pixel_size_m
        self._last_frame_shape = frame.data.shape[:2]
        return frame

    def _measure_once(self) -> Optional[EllipseFit]:
        """One grab + sanity guard + detect + gates. Publishes every
        frame (including rejected ones, so the operator sees why)."""
        frame = self._grab()
        if not self._frame_usable(frame):
            self._on_frame(frame.data, None, frame.pixel_size_m)
            return None
        fit = self._detect(frame.data)
        self._on_frame(frame.data, fit, frame.pixel_size_m)
        if fit is None:
            return None
        return fit if self._fit_acceptable(fit) else None

    def _frame_usable(self, frame: FibFrame) -> bool:
        """Near-black, saturated, or contrast-less frames never reach
        the detector — it could hallucinate a fit from noise. Treated
        as a failed detection so the ladder's auto-C/B can rescue."""
        cfg = self._cfg
        data = frame.data
        if np.issubdtype(data.dtype, np.integer):
            full_scale = float(np.iinfo(data.dtype).max)
        else:
            full_scale = max(float(data.max()), 1.0)
        mean_frac = float(data.mean()) / full_scale
        std_frac = float(data.std()) / full_scale
        if (mean_frac < cfg.frame_min_mean_frac
                or mean_frac > cfg.frame_max_mean_frac
                or std_frac < cfg.frame_min_std_frac):
            logger.info("Frame rejected by the sanity guard: mean %.1f%%, "
                        "std %.2f%% of full scale", mean_frac * 100,
                        std_frac * 100)
            return False
        return True

    def _measure_required(self) -> EllipseFit:
        """Measurement with the recovery ladder; losing the ellipse
        mid-alignment is NOT_FOUND."""
        for _ in range(1 + self._cfg.detection_retries):
            fit = self._measure_once()
            if fit is not None:
                return fit
        logger.info("Detection lost; running auto contrast/brightness "
                    "and retrying once")
        self._check_stop()
        self._ops.imaging.run_auto_cb()
        fit = self._measure_once()
        if fit is not None:
            return fit
        raise _NotFound("Ellipse lost during alignment — check the FIB "
                        "view, then press Start to retry")

    def _fit_acceptable(self, fit: EllipseFit) -> bool:
        cfg = self._cfg
        if (fit.n_inliers < cfg.fit_min_inliers
                or fit.coverage < cfg.fit_min_coverage
                or fit.rms_px > cfg.fit_max_rms_px):
            logger.info("Fit rejected by quality gates: inliers=%d "
                        "coverage=%.2f rms=%.2f", fit.n_inliers,
                        fit.coverage, fit.rms_px)
            return False
        model_angle_deg = self._tilt_deg + FIB_ANGLE_FROM_STAGE_PLANE_DEG
        if abs(fit.milling_angle_deg
               - model_angle_deg) > cfg.plausibility_window_deg:
            logger.info(
                "Fit rejected as implausible: measured %.2f deg vs model "
                "%.2f deg at stage tilt %.2f deg", fit.milling_angle_deg,
                model_angle_deg, self._tilt_deg)
            return False
        aoi_um = self._params.aoi_diameter_um
        if aoi_um > 0 and self._last_pixel_size_m > 0:
            # The major axis is the true AOI diameter — foreshortening
            # only shrinks the minor axis — so measured width vs the
            # user's diameter is an independent false-detection gate.
            width_um = (2.0 * fit.semi_major_px
                        * self._last_pixel_size_m * 1e6)
            if abs(width_um - aoi_um) > cfg.aoi_width_tolerance_frac * aoi_um:
                logger.info(
                    "Fit rejected by the AOI width gate: measured width "
                    "%.0f um vs expected %.0f um", width_um, aoi_um)
                return False
        return True

    def _offset_m(self, fit: EllipseFit) -> Tuple[float, float]:
        """Ellipse-center offset from the frame center, image coords."""
        height, width = self._last_frame_shape
        return ((fit.center_x_px - width / 2.0) * self._last_pixel_size_m,
                (fit.center_y_px - height / 2.0) * self._last_pixel_size_m)

    def _image_to_world(self, dx_m: float,
                        dy_m: float) -> Tuple[float, float]:
        """Rotate an image-frame offset back through the scan rotation."""
        rotation_deg = self._ops.ion_beam.scan_rotation_deg()
        c = math.cos(math.radians(rotation_deg))
        s = math.sin(math.radians(rotation_deg))
        return (c * dx_m + s * dy_m, -s * dx_m + c * dy_m)

    def _stage_tolerance_m(self) -> float:
        return max(self._cfg.center_tolerance_frac_of_hfw
                   * self._expected_hfw_m,
                   3.0 * self._last_pixel_size_m)

    def _beam_tolerance_m(self) -> float:
        return max(self._cfg.center_tolerance_beam_frac_of_hfw
                   * self._expected_hfw_m,
                   3.0 * self._last_pixel_size_m)

    # --- Motion helpers -----------------------------------------------------

    def _tilt_absolute(self, tilt_deg: float) -> None:
        cfg = self._cfg
        if tilt_deg <= cfg.tilt_floor_deg:
            raise _TiltLimit(
                f"Stage tilt of {tilt_deg:.2f}° would reach the "
                f"{cfg.tilt_floor_deg}° limit — tilt angles are too "
                "large to proceed. Check the sample and target angle.")
        low_deg, high_deg = self._ops.stage.tilt_limits_deg()
        if not (low_deg <= tilt_deg <= high_deg):
            raise _NotConverged(
                f"Stage tilt {tilt_deg:.2f}° is outside the stage "
                f"limits ({low_deg:.1f}–{high_deg:.1f}°)")
        self._check_stop()
        self._ops.stage.absolute_move(t_deg=tilt_deg)
        self._tilt_moves += 1
        actual_deg = self._ops.stage.current_position().t_deg
        if abs(actual_deg - tilt_deg) > cfg.tilt_readback_tolerance_deg:
            raise RuntimeError(
                f"Stage tilt read-back {actual_deg:.3f}° does not "
                f"match the commanded {tilt_deg:.3f}° — external "
                "stage movement or an axis fault")
        self._tilt_deg = actual_deg
        self._settle()

    def _stage_move_xy(self, dx_m: float, dy_m: float) -> None:
        self._check_stop()
        before = self._ops.stage.current_position()
        self._ops.stage.relative_move(x_m=dx_m, y_m=dy_m)
        self._center_moves += 1
        after = self._ops.stage.current_position()
        tolerance_m = self._cfg.xy_readback_tolerance_m
        if (abs(after.x_m - (before.x_m + dx_m)) > tolerance_m
                or abs(after.y_m - (before.y_m + dy_m)) > tolerance_m):
            raise RuntimeError(
                "Stage X/Y read-back does not match the commanded move — "
                "external stage movement or an axis fault")
        self._settle()

    def _settle(self) -> None:
        """Post-move settle that stays responsive to Stop."""
        if self._stop_event.wait(self._cfg.settle_delay_s):
            raise _Stop()

    # --- Small utilities ------------------------------------------------

    def _check_stop(self) -> None:
        if self._stop_event.is_set():
            raise _Stop()

    def _phase(self, label: str, status: str) -> None:
        self._phase_label = label
        self._status(status)

    def _status(self, text: str) -> None:
        logger.info("%s", text)
        self._on_status(text)

    def _result(self, outcome: AlignmentOutcome, message: str,
                fit: Optional[EllipseFit] = None) -> AlignmentResult:
        self._status(message)
        return AlignmentResult(
            outcome=outcome, message=message, final_fit=fit,
            frames_grabbed=self._frames, tilt_moves=self._tilt_moves,
            center_moves=self._center_moves)


def _clamp(value: float, magnitude: float) -> float:
    return max(-magnitude, min(magnitude, value))
