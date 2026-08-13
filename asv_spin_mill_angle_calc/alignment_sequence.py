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
    capped at the detector's angle ceiling. The sample-planarity
    anchor requires TWO consistent fits (same center and width,
    angles tracking stage tilt 1:1) — one clutter fit can no longer
    poison the run — and once confirmed, the MEASURED ring width
    becomes the working width (mismatch with the entered AOI is an
    operator advisory, not a rejection). A failed sweep gets one
    auto-C/B + HFW-escalation rescue and a second sweep; both failing
    is NOT_FOUND.
4.  CONVERGE — center (stage x/y), level (FIB scan rotation until the
    ellipse is horizontal; once the ring has been SEEN level, later
    larger tilt readings are noise and leveling stays off), walk tilt
    to the target and close the loop on the measured angle
    (correcting sample planarity), re-center, and optionally trim
    with ion-beam shift. Losing detection mid-run triggers a bounded
    in-place re-anchor (fresh 2-frame lock at the wide window) before
    giving up.
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

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

from asv_spin_mill_angle_calc.alignment_config import (
    DEFAULT_ALIGNMENT_CONFIG,
    AlignmentConfig,
)
from asv_spin_mill_angle_calc.ellipse_detector import (
    EllipseFit,
    ExpectedGeometry,
    FiducialEllipseDetector,
)
from asv_spin_mill_angle_calc.microscope_ops import FibFrame, MicroscopeOps
from asv_spin_mill_angle_calc.spin_mill_geometry import (
    FIB_ANGLE_FROM_STAGE_PLANE_DEG,
    stage_tilt_for_milling_angle_deg,
)

logger = logging.getLogger(__name__)

# Environment override for AlignmentConfig.debug_frames_dir (takes
# precedence when set, so debug capture can be enabled without a code
# or config change on the support PC).
ASV_DEBUG_ENV = "ASV_DEBUG_FRAMES_DIR"

# Headroom for the ring's intrinsic in-plane rotation when bounding the
# detector's tilt search (measured +0.14 deg on the 2026-08 corpus; the
# bound additionally grows with the applied scan rotation).
_INTRINSIC_RING_TILT_HEADROOM_DEG = 2.0

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
    # Operator advisories collected during the run (width mismatch,
    # mid-run re-anchor, ...) — attached to every outcome, so a failed
    # run still tells the operator what was tried.
    warnings: Tuple[str, ...] = ()


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


class _Reacquired(Exception):
    """Mid-run re-anchor succeeded: convergence must restart from the
    fresh lock (sign probes and iteration counters hold pre-blackout
    history that is no longer meaningful). Consumed in _run_inner;
    bounded by reanchor_budget."""

    def __init__(self, fit: EllipseFit) -> None:
        super().__init__("re-anchored")
        self.fit = fit


@dataclass(frozen=True)
class _AnchorObservation:
    """One gate-passing fit, in anchor-relevant coordinates."""
    fit: EllipseFit
    tilt_deg: float      # stage tilt when measured
    offset_deg: float    # measured milling angle - open-loop model
    width_um: float      # measured ring width (0 when unknown)


