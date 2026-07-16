"""Tunables for the Position Alignment automation (Qt-free).

Every knob the alignment sequence uses lives in this one frozen
dataclass, following the ``EllipseDetectorConfig`` idiom, so hardware
shakedown is config-only: direction signs, tolerances, iteration caps,
and the search-sweep shape are all adjusted here without touching the
sequence logic.

The defaults encode the safeguards from the design review:

* The tilt tolerance floor comes from measurement physics — the fit's
  angle sensitivity is roughly 0.23 deg per pixel of semi-minor error at
  a 4 deg target, so tolerances below ~2x the per-frame noise would make
  the loop chase noise forever. The floor is enforced at construction.
* The hard tilt floor (-37.9 deg) is a user requirement: stage tilts at
  or beyond -38 deg (a zero milling angle) abort the run with a dialog.
* Bounded actuation (per-step clamps, total caps) means no single fit —
  however plausible — can command a large move.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from asv_spin_mill_angle_calc.ellipse_detector import EllipseDetectorConfig


@dataclass(frozen=True)
class AlignmentConfig:
    """Tunables and safeguards for one alignment run."""
    # Imaging / view
    fib_view: int = 2                       # xT quadrant the FIB occupies
    settle_delay_s: float = 1.0             # stage settle before each grab
    # Valid target-milling-angle window: below ~2 deg the ellipse is too
    # flat to measure; above ~18 deg the detector's axis-ratio prior
    # (asin(0.35) ~ 20.5 deg) rejects genuine ellipses.
    min_target_angle_deg: float = 2.0
    max_target_angle_deg: float = 18.0
    # Tilt safety (user requirement: never command tilt at/below -37.9)
    tilt_floor_deg: float = -37.9
    tilt_step_clamp_deg: float = 2.0        # max single closed-loop step
    # Search sweep (tilt toward 0, never more negative)
    sweep_step_deg: float = 1.0
    sweep_max_milling_angle_deg: float = 18.0
    sweep_count: int = 2                    # sweeps before NOT_FOUND
    hfw_escalation_factor: float = 2.0      # zoom-out between sweeps
    # Fit acceptance gates (never act on an ungated fit)
    fit_min_inliers: int = 40
    fit_min_coverage: float = 0.30
    fit_max_rms_px: float = 1.5
    # Measured angle must sit within this window of the open-loop model
    # (stage tilt + 38); wilder values are treated as failed detections,
    # not as giant corrections. Sized to plausible sample planarity.
    plausibility_window_deg: float = 4.0
    # AOI width gate: the ellipse's MAJOR axis is the true AOI diameter
    # (foreshortening only shrinks the minor axis), so a fit whose
    # measured width disagrees with the user-entered diameter by more
    # than this fraction is rejected as a false detection. Generous on
    # purpose — a wrong user entry should not doom obviously-good fits.
    aoi_width_tolerance_frac: float = 0.10
    # Field-of-view fit band: the detector wants the semi-major axis
    # within (0.25, 0.60) of image width, i.e. D/HFW within (0.5, 1.2).
    # Outside it, setup adjusts HFW to D / aoi_hfw_target_ratio (band
    # center) and restores the operator's HFW at the end of the run.
    aoi_hfw_fit_min: float = 0.5
    aoi_hfw_fit_max: float = 1.2
    aoi_hfw_target_ratio: float = 0.8
    # Closed tilt loop
    tilt_tolerance_deg: float = 0.5
    tilt_tolerance_floor_deg: float = 0.25
    tilt_max_iterations: int = 5
    tilt_walk_step_deg: float = 2.0         # open-loop walk toward target
    # Centering loop (tolerances as fractions of HFW, floored at 3 px)
    center_tolerance_frac_of_hfw: float = 0.02
    center_tolerance_beam_frac_of_hfw: float = 0.01
    center_max_iterations: int = 5
    keep_in_view_frac: float = 0.15         # recenter trigger mid-walk
    # Scan-rotation leveling loop
    level_tolerance_deg: float = 0.5
    level_max_iterations: int = 5
    level_step_clamp_deg: float = 10.0
    # Detection recovery ladder (per measurement: re-grabs, then one
    # auto-CB rescue)
    detection_retries: int = 1
    # Converge+verify rounds (verification failure re-enters converge
    # once before reporting NOT_CONVERGED)
    verify_rounds: int = 2
    # Direction signs — the loops probe and self-correct once, but the
    # confirmed instrument conventions belong here after shakedown.
    # The simulator implements the all-(+1) convention.
    tilt_sign: float = 1.0
    stage_sign_x: float = 1.0
    stage_sign_y: float = 1.0
    beam_shift_sign_x: float = 1.0
    beam_shift_sign_y: float = 1.0
    level_sign: float = 1.0
    # Beam shift clamp when the SDK limits are unreadable
    beam_shift_fallback_limit_m: float = 45.0e-6
    # Run guards
    hfw_change_abort_frac: float = 0.05     # external HFW change aborts
    tilt_readback_tolerance_deg: float = 0.05
    xy_readback_tolerance_m: float = 2.0e-6
    # Frame sanity guard: near-black, saturated, or flat (contrast-less)
    # frames never reach the detector — they count as failed detections,
    # so the recovery ladder's auto-C/B gets a chance to fix them.
    # Fractions of the frame dtype's full scale.
    frame_min_mean_frac: float = 0.02
    frame_max_mean_frac: float = 0.98
    frame_min_std_frac: float = 0.005
    detector: EllipseDetectorConfig = field(
        default_factory=EllipseDetectorConfig)

    def __post_init__(self) -> None:
        if self.tilt_tolerance_deg < self.tilt_tolerance_floor_deg:
            raise ValueError(
                f"tilt_tolerance_deg {self.tilt_tolerance_deg} is below "
                f"the {self.tilt_tolerance_floor_deg} floor — tolerances "
                "under the measurement noise oscillate forever")
        if self.sweep_step_deg <= 0:
            raise ValueError("sweep_step_deg must be positive (the sweep "
                             "only ever tilts toward 0)")
        if not 1 <= self.fib_view <= 4:
            raise ValueError("fib_view must be an xT quadrant (1-4)")


DEFAULT_ALIGNMENT_CONFIG = AlignmentConfig()
