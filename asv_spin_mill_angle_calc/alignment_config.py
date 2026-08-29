"""Tunables for the Position Alignment automation (Qt-free).

Every knob the alignment sequence uses lives in this one frozen
dataclass, following the ``EllipseDetectorConfig`` idiom, so hardware
shakedown is config-only: direction signs, tolerances, iteration caps,
and the search-sweep shape are all adjusted here without touching the
sequence logic.

The defaults encode the safeguards from the design review:

* The tilt tolerance floor comes from measurement physics — at the
  instrument's 1536 px frames the fit's angle sensitivity is ~0.11 deg
  per pixel of semi-minor error at a 4 deg target, and the closed tilt
  loop decides on a median of tilt_measure_frames fits (~0.02-0.03 deg
  median noise), so tolerances below ~3x that noise would make the
  loop chase noise forever. The floor is enforced at construction.
* The hard tilt floor (-37.9 deg) is a user requirement: stage tilts at
  or beyond -38 deg (a zero milling angle) abort the run with a dialog.
* Bounded actuation (per-step clamps, total caps) means no single fit —
  however plausible — can command a large move.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from asv_spin_mill_angle_calc.ellipse_detector import (
    REFINE_SEMI_MAJOR_GUARD_FRAC,
    EllipseDetectorConfig,
)


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
    # Zoom-out between sweeps; the sequence additionally clamps the
    # escalated HFW to aoi / aoi_hfw_fit_min so the ellipse stays
    # inside the detector's size band (a larger factor pushes it out).
    hfw_escalation_factor: float = 1.4
    # Fit acceptance gates (never act on an ungated fit)
    fit_min_inliers: int = 40
    fit_min_coverage: float = 0.30
    fit_max_rms_px: float = 1.5
    # Measured angle must sit within this window of the open-loop model
    # (stage tilt + 38); wilder values are treated as failed detections,
    # not as giant corrections. Sized to plausible sample planarity.
    plausibility_window_deg: float = 4.0
    # Once the search has found the ellipse, the sample-planarity offset
    # is anchored (measured - model) and subsequent fits must sit in this
    # tighter window around the anchored model — wide enough for the
    # 1 deg sweep steps and measurement jitter, tight enough to reject
    # the degenerate flat fits real frames produce.
    plausibility_window_tracking_deg: float = 2.0
    # Anchor hardening: the anchor requires two consistent observations
    # — same center, same semi-major, and angles moving 1:1 with stage
    # tilt across sweep steps — so a single unverified clutter fit
    # cannot poison the anchor and make the true ring inadmissible for
    # the rest of the run. An anchor-candidate fit whose implied
    # planarity offset exceeds the cap is rejected outright (genuinely
    # warped samples up to the cap still anchor). Pair-consistency
    # tolerances are sized so bad anchors separate from healthy ones by
    # pair disagreement (axis and center deltas several times the
    # healthy worst case), not by fit quality; coverage does not
    # discriminate — low-coverage runs have produced some of the most
    # accurate widths — so there is deliberately no coverage gate here.
    # Failing a pair is cheap: the newest observation replaces the
    # candidate and the sweep's two extra same-tilt grabs re-confirm.
    anchor_center_tolerance_px: float = 10.0
    anchor_axis_tolerance_frac: float = 0.01
    anchor_angle_tolerance_deg: float = 0.5
    anchor_max_offset_deg: float = 2.5
    # Mid-run re-anchor attempts after the post-anchor measurement
    # ladder fails (detection blackout or a poisoned anchor): each
    # attempt clears the anchor — which also reverts the detector
    # prior to the wide search window — and demands a fresh 2-frame
    # confirmation before the run continues.
    reanchor_budget: int = 1
    # AOI width gate: the ellipse's major axis is the true AOI diameter
    # (foreshortening only shrinks the minor axis), so a fit whose
    # measured width disagrees with the user-entered diameter by more
    # than this fraction is rejected as a false detection. Generous on
    # purpose — a wrong user entry should not doom obviously-good fits.
    # Applies against the entered diameter until the anchor is
    # confirmed; after that the measured (working) width takes over,
    # gated by the detector's own semi-major tolerance instead.
    aoi_width_tolerance_frac: float = 0.10
    # When the confirmed ring width differs from the entered AOI
    # diameter by more than this fraction, the run continues on the
    # measured width and the operator gets an advisory (user decision:
    # prioritize finding the ellipse; report mismatches, don't die).
    # Sized as an early warning for the detector's refinement cliff at
    # REFINE_SEMI_MAJOR_GUARD_FRAC (8%): inside the cliff the free fit
    # recovers the true width and the reported angle barely moves
    # (verified: +/-4.5% of pinned width shifts the angle <= 0.04 deg),
    # but past it the fit reverts to the pinned vote lock and the angle
    # inherits the width error in full. 0.02 fires on real mismatches
    # (~3%) while staying silent on healthy runs (<= 0.7% observed).
    # Validated below to stay under the cliff.
    aoi_width_advisory_frac: float = 0.02
    # Wrong-AOI-entry advisory: with a wrong AOI Diameter entry the
    # width gate can be the only gate rejecting fits, and bare repeated
    # failures read to the operator as broken alignment. The first
    # pre-anchor width rejection of a run puts measured-vs-entered in
    # the status line immediately; once this many consecutive
    # rejections carry consistent widths, the run escalates to a
    # collected warning naming the AOI Diameter entry.
    aoi_advisory_min_rejections: int = 2
    # Two rejected widths are "consistent" when they agree within this
    # fraction — inconsistent widths mean clutter, not a wrong entry.
    aoi_advisory_consistency_frac: float = 0.05
    # Field-of-view fit band: the detector wants the semi-major axis
    # within (0.25, 0.60) of image width, i.e. D/HFW within (0.5, 1.2).
    # Outside it, setup adjusts HFW to D / aoi_hfw_target_ratio (band
    # center) and restores the operator's HFW at the end of the run.
    aoi_hfw_fit_min: float = 0.5
    aoi_hfw_fit_max: float = 1.2
    aoi_hfw_target_ratio: float = 0.8
    # Closed tilt loop. 0.10 deg: real site planarity within one
    # rosette spans several tenths of a degree at a single stage tilt,
    # so a looser tolerance lets sites mill 0.25 deg low with no flag.
    # The loop decides on a median of tilt_measure_frames fits
    # (~0.02-0.03 deg noise), so 0.10 is 3-5x the acting noise; the
    # floor tracks the 1536-px frames' ~0.11 deg/px angle sensitivity.
    tilt_tolerance_deg: float = 0.10
    tilt_tolerance_floor_deg: float = 0.10
    tilt_max_iterations: int = 5
    tilt_walk_step_deg: float = 2.0         # open-loop walk toward target
    # Frames per closed-tilt-loop measurement: the per-iteration verdict
    # is the median angle of this many ladder measurements (same rule as
    # verification). Must be odd; 1 selects single-frame measurement.
    # Only correcting iterations pay the extra grabs — a site already
    # at target exits on the walk's own fit.
    tilt_measure_frames: int = 3
    # Centering loop (tolerances as fractions of HFW, floored at 3 px).
    # The tolerance is applied per axis in image space: a combined hypot
    # lets a converged X mask a broken Y. 0.005 (= 7.7 px / 3.7 um at
    # HFW 748 um) is tight enough that a site genuinely off by ~10 um
    # cannot verify, yet still 5.5-38x the measured 0.2-1.4 px
    # within-run center scatter, and X actuation nulls 56 um to 0.4 um
    # in one move, so the cost is one extra move.
    center_tolerance_frac_of_hfw: float = 0.005
    # Beam trim must be at least as tight as the stage exit. 0.004 is
    # the practical floor: at the simulator's 768 px frames the 3-px
    # minimum equals frac 0.0039, so anything lower makes this knob
    # inert in tests.
    center_tolerance_beam_frac_of_hfw: float = 0.004
    # Six, not five: a wrong stage sign costs the probe one move to
    # detect and one to reverse, and the loop validates the last
    # move's result instead of raising on it.
    center_max_iterations: int = 6
    keep_in_view_frac: float = 0.15         # recenter trigger mid-walk
    # Stage-Y de-projection. At a grazing milling angle beta the FIB
    # image foreshortens specimen-plane Y by sin(beta) (~0.07 at
    # 4 deg) — the same projection that turns the circular AOI into an
    # ellipse with b/a = sin(beta). Without de-projection, stage-Y
    # corrections land ~14x short and vertical centering never
    # converges.
    #
    # This flag governs both the de-projection and the per-axis exit
    # above: they are one physical fix. Enabling the per-axis exit
    # alone would turn silently-passing runs into NOT_CONVERGED, and
    # de-projecting without it leaves the combined hypot masking the
    # result. Ships enabled: the projection physics is instrument-
    # proven, every move is capped (stage_move_max_m,
    # center_offset_max_frac_of_hfw) and the sign probe self-corrects.
    # Flipping this False is the instant full revert to the
    # un-de-projected arithmetic.
    stage_y_deprojection_enabled: bool = True
    # Floor on the grazing angle feeding sin(beta), capping the Y gain
    # at 1/sin(2 deg) = 28.6x. Matches min_target_angle_deg: below it
    # the ellipse is too flat to measure anyway.
    deprojection_min_angle_deg: float = 2.0
    # Per-move cap on the commanded specimen-plane move (applied to the
    # hypot by uniform scaling, so direction is preserved). ~8x the
    # largest legitimate correction observed (a 10 px residual
    # de-projects to ~65 um); bounds a 100-px-class bad fit to one
    # recoverable move rather than a blind lunge.
    stage_move_max_m: float = 5.0e-4
    # Image-space sanity ceiling on the measured center offset: beyond
    # this fraction of HFW the fit is treated as a failed detection (the
    # recovery ladder re-measures) rather than as a move. The worst
    # legitimate offset observed is 0.042 of HFW, so this is ~8x
    # headroom.
    center_offset_max_frac_of_hfw: float = 0.35
    # Beam-shift trim iterations. Two bounded iterations with per-axis
    # probes let an inverted sign self-correct (see beam_shift_sign_y)
    # at the cost of at most one extra grab — measured trims reach
    # 81-94% of the commanded move in one step.
    beam_max_iterations: int = 2
    # Scan-rotation leveling loop. 0.30: looser tolerances leave real,
    # repeatable ~0.4 deg tilts that operators end up correcting by
    # hand. 0.30/0.20 rather than tighter: the steepest
    # legitimately-level site observed reads 0.21-0.23 deg, so 0.30
    # keeps it 3.5 sigma inside tolerance (at 0.25 it would sit one
    # noise-width from flapping a verification round), and 0.20 still
    # latches most level sites on their first fit.
    level_tolerance_deg: float = 0.30
    level_max_iterations: int = 5
    level_step_clamp_deg: float = 10.0
    # Leveling noise-floor latch: once any gated fit measures |tilt| at
    # or under this, the ring has been seen level — its plane rotation
    # cannot change unless we rotate the scan, so leveling is skipped
    # for the rest of the run and later larger readings are treated as
    # measurement noise, never "corrected" ("correcting" an
    # already-level ring only injects real tilt). The in-tolerance
    # exit latches too (see _level_loop), so this threshold's
    # remaining job is latching on the first fit.
    level_noise_floor_deg: float = 0.20
    # Detection recovery ladder (per measurement: re-grabs, then one
    # auto contrast-brightness rescue)
    detection_retries: int = 1
    # Converge+verify rounds (verification failure re-enters converge
    # once before reporting NOT_CONVERGED)
    verify_rounds: int = 2
    # Frames per verification round: centering and leveling are checked
    # on every frame, the angle verdict is the round's median angle.
    # Must be odd (validated): an even count would let the upper-middle
    # frame decide the verdict alone — exactly the single-noisy-fit
    # failure the median exists to prevent.
    verify_frames: int = 3
    # Direction signs — the loops probe and self-correct once, but the
    # confirmed instrument conventions belong here after shakedown.
    # The simulator implements the all-(+1) convention, so
    # simulator-backed tests pass level_sign=+1.0 explicitly.
    tilt_sign: float = 1.0
    stage_sign_x: float = 1.0
    # stage_sign_y is instrument-proven -1: independent measurements of
    # the stage-Y -> image response — centering moves plus a
    # crosstalk-free eucentric compensation at exactly 180 scan
    # rotation — all came back positive (~+0.077, matching
    # sin 4 deg = 0.070 in magnitude) where the loop assumes negative,
    # and with +1 the de-projected closed loop diverges, pushing the
    # ellipse away by ~110% of each residual. Hard-coded rather than
    # left to the probe because the probe is structurally blind here:
    # X nulls in one move, the small |dy| sits inside the per-axis
    # tolerance, and _recenter_loop exits before probe_y ever runs
    # (verified in sim: a wrong sign silently doubles a 25 um Y error
    # and still reports ALIGNED). Hard-coding also fixes _keep_in_view
    # and the beam-spill path, which use this raw value, never the
    # probe-corrected sign. The simulator implements the all-(+1)
    # convention, so simulator-backed tests pass stage_sign_y=+1.0
    # explicitly.
    stage_sign_y: float = -1.0
    beam_shift_sign_x: float = 1.0
    # beam_shift_sign_y is instrument-proven -1: beam trims moved the
    # ellipse away from center vertically at 90-94% of the commanded
    # magnitude, while X in the very same moves went the right way at
    # 81-86%. Beam shift acts in the beam plane and is not
    # foreshortened, so a correct magnitude with a wrong direction is
    # the classic image-Y-down vs beam-shift-Y-up handedness flip.
    # The simulator implements the all-(+1) convention, so
    # simulator-backed tests pass beam_shift_sign_y=+1.0 explicitly.
    beam_shift_sign_y: float = -1.0
    # level_sign is instrument-proven -1: with +1, applying a
    # scan-rotation "correction" doubles the measured ellipse tilt —
    # the classic inverted-sign signature. The probe still recovers a
    # wrong sign once either way.
    level_sign: float = -1.0
    # Beam shift clamp when the SDK limits are unreadable
    beam_shift_fallback_limit_m: float = 45.0e-6
    # Run guards
    hfw_change_abort_frac: float = 0.05     # external HFW change aborts
    tilt_readback_tolerance_deg: float = 0.05
    xy_readback_tolerance_m: float = 2.0e-6
    # Debug frame capture: when non-empty, every grabbed frame is saved
    # under <debug_frames_dir>/<run timestamp>/ as a native-bit-depth
    # PNG plus a JSON sidecar (stage state, fit, gate verdict). The
    # normal way to enable capture is the Settings page's "Save Debug
    # Images" checkbox, which routes DEFAULT_DEBUG_FRAMES_DIR (below)
    # into this field per run — a hand-edited value here is superseded
    # whenever that wiring is active (i.e. in the real app). The
    # ASV_DEBUG_FRAMES_DIR environment variable overrides both.
    # Write failures disable capture for the run, never abort it. No
    # retention policy: the operator deletes run folders manually.
    debug_frames_dir: str = ""
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
        if not 0 < self.anchor_max_offset_deg \
                <= self.plausibility_window_deg:
            raise ValueError(
                "anchor_max_offset_deg must sit inside the search "
                "plausibility window — the cap is a stricter subset of "
                "the gate, never a widening")
        if self.anchor_angle_tolerance_deg >= self.sweep_step_deg:
            raise ValueError(
                "anchor_angle_tolerance_deg must be smaller than the "
                "sweep step, or static clutter across a sweep step "
                "could pass the 1:1 angle-tracking consistency check")
        if self.reanchor_budget < 0:
            raise ValueError("reanchor_budget cannot be negative")
        if not 0 < self.deprojection_min_angle_deg \
                <= self.min_target_angle_deg:
            raise ValueError(
                "deprojection_min_angle_deg must be positive and no "
                "larger than min_target_angle_deg — it is the floor that "
                "caps the de-projection gain, not a second opinion on "
                "the measurable window")
        if self.stage_move_max_m <= 0:
            raise ValueError("stage_move_max_m must be positive")
        if not 0 < self.center_offset_max_frac_of_hfw <= 1.0:
            raise ValueError(
                "center_offset_max_frac_of_hfw must be a fraction of "
                "HFW in (0, 1]")
        if self.beam_max_iterations < 1:
            raise ValueError("beam_max_iterations must be at least 1")
        if self.tilt_measure_frames < 1 \
                or self.tilt_measure_frames % 2 == 0:
            raise ValueError(
                f"tilt_measure_frames {self.tilt_measure_frames} must be "
                "a positive odd count — with an even count the 'median' "
                "is the upper-middle frame, so one noisy fit decides the "
                "iteration")
        if self.aoi_advisory_min_rejections < 1:
            raise ValueError(
                "aoi_advisory_min_rejections must be at least 1")
        if not 0 < self.aoi_advisory_consistency_frac < 1:
            raise ValueError(
                "aoi_advisory_consistency_frac must be a fraction "
                "in (0, 1)")
        if self.verify_frames < 1 or self.verify_frames % 2 == 0:
            raise ValueError(
                f"verify_frames {self.verify_frames} must be a positive "
                "odd count — with an even count the 'median' is the "
                "upper-middle frame, so one noisy fit decides the round")
        if not 0 <= self.level_noise_floor_deg <= self.level_tolerance_deg:
            raise ValueError(
                "level_noise_floor_deg must sit within the leveling "
                "tolerance — a floor above it would skip real leveling")
        if not 0 < self.aoi_width_advisory_frac \
                <= self.aoi_width_tolerance_frac:
            raise ValueError(
                "aoi_width_advisory_frac must sit within the width "
                "gate tolerance — advising about widths the gate would "
                "reject is a contradiction")
        if self.aoi_width_advisory_frac >= REFINE_SEMI_MAJOR_GUARD_FRAC:
            raise ValueError(
                f"aoi_width_advisory_frac "
                f"{self.aoi_width_advisory_frac} must fire before the "
                f"detector's semi-major refinement cliff "
                f"({REFINE_SEMI_MAJOR_GUARD_FRAC}) — past that the free "
                "fit is rejected and the reported angle inherits the "
                "pinned width's error with no operator warning")


DEFAULT_ALIGNMENT_CONFIG = AlignmentConfig()

# Canonical on-repo debug capture location (gitignored). The Settings
# page's "Save Debug Images" checkbox routes capture here via
# PositionAlignmentController's debug_dir_provider;
# DEFAULT_ALIGNMENT_CONFIG itself stays pure (empty).
DEFAULT_DEBUG_FRAMES_DIR = str(
    Path(__file__).resolve().parents[1] / "debug_frames_dir")


# --- Developer / Testing Overrides ------------------------------------------
#
# Ship-as-False source toggles: flip one locally to exercise a path, then
# flip it back. Never commit a True.
#
# DEV_FORCE_SIMULATION:
#   Makes the Connect switch produce the simulated microscope client
#   instead of AutoScript — equivalent to setting the
#   ASV_SIMULATED_MICROSCOPE=1 environment variable (either one selects
#   simulation; read by microscope_client.create_client() at connect
#   time). The session is visibly badged "(sim)" in the UI either way.
DEV_FORCE_SIMULATION: bool = False