class _PlanarityAnchor:
    """Two-frame-verified sample-planarity anchor.

    Run 1 of the 2026-08 hardware test died from anchor poisoning: ONE
    unverified clutter fit anchored the offset at -2.97 deg and the
    tracking window then excluded the true ring for the rest of the
    run. The anchor now requires two consistent observations: same
    center, same semi-major axis, and measured angles moving 1:1 with
    stage tilt (a static clutter structure across a 1 deg sweep step
    shows slope 0 and fails the third check).
    """

    def __init__(self, center_tolerance_px: float,
                 axis_tolerance_frac: float,
                 angle_tolerance_deg: float) -> None:
        self._center_tolerance_px = center_tolerance_px
        self._axis_tolerance_frac = axis_tolerance_frac
        self._angle_tolerance_deg = angle_tolerance_deg
        self.offset_deg: Optional[float] = None
        self._candidate: Optional[_AnchorObservation] = None

    def observe(self, observation: _AnchorObservation
                ) -> Optional[Tuple[_AnchorObservation,
                                    _AnchorObservation]]:
        """Feed one gate-passing fit; returns the confirming pair when
        this observation establishes the anchor, else None. An
        inconsistent observation replaces the candidate (the newest
        evidence wins — a stale candidate must not block forever)."""
        if self.offset_deg is not None:
            return None
        if (self._candidate is not None
                and self._consistent(self._candidate, observation)):
            pair = (self._candidate, observation)
            self.offset_deg = (self._candidate.offset_deg
                               + observation.offset_deg) / 2.0
            self._candidate = None
            return pair
        self._candidate = observation
        return None

    def reset(self) -> None:
        self.offset_deg = None
        self._candidate = None

    def _consistent(self, a: _AnchorObservation,
                    b: _AnchorObservation) -> bool:
        center_px = math.hypot(b.fit.center_x_px - a.fit.center_x_px,
                               b.fit.center_y_px - a.fit.center_y_px)
        if center_px > self._center_tolerance_px:
            return False
        axis_frac = (abs(b.fit.semi_major_px - a.fit.semi_major_px)
                     / max(a.fit.semi_major_px, 1e-9))
        if axis_frac > self._axis_tolerance_frac:
            return False
        # 1:1 slope check: measured angle must move with stage tilt.
        slope_residual_deg = abs(
            (b.fit.milling_angle_deg - a.fit.milling_angle_deg)
            - (b.tilt_deg - a.tilt_deg))
        return slope_residual_deg <= self._angle_tolerance_deg


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
                     Callable[..., Tuple[EllipseFit, ...]]] = None,
                 ) -> None:
        # detect(image, expected) returns per-polarity candidate fits,
        # best score first; the sequence gates them in order and acts
        # on the first acceptable one.
        self._ops = ops
        self._params = params
        self._cfg = config
        self._detect = detect or FiducialEllipseDetector(
            config.detector).detect_all
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
        # Sample-planarity offset (measured - model), anchored once TWO
        # consistent observations confirm the lock.
        self._anchor = _PlanarityAnchor(
            config.anchor_center_tolerance_px,
            config.anchor_axis_tolerance_frac,
            config.anchor_angle_tolerance_deg)
        self._reanchors_used = 0
        # Ring width the run tracks: the entered AOI diameter until the
        # anchor confirms, the measured width afterwards (user
        # decision: report mismatches instead of rejecting the run).
        self._working_aoi_diameter_um = params.aoi_diameter_um
        # Leveling latch: once the ring has been SEEN level, later
        # larger tilt readings are noise, never "corrected".
        self._level_established = False
        self._warnings: list = []
        # Debug frame capture (env override beats the config field)
        debug_dir = os.environ.get(ASV_DEBUG_ENV) or config.debug_frames_dir
        self._debug_dir: Optional[Path] = Path(debug_dir) if debug_dir \
            else None
        self._debug_run_dir: Optional[Path] = None
        self._debug_frames_written = 0

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
        if self._debug_dir is not None:
            self._debug_run_dir = (self._debug_dir
                                   / time.strftime("%Y%m%d-%H%M%S"))
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
            if self._debug_frames_written:
                logger.info("Debug capture: %d frame(s) written to %s",
                            self._debug_frames_written, self._debug_run_dir)

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def _run_inner(self) -> AlignmentResult:
        target_deg = self._params.target_milling_angle_deg
        self._checks(target_deg)
        self._setup()
        fit = self._search()
        round_index = 1
        while round_index <= self._cfg.verify_rounds:
            try:
                fit = self._converge(fit, target_deg)
                verified, fit, detail = self._verify(target_deg)
            except _Reacquired as reacquired:
                # Fresh 2-frame lock after a mid-run blackout: restart
                # convergence cleanly (probes/counters reset) without
                # consuming a verify round. Bounded by reanchor_budget,
                # which was spent before this could be raised.
                fit = reacquired.fit
                continue
            if verified:
                return self._result(
                    AlignmentOutcome.ALIGNED,
                    f"Aligned: {fit.milling_angle_deg:.2f}° milling "
                    "angle, centered and level",
                    fit)
            logger.info("Verification round %d failed: %s",
                        round_index, detail)
            round_index += 1
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
                # Pixel size and geometry change with the field of
                # view: a pending anchor candidate is meaningless.
                self._anchor.reset()
                self._tilt_absolute(start_tilt_deg)
            fit = self._sweep_once(start_tilt_deg, sweep)
            if fit is not None:
                self._status(
                    f"Ellipse found and confirmed at "
                    f"{fit.milling_angle_deg:.2f}° "
                    f"(stage tilt {self._tilt_deg:.1f}°)")
                return fit
        raise _NotFound(
            f"Ellipse not found after {cfg.sweep_count} search sweeps — "
            "check the FIB view, then press Start to retry")

    def _sweep_once(self, start_tilt_deg: float,
                    sweep: int) -> Optional[EllipseFit]:
        """One tilt-toward-0 sweep; returns an ANCHOR-CONFIRMED fit or
        None. A single accepted fit only records an anchor candidate;
        up to two same-tilt confirmation grabs (no stage motion) try to
        confirm it immediately, and otherwise the candidate rides along
        to the next sweep step, where the 1:1 angle/tilt slope check
        does the discriminating."""
        cfg = self._cfg
        tilt_deg = start_tilt_deg
        while True:
            self._status(f"Search sweep {sweep}/{cfg.sweep_count}: "
                         f"looking at stage tilt {tilt_deg:.1f}°...")
            fit = self._measure_once()
            if fit is not None:
                if self._observe_for_anchor(fit):
                    return fit
                for _ in range(2):  # same-tilt confirmation grabs
                    confirm = self._measure_once()
                    if confirm is not None \
                            and self._observe_for_anchor(confirm):
                        return confirm
            next_tilt_deg = tilt_deg + cfg.sweep_step_deg
            next_angle_deg = (next_tilt_deg
                              + FIB_ANGLE_FROM_STAGE_PLANE_DEG)
            if next_angle_deg > cfg.sweep_max_milling_angle_deg:
                return None
            self._tilt_absolute(next_tilt_deg)
            tilt_deg = next_tilt_deg

    def _observe_for_anchor(self, fit: EllipseFit) -> bool:
        """Feed a gate-passing fit to the anchor; True when it
        establishes the 2-frame-confirmed lock."""
        model_deg = self._tilt_deg + FIB_ANGLE_FROM_STAGE_PLANE_DEG
        width_um = 0.0
        if self._last_pixel_size_m > 0:
            width_um = (2.0 * fit.semi_major_px
                        * self._last_pixel_size_m * 1e6)
        pair = self._anchor.observe(_AnchorObservation(
            fit=fit, tilt_deg=self._tilt_deg,
            offset_deg=fit.milling_angle_deg - model_deg,
            width_um=width_um))
        if pair is None:
            return False
        self._finalize_anchor(pair)
        return True

    def _finalize_anchor(self, pair: Tuple[_AnchorObservation,
                                           _AnchorObservation]) -> None:
        """Adopt the confirmed lock: log the offset, switch the run to
        the measured (working) ring width, and advise the operator when
        it disagrees with the entered AOI diameter."""
        logger.info(
            "Planarity offset anchored at %+.2f deg (2-frame confirmed: "
            "%+.2f and %+.2f deg)", self._anchor.offset_deg,
            pair[0].offset_deg, pair[1].offset_deg)
        entered_um = self._params.aoi_diameter_um
        if entered_um <= 0 or pair[0].width_um <= 0:
            return
        working_um = (pair[0].width_um + pair[1].width_um) / 2.0
        self._working_aoi_diameter_um = working_um
        mismatch_frac = abs(working_um - entered_um) / entered_um
        if mismatch_frac > self._cfg.aoi_width_advisory_frac:
            self._warn(
                f"Measured AOI width ≈ {working_um:.0f} µm differs "
                f"from the entered {entered_um:.0f} µm by "
                f"{mismatch_frac * 100:.0f}% — tracking the measured "
                "width")

    def _escalate_hfw(self) -> None:
        """Zoom out for the second sweep, but never past the AOI
        detection band: beyond D/HFW = aoi_hfw_fit_min the ellipse
        falls below the detector's semi-major prior and the sweep
        could not succeed by construction."""
        cfg = self._cfg
        new_hfw_m = self._expected_hfw_m * cfg.hfw_escalation_factor
        aoi_m = self._params.aoi_diameter_um * 1e-6
        if aoi_m > 0:
            new_hfw_m = min(new_hfw_m, aoi_m / cfg.aoi_hfw_fit_min)
        if new_hfw_m <= self._expected_hfw_m * 1.01:
            logger.info("HFW already at the AOI detection-band limit; "
                        "next sweep runs without escalation")
            return
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
        if self._level_established:
            return fit
        self._phase("Scan-rotation leveling",
                    "Leveling the ellipse with FIB scan rotation...")
        probe = _SignProbe("Scan-rotation leveling", cfg.level_sign)
        previous: Optional[float] = None
        for _ in range(cfg.level_max_iterations):
            if abs(fit.tilt_deg) <= cfg.level_noise_floor_deg:
                # The ring has been SEEN level. Its plane rotation
                # cannot change unless we rotate the scan, so leveling
                # is done for this run: later larger readings are
                # measurement noise, and "correcting" them injects
                # real tilt (exactly what the 2026-08 run 1 did).
                self._level_established = True
                logger.info(
                    "Ellipse is level (tilt %.2f deg ≤ %.2f noise "
                    "floor); scan-rotation leveling disabled for this "
                    "run", fit.tilt_deg, cfg.level_noise_floor_deg)
                return fit
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
        # The exit epsilon must be at least the read-back tolerance:
        # _tilt_absolute assigns the stage READ-BACK to self._tilt_deg,
        # accepting up to tilt_readback_tolerance_deg of deviation — a
        # tighter epsilon re-commands the same tilt forever. The cap and
        # stall guard break to the closed loop, which owns convergence.
        epsilon_deg = max(cfg.tilt_readback_tolerance_deg, 0.02)
        max_steps = math.ceil(abs(model_tilt_deg - self._tilt_deg)
                              / cfg.tilt_walk_step_deg) + 2
        for _ in range(max_steps):
            remaining_deg = model_tilt_deg - self._tilt_deg
            if abs(remaining_deg) <= epsilon_deg:
                break
            step_deg = _clamp(remaining_deg, cfg.tilt_walk_step_deg)
            self._status(f"Tilting stage to "
                         f"{self._tilt_deg + step_deg:.1f}°...")
            before_deg = self._tilt_deg
            self._tilt_absolute(self._tilt_deg + step_deg)
            if (abs(step_deg) >= epsilon_deg
                    and abs(self._tilt_deg - before_deg) < epsilon_deg / 2):
                logger.warning(
                    "Tilt walk stalled at %.3f° (commanded step %+.3f°); "
                    "handing over to the closed loop", self._tilt_deg,
                    step_deg)
                fit = self._measure_required()
                fit = self._keep_in_view(fit)
                break
            fit = self._measure_required()
            fit = self._keep_in_view(fit)
        else:
            logger.warning(
                "Tilt walk did not settle within %d steps (at %.3f°, "
                "model %.3f°); handing over to the closed loop",
                max_steps, self._tilt_deg, model_tilt_deg)
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
        frame (including rejected ones, so the operator sees why).
        Candidates are gated best-score first: a garbage fit from one
        ring polarity cannot shadow an acceptable fit from the other."""
        frame = self._grab()
        if not self._frame_usable(frame):
            self._on_frame(frame.data, None, frame.pixel_size_m)
            self._debug_frame(frame, None, "unusable_frame")
            return None
        fits = self._detect(frame.data, self._expected_geometry())
        if not fits:
            self._on_frame(frame.data, None, frame.pixel_size_m)
            self._debug_frame(frame, None, "no_fit")
            return None
        first_reason = None
        for fit in fits:
            reason = self._gate_fit(fit)
            if reason is None:
                self._on_frame(frame.data, fit, frame.pixel_size_m)
                self._debug_frame(frame, fit, "accepted")
                return fit
            if first_reason is None:
                first_reason = reason
        self._on_frame(frame.data, fits[0], frame.pixel_size_m)
        self._debug_frame(frame, fits[0], f"rejected: {first_reason}")
        return None

    def _expected_geometry(self) -> Optional[ExpectedGeometry]:
        """Physical-model priors for the detector. The AOI diameter
        pins the semi-major axis (tilt-invariant); the acceptance
        angle window pins the axis-ratio band, excluding degenerate
        flat hypotheses inside RANSAC so the true ring wins the fit.
        None when the AOI is unknown (checks-disabled mode)."""
        aoi_um = self._working_aoi_diameter_um
        if aoi_um <= 0 or self._last_pixel_size_m <= 0:
            return None
        semi_major_px = (aoi_um * 1e-6 / 2.0) / self._last_pixel_size_m
        low_deg, high_deg = self._angle_window_deg()
        detector_cfg = self._cfg.detector
        ratio_low = max(math.sin(math.radians(max(low_deg, 0.5))),
                        detector_cfg.min_axis_ratio)
        ratio_high = min(math.sin(math.radians(min(high_deg, 20.0))),
                         detector_cfg.max_axis_ratio)
        if ratio_high <= ratio_low:
            ratio_low = detector_cfg.min_axis_ratio
            ratio_high = detector_cfg.max_axis_ratio
        # The ring's image tilt tracks the applied scan rotation 1:1
        # (verified on the real corpus; tracking sign is instrument-
        # dependent, so the bound is symmetric): intrinsic ring
        # rotation headroom plus whatever rotation this run applied.
        max_abs_tilt_deg = (_INTRINSIC_RING_TILT_HEADROOM_DEG
                            + abs(self._ops.ion_beam.scan_rotation_deg()))
        return ExpectedGeometry(semi_major_px=semi_major_px,
                                axis_ratio=(ratio_low, ratio_high),
                                max_abs_tilt_deg=max_abs_tilt_deg)

    def _angle_window_deg(self) -> Tuple[float, float]:
        """Acceptance window for the measured milling angle, shared by
        the detector prior and the plausibility gate so the two can
        never disagree. Before FOUND: the wide search window around
        the raw model (sample planarity unknown). After FOUND: a
        tighter window around the planarity-anchored model."""
        model_deg = self._tilt_deg + FIB_ANGLE_FROM_STAGE_PLANE_DEG
        if self._anchor.offset_deg is None:
            window_deg = self._cfg.plausibility_window_deg
            return (model_deg - window_deg, model_deg + window_deg)
        window_deg = self._cfg.plausibility_window_tracking_deg
        center_deg = model_deg + self._anchor.offset_deg
        return (center_deg - window_deg, center_deg + window_deg)

    def _debug_frame(self, frame: FibFrame, fit: Optional[EllipseFit],
                     verdict: str) -> None:
        """Write the grabbed frame (native dtype PNG) plus a JSON
        sidecar for offline analysis and simulator replay. Never fatal:
        the first write failure disables capture for the rest of the
        run. No retention policy — per-run subfolders keep manual
        cleanup trivial."""
        if self._debug_run_dir is None:
            return
        try:
            self._debug_run_dir.mkdir(parents=True, exist_ok=True)
            stem = f"frame_{self._frames:04d}"
            cv2.imwrite(str(self._debug_run_dir / f"{stem}.png"),
                        frame.data)
            fit_map = None
            if fit is not None:
                fit_map = asdict(fit)
                fit_map["milling_angle_deg"] = fit.milling_angle_deg
            sidecar = {
                "schema": 2,
                "frame_index": self._frames,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "phase": self._phase_label,
                "stage_tilt_deg": self._tilt_deg,
                "model_milling_angle_deg": (
                    self._tilt_deg + FIB_ANGLE_FROM_STAGE_PLANE_DEG),
                "planarity_offset_deg": self._anchor.offset_deg,
                "working_aoi_diameter_um": self._working_aoi_diameter_um,
                "reanchors_used": self._reanchors_used,
                "target_milling_angle_deg": (
                    self._params.target_milling_angle_deg),
                "aoi_diameter_um": self._params.aoi_diameter_um,
                "hfw_m": frame.hfw_m,
                "pixel_size_m": frame.pixel_size_m,
                "scan_rotation_deg": self._ops.ion_beam.scan_rotation_deg(),
                "frame_shape": list(frame.data.shape),
                "frame_dtype": str(frame.data.dtype),
                "verdict": verdict,
                "fit": fit_map,
            }
            (self._debug_run_dir / f"{stem}.json").write_text(
                json.dumps(sidecar, indent=2))
            self._debug_frames_written += 1
        except Exception:
            logger.exception("Debug frame capture failed; disabling it "
                             "for the rest of this run")
            self._debug_run_dir = None

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

    def _measure_ladder(self) -> Optional[EllipseFit]:
        """Plain re-grabs, then one auto-C/B rescue."""
        for _ in range(1 + self._cfg.detection_retries):
            fit = self._measure_once()
            if fit is not None:
                return fit
        logger.info("Detection lost; running auto contrast/brightness "
                    "and retrying once")
        self._check_stop()
        self._ops.imaging.run_auto_cb()
        return self._measure_once()

    def _measure_required(self) -> EllipseFit:
        """Measurement with the recovery ladder. When the ladder fails
        post-anchor, a bounded re-anchor attempt clears the lock —
        which also reverts the detector prior and gates to the wide
        search window, re-admitting a ring a poisoned anchor excluded —
        and demands a fresh 2-frame confirmation. Success restarts
        convergence via _Reacquired; exhaustion is NOT_FOUND."""
        fit = self._measure_ladder()
        if fit is not None:
            return fit
        cfg = self._cfg
        while self._reanchors_used < cfg.reanchor_budget:
            self._reanchors_used += 1
            self._warn(
                f"Detection lost — re-acquiring the ellipse (attempt "
                f"{self._reanchors_used}/{cfg.reanchor_budget})")
            previous_offset = self._anchor.offset_deg
            self._anchor.reset()
            # Full lock-trust reset: a poisoned lock may carry a
            # poisoned width.
            self._working_aoi_diameter_um = self._params.aoi_diameter_um
            fit = self._acquire_lock_in_place()
            if fit is not None:
                was = (f"{previous_offset:+.2f}°"
                       if previous_offset is not None else "none")
                self._warn(
                    f"Re-anchored at {self._anchor.offset_deg:+.2f}° "
                    f"(was {was})")
                raise _Reacquired(fit)
        raise _NotFound("Ellipse lost during alignment — re-acquisition "
                        "failed; check the FIB view, then press Start "
                        "to retry")

    def _acquire_lock_in_place(self) -> Optional[EllipseFit]:
        """Bounded same-tilt re-acquisition: two grabs, one auto-C/B,
        two more grabs, each accepted fit feeding the (cleared) anchor
        until a 2-frame confirmation lands."""
        for attempt in range(4):
            if attempt == 2:
                self._check_stop()
                self._ops.imaging.run_auto_cb()
            fit = self._measure_once()
            if fit is not None and self._observe_for_anchor(fit):
                return fit
        return None

    def _gate_fit(self, fit: EllipseFit) -> Optional[str]:
        """None when the fit passes every gate, else the rejection
        reason (logged here, and recorded in the debug sidecar)."""
        cfg = self._cfg
        # rms scales with the detector's width-rescaled inlier
        # tolerance, so the ceiling must follow the frame width too.
        width_px = (self._last_frame_shape[1]
                    or cfg.detector.reference_width_px)
        max_rms_px = (cfg.fit_max_rms_px
                      * width_px / cfg.detector.reference_width_px)
        if (fit.n_inliers < cfg.fit_min_inliers
                or fit.coverage < cfg.fit_min_coverage
                or fit.rms_px > max_rms_px):
            reason = (f"quality inliers={fit.n_inliers} "
                      f"coverage={fit.coverage:.2f} rms={fit.rms_px:.2f}")
            logger.info("Fit rejected by quality gates: inliers=%d "
                        "coverage=%.2f rms=%.2f", fit.n_inliers,
                        fit.coverage, fit.rms_px)
            return reason
        low_deg, high_deg = self._angle_window_deg()
        if not low_deg <= fit.milling_angle_deg <= high_deg:
            logger.info(
                "Fit rejected as implausible: measured %.2f deg vs "
                "window [%.2f, %.2f] deg at stage tilt %.2f deg",
                fit.milling_angle_deg, low_deg, high_deg, self._tilt_deg)
            return (f"implausible measured={fit.milling_angle_deg:.2f} "
                    f"window=[{low_deg:.2f}, {high_deg:.2f}]")
        if self._anchor.offset_deg is None:
            # Anchor-candidate plausibility cap, STRICTER than the
            # search window and applied in the gate so the best-first
            # candidate iteration falls through a persistent decoy to
            # the true ring (run 1's -2.97 deg clutter passed the
            # window and would have anchored again).
            model_deg = self._tilt_deg + FIB_ANGLE_FROM_STAGE_PLANE_DEG
            offset_deg = fit.milling_angle_deg - model_deg
            if abs(offset_deg) > cfg.anchor_max_offset_deg:
                logger.info(
                    "Fit rejected as an anchor candidate: implied "
                    "planarity offset %+.2f deg exceeds the %.1f deg "
                    "cap", offset_deg, cfg.anchor_max_offset_deg)
                return (f"anchor_offset {offset_deg:+.2f} deg exceeds "
                        f"±{cfg.anchor_max_offset_deg:.1f}")
        if self._last_pixel_size_m > 0:
            width_um = (2.0 * fit.semi_major_px
                        * self._last_pixel_size_m * 1e6)
            entered_um = self._params.aoi_diameter_um
            if self._anchor.offset_deg is None:
                # The major axis is the true AOI diameter, so measured
                # width vs the user's entry is an independent
                # false-detection gate at lock time.
                if entered_um > 0 and abs(width_um - entered_um) \
                        > cfg.aoi_width_tolerance_frac * entered_um:
                    logger.info(
                        "Fit rejected by the AOI width gate: measured "
                        "width %.0f um vs expected %.0f um", width_um,
                        entered_um)
                    return (f"aoi_width {width_um:.0f} um vs "
                            f"expected {entered_um:.0f} um")
            elif self._working_aoi_diameter_um > 0:
                # Post-anchor the run tracks the measured (working)
                # width; the band derives from the detector's own
                # semi-major prior tolerance so the gate and the prior
                # can never disagree.
                working_um = self._working_aoi_diameter_um
                tolerance_frac = \
                    cfg.detector.expected_semi_major_tolerance_frac
                if abs(width_um - working_um) \
                        > tolerance_frac * working_um:
                    logger.info(
                        "Fit rejected by the AOI width gate: measured "
                        "width %.0f um vs working %.0f um", width_um,
                        working_um)
                    return (f"aoi_width {width_um:.0f} um vs "
                            f"working {working_um:.0f} um")
        return None

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

    def _warn(self, text: str) -> None:
        """Operator advisory: live status line now, and collected onto
        the AlignmentResult for the end-of-run surface."""
        logger.warning("%s", text)
        self._on_status(f"Warning: {text}")
        self._warnings.append(text)

    def _result(self, outcome: AlignmentOutcome, message: str,
                fit: Optional[EllipseFit] = None) -> AlignmentResult:
        self._status(message)
        return AlignmentResult(
            outcome=outcome, message=message, final_fit=fit,
            frames_grabbed=self._frames, tilt_moves=self._tilt_moves,
            center_moves=self._center_moves,
            warnings=tuple(self._warnings))


def _clamp(value: float, magnitude: float) -> float:
    return max(-magnitude, min(magnitude, value))
