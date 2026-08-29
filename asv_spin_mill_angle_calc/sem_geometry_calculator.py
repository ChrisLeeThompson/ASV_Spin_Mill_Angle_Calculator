"""SEM geometry calculations for sample alignment.

The calculator analyses a set of FIB spin mill position images — each
captured at a different stage rotation, with the stage tilt adjusted by
the user to hold the milled fiducial ellipse height constant — and
computes the stage rotation and stage tilt required to bring the sample
surface normal parallel to the SEM beam (+Z).

The Approach
------------
At every (stage rotation, stage tilt) the FIB sees the sample with a
constant milling angle (the user's target milling angle, alpha). Because
the constant-alpha constraint pins the FIB-to-surface angle, the
recorded FIB scan rotation as a function of stage rotation traces out a
sinusoid whose two zero crossings, ~180 degrees apart, are the stage
rotations at which the sample surface normal lies in the FIB-SEM plane.
At those rotations the only remaining degree of freedom is stage tilt,
and a closed-form correction (38 deg - alpha) brings the normal to +Z.

The calculator fits scan rotation vs stage rotation as a linear least-
squares sinusoid in the sin/cos basis (no nonlinear initial guesses
needed), fits stage tilt vs stage rotation the same way, and at each
candidate zero crossing evaluates theta_final = theta_star + (38 - alpha).
The primary candidate is the one with the smaller |theta_final|; the
alternate is logged for diagnostic purposes.

The math is validated against an exact forward model and a real-image
dataset — do not re-derive it.

Sign conventions and units match the rest of the application: angles
enter and leave in radians (rounded to 0.0001 rad internally), with
degrees provided as a display convenience. The module is pure Python /
NumPy with no Qt dependencies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

import numpy as np

from asv_spin_mill_angle_calc.image_metadata import SpinMillImageMetadata
from asv_spin_mill_angle_calc.spin_mill_geometry import (
    FIB_ANGLE_FROM_STAGE_PLANE_DEG,
    fold_scan_rotation_rad,
)

# -----------------------------------------------------------------
# Numerical constants
# -----------------------------------------------------------------
# (The instrument geometry constant FIB_ANGLE_FROM_STAGE_PLANE_DEG is
# imported from spin_mill_geometry — the single source of truth.)

# Internal precision: 0.0001 rad ~ 0.0057 degrees, matching the rest of
# the application's precision conventions.
INTERNAL_RAD_PRECISION: int = 4
DISPLAY_DEG_PRECISION: int = 2

# Hard floor on the number of input positions. Matches the ASV software
# convention. Below this the fit is rejected outright.
MIN_POSITIONS: int = 3

# Below this count the linear sinusoid fit is exactly determined (3
# unknowns) or very nearly so, which makes the R-squared metric
# meaningless. The calculator still produces an answer but emits a
# marginal-fit warning.
MARGINAL_FIT_THRESHOLD: int = 5

# Quality thresholds for committing to a result with status OK. If
# either fit falls below MIN_R_SQUARED or the scan rotation amplitude
# is below MIN_FIT_AMPLITUDE_RAD, the result is marked AMBIGUOUS and
# the result labels stay blank.
MIN_R_SQUARED: float = 0.95
MIN_FIT_AMPLITUDE_RAD: float = math.radians(0.5)

# --- Data-Quality Warning Thresholds (warnings only) -----------------
# Below this circular span of input stage rotations the sinusoid phase
# is poorly constrained even at high R-squared (validated failure mode:
# a 60 deg span gave p95 residual 1.31 deg while R-squared stayed OK).
MIN_ROTATION_SPAN_DEG: float = 150.0
# The two fits independently measure the same sample tilt: amplitudes
# should agree (ratio within this factor) and phases should sit in
# quadrature (scan-rotation zero crossings coincide with stage-tilt
# extrema). Disagreement usually means scan rotation was not actually
# used to level the ellipse at each position.
FIT_AMPLITUDE_RATIO_MAX: float = 2.0
QUADRATURE_TOLERANCE_DEG: float = 20.0


def scan_rotation_branch_center_rad(values_rad: Sequence[float]) -> float:
    """The pi-periodic circular mean of a set of scan rotations.

    Computed on doubled angles — ``0.5 * atan2(sum sin 2v, sum cos 2v)``
    — because ellipse orientation is pi-periodic (see
    ``spin_mill_geometry.fold_scan_rotation_rad``), then folded into
    (-pi/2, pi/2]. Returns 0.0 when the resultant vector is degenerate
    (values 90 deg apart cancel exactly).
    """
    s = sum(math.sin(2.0 * v) for v in values_rad)
    c = sum(math.cos(2.0 * v) for v in values_rad)
    if math.hypot(s, c) < 1e-12:
        return 0.0
    return fold_scan_rotation_rad(0.5 * math.atan2(s, c))


# -----------------------------------------------------------------
# Status enum
# -----------------------------------------------------------------

class SEMGeometryStatus(Enum):
    """Outcome of a single SEM geometry calculation."""
    OK = "ok"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_DATA = "insufficient_data"
    FIT_FAILED = "fit_failed"


# -----------------------------------------------------------------
# Input bundle
# -----------------------------------------------------------------

@dataclass(frozen=True)
class SEMGeometryInputs:
    """Immutable input bundle for the SEM geometry calculation.

    Attributes:
        stage_rotations_rad: Stage rotation angles, in radians, one per
            spin mill position image.
        stage_tilts_rad: Stage tilt angles, in radians, in the same
            order as ``stage_rotations_rad``.
        scan_rotations_rad: FIB scan rotations, in radians, in the same
            order as ``stage_rotations_rad``.
        target_milling_angle_deg: The user's target FIB milling angle
            (alpha), in degrees.
    """
    stage_rotations_rad: Tuple[float, ...]
    stage_tilts_rad: Tuple[float, ...]
    scan_rotations_rad: Tuple[float, ...]
    target_milling_angle_deg: float

    def __post_init__(self) -> None:
        n = len(self.stage_rotations_rad)
        if not (len(self.stage_tilts_rad) == n
                == len(self.scan_rotations_rad)):
            raise ValueError(
                "stage_rotations_rad, stage_tilts_rad, and "
                "scan_rotations_rad must all have the same length."
            )

    @property
    def num_points(self) -> int:
        return len(self.stage_rotations_rad)

    @property
    def scan_rotation_branch_center_rad(self) -> float:
        """The pi-periodic circular mean of the scan rotations, in
        (-pi/2, pi/2] — the anchor for :attr:`folded_scan_rotations_rad`
        and the "your baseline is off the 0/180 reference" diagnostic."""
        return scan_rotation_branch_center_rad(self.scan_rotations_rad)

    @property
    def folded_scan_rotations_rad(self) -> Tuple[float, ...]:
        """Scan rotations folded into the pi-wide branch nearest their
        circular mean.

        Ellipse orientation is pi-periodic, so a scan rotation of 180 deg
        is physically the same orientation as 0 deg; instruments whose
        session baseline is 180 deg would otherwise hand the sinusoid fit
        an offset ~300x its amplitude and never find a zero crossing.
        Anchoring on the circular mean (rather than folding each value
        about 0) keeps a cluster continuous: values straddling +/-90 deg
        would otherwise fold to opposite ends of the branch and wreck the
        fit. For a non-straddling cluster every value differs from its
        raw counterpart by the same multiple of pi, so the fit's
        amplitude, phase and R-squared are unchanged — only the offset C
        moves. ``scan_rotations_rad`` itself stays raw: it is the
        reproducibility record the formatter logs.
        """
        center = self.scan_rotation_branch_center_rad
        return tuple(center + fold_scan_rotation_rad(v - center)
                     for v in self.scan_rotations_rad)

    @classmethod
    def from_records(cls, records: Sequence[SpinMillImageMetadata],
                     target_milling_angle_deg: float) -> "SEMGeometryInputs":
        """Build inputs from parsed image records.

        Every record carries all required fields by construction (the
        parser raises per-file instead of yielding partial rows), so
        there is no silent row-skipping here.
        """
        return cls(
            stage_rotations_rad=tuple(r.stage_rotation_rad for r in records),
            stage_tilts_rad=tuple(r.stage_tilt_rad for r in records),
            scan_rotations_rad=tuple(r.scan_rotation_rad for r in records),
            target_milling_angle_deg=float(target_milling_angle_deg),
        )


# -----------------------------------------------------------------
# Sinusoid fit container
# -----------------------------------------------------------------

@dataclass(frozen=True)
class SinusoidFit:
    """Result of a linear sinusoid fit ``y = A * sin(x - phi0) + C``.

    Attributes:
        amplitude_rad: Fitted amplitude ``A`` (always non-negative).
        phase_rad: Fitted phase ``phi0``.
        offset_rad: Fitted vertical offset ``C``.
        r_squared: Coefficient of determination. Reported as 1.0 for
            exactly-determined fits (N == 3) where the metric is not
            meaningful.
    """
    amplitude_rad: float
    phase_rad: float
    offset_rad: float
    r_squared: float

    def evaluate(self, x_rad: float) -> float:
        return self.amplitude_rad * math.sin(x_rad - self.phase_rad) + self.offset_rad


# -----------------------------------------------------------------
# Result bundle
# -----------------------------------------------------------------

@dataclass(frozen=True)
class SEMGeometryResult:
    """Immutable result bundle from a single SEM geometry calculation.

    The result is self-contained: it carries the inputs, the fit
    diagnostics, both candidate solutions, the selected primary, and
    any warnings raised during the calculation. Both the UI status
    label and the log entry are produced from this object alone, with
    no further computation needed.
    """
    status: SEMGeometryStatus
    status_message: str
    warnings: Tuple[str, ...]

    # Primary answer. ``None`` for AMBIGUOUS / INSUFFICIENT_DATA /
    # FIT_FAILED — these states explicitly mean "no number to show".
    target_stage_rotation_rad: Optional[float]
    target_stage_tilt_rad: Optional[float]

    # The other zero-crossing candidate. May be present even when the
    # primary is None (e.g. AMBIGUOUS due to low R-squared) so the log
    # can still record both candidates the fit produced.
    alternate_stage_rotation_rad: Optional[float]
    alternate_stage_tilt_rad: Optional[float]

    # Fit diagnostics for both fitted relationships.
    scan_rotation_fit: Optional[SinusoidFit]
    stage_tilt_fit: Optional[SinusoidFit]

    # Echo of the inputs, so the formatter can produce a complete log
    # entry without the caller having to pass the inputs alongside.
    inputs: SEMGeometryInputs

    # ----- Display-degree convenience properties ---------------------

    @property
    def target_stage_rotation_deg(self) -> Optional[float]:
        if self.target_stage_rotation_rad is None:
            return None
        return round(math.degrees(self.target_stage_rotation_rad),
                     DISPLAY_DEG_PRECISION)

    @property
    def target_stage_tilt_deg(self) -> Optional[float]:
        if self.target_stage_tilt_rad is None:
            return None
        return round(math.degrees(self.target_stage_tilt_rad),
                     DISPLAY_DEG_PRECISION)

    @property
    def alternate_stage_rotation_deg(self) -> Optional[float]:
        if self.alternate_stage_rotation_rad is None:
            return None
        return round(math.degrees(self.alternate_stage_rotation_rad),
                     DISPLAY_DEG_PRECISION)

    @property
    def alternate_stage_tilt_deg(self) -> Optional[float]:
        if self.alternate_stage_tilt_rad is None:
            return None
        return round(math.degrees(self.alternate_stage_tilt_rad),
                     DISPLAY_DEG_PRECISION)


# -----------------------------------------------------------------
# Calculator
# -----------------------------------------------------------------

class SEMGeometryCalculator:
    """Pure-Python SEM geometry calculator.

    The class is stateless: a single public method ``calculate``
    consumes an ``SEMGeometryInputs`` and returns an
    ``SEMGeometryResult``. There are no Qt dependencies and no I/O.
    Helper methods are kept private so the public surface stays
    minimal.
    """

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def calculate(self, inputs: SEMGeometryInputs) -> SEMGeometryResult:
        """Run the full geometry calculation on a single input bundle.

        Args:
            inputs: The input bundle from ``SEMGeometryInputs``.

        Returns:
            A populated ``SEMGeometryResult``. The result's ``status``
            field tells the caller whether the answer is usable.
        """
        n = inputs.num_points
        warnings: list = []

        # Step 0: hard floor on number of positions.
        if n < MIN_POSITIONS:
            return self._insufficient_data_result(inputs, n)

        # Below the marginal threshold the fit is exact (or nearly so);
        # produce a result anyway but warn the user that R-squared is
        # not meaningful in this regime.
        if n < MARGINAL_FIT_THRESHOLD:
            warnings.append(
                f"Fit is marginal with {n} positions. R-squared is "
                f"undefined or unreliable below {MARGINAL_FIT_THRESHOLD} "
                f"positions."
            )

        # Rotation-span check: a narrow span leaves the sinusoid
        # phase poorly constrained even when R-squared looks fine.
        span_rad = self._rotation_span_rad(inputs.stage_rotations_rad)
        if span_rad < math.radians(MIN_ROTATION_SPAN_DEG):
            warnings.append(
                f"Stage rotations span only {math.degrees(span_rad):.0f}°; "
                f"the result may be poorly constrained (recommend "
                f"covering at least {MIN_ROTATION_SPAN_DEG:.0f}°)."
            )

        # Step 1: fit both relationships. The scan sinusoid is fitted on
        # the folded rotations (pi-periodic orientation, see
        # folded_scan_rotations_rad): for a coherent cluster the fold is
        # a constant offset, so A/phi/R-squared are unchanged and only C
        # moves into the branch where a zero crossing exists.
        try:
            scan_fit = self._fit_sinusoid(
                np.asarray(inputs.stage_rotations_rad, dtype=float),
                np.asarray(inputs.folded_scan_rotations_rad, dtype=float),
            )
            tilt_fit = self._fit_sinusoid(
                np.asarray(inputs.stage_rotations_rad, dtype=float),
                np.asarray(inputs.stage_tilts_rad, dtype=float),
            )
        except Exception as exc:  # pragma: no cover - defensive
            return self._fit_failed_result(inputs, warnings, exc)

        # Cross-fit consistency check: both fits independently
        # measure the same sample tilt, so their amplitudes and phase
        # quadrature are a free lie detector for the input data.
        warnings.extend(
            self._collect_consistency_warnings(scan_fit, tilt_fit))

        # Step 2: locate the zero crossings of the scan rotation fit.
        crossings = self._find_zero_crossings(scan_fit)
        if crossings is None:
            return self._no_crossing_result(
                inputs, warnings, scan_fit, tilt_fit
            )

        # Step 3: at each crossing, read theta_star from the tilt fit
        # and apply the closed-form (38 - alpha) correction.
        alpha_deg = inputs.target_milling_angle_deg
        delta_theta_rad = math.radians(
            FIB_ANGLE_FROM_STAGE_PLANE_DEG - alpha_deg
        )
        candidates = []
        for phi_star in crossings:
            theta_final = tilt_fit.evaluate(phi_star) + delta_theta_rad
            candidates.append(
                (self._wrap_to_signed_pi(phi_star), theta_final)
            )

        # Step 4: round to internal precision.
        candidates = [
            (round(phi, INTERNAL_RAD_PRECISION),
             round(theta, INTERNAL_RAD_PRECISION))
            for phi, theta in candidates
        ]

        # Step 5: select primary candidate. Smaller |theta_final| wins;
        # ties (which the symmetric ideal case produces) are broken by
        # smaller |phi_star|. The other becomes the alternate.
        candidates.sort(key=lambda c: (abs(c[1]), abs(c[0])))
        primary, alternate = candidates

        # Step 6: quality assessment. The R-squared check is only
        # meaningful when there are enough points for the fit to be
        # over-determined.
        ambiguous_reasons = self._collect_ambiguous_reasons(
            n=n, scan_fit=scan_fit, tilt_fit=tilt_fit,
        )

        if ambiguous_reasons:
            warnings.extend(ambiguous_reasons)
            return SEMGeometryResult(
                status=SEMGeometryStatus.AMBIGUOUS,
                status_message="Low fit quality. See log for details.",
                warnings=tuple(warnings),
                target_stage_rotation_rad=None,
                target_stage_tilt_rad=None,
                alternate_stage_rotation_rad=alternate[0],
                alternate_stage_tilt_rad=alternate[1],
                scan_rotation_fit=scan_fit,
                stage_tilt_fit=tilt_fit,
                inputs=inputs,
            )

        return SEMGeometryResult(
            status=SEMGeometryStatus.OK,
            status_message=(
                f"Calculation complete using {n} "
                f"position{'s' if n != 1 else ''}."
            ),
            warnings=tuple(warnings),
            target_stage_rotation_rad=primary[0],
            target_stage_tilt_rad=primary[1],
            alternate_stage_rotation_rad=alternate[0],
            alternate_stage_tilt_rad=alternate[1],
            scan_rotation_fit=scan_fit,
            stage_tilt_fit=tilt_fit,
            inputs=inputs,
        )

    # -----------------------------------------------------------------
    # Result builders for early-exit paths
    # -----------------------------------------------------------------

    @staticmethod
    def _insufficient_data_result(inputs: SEMGeometryInputs,
                                  n: int) -> SEMGeometryResult:
        return SEMGeometryResult(
            status=SEMGeometryStatus.INSUFFICIENT_DATA,
            status_message=(
                f"Need at least {MIN_POSITIONS} positions, got {n}."
            ),
            warnings=(),
            target_stage_rotation_rad=None,
            target_stage_tilt_rad=None,
            alternate_stage_rotation_rad=None,
            alternate_stage_tilt_rad=None,
            scan_rotation_fit=None,
            stage_tilt_fit=None,
            inputs=inputs,
        )

    @staticmethod
    def _fit_failed_result(inputs: SEMGeometryInputs,
                           warnings: list,
                           exc: Exception) -> SEMGeometryResult:
        return SEMGeometryResult(
            status=SEMGeometryStatus.FIT_FAILED,
            status_message=f"Sinusoid fit failed: {exc}",
            warnings=tuple(warnings),
            target_stage_rotation_rad=None,
            target_stage_tilt_rad=None,
            alternate_stage_rotation_rad=None,
            alternate_stage_tilt_rad=None,
            scan_rotation_fit=None,
            stage_tilt_fit=None,
            inputs=inputs,
        )

    @staticmethod
    def _no_crossing_result(inputs: SEMGeometryInputs,
                            warnings: list,
                            scan_fit: SinusoidFit,
                            tilt_fit: SinusoidFit) -> SEMGeometryResult:
        message = ("Scan rotation does not cross zero. Sample may be too "
                   "flat to align, or fit offset exceeds amplitude.")
        # A branch center materially off 0 usually means the instrument's
        # baseline sits off the 0/180 reference (the fold handles 180
        # exactly; e.g. a 90 deg baseline is a genuinely different
        # orientation and cannot alias to 0).
        center_deg = math.degrees(inputs.scan_rotation_branch_center_rad)
        if abs(center_deg) > 1.0:
            message += (f" (scan rotations sit ~{center_deg:.1f}° off "
                        f"the 0/180 reference)")
        return SEMGeometryResult(
            status=SEMGeometryStatus.AMBIGUOUS,
            status_message=message,
            warnings=tuple(warnings),
            target_stage_rotation_rad=None,
            target_stage_tilt_rad=None,
            alternate_stage_rotation_rad=None,
            alternate_stage_tilt_rad=None,
            scan_rotation_fit=scan_fit,
            stage_tilt_fit=tilt_fit,
            inputs=inputs,
        )

    # -----------------------------------------------------------------
    # Quality assessment
    # -----------------------------------------------------------------

    @staticmethod
    def _collect_ambiguous_reasons(n: int,
                                   scan_fit: SinusoidFit,
                                   tilt_fit: SinusoidFit) -> list:
        """Collect reasons why the fit should be considered ambiguous.

        Returns plain strings; an empty list means the fit is OK.
        """
        reasons: list = []
        if scan_fit.amplitude_rad < MIN_FIT_AMPLITUDE_RAD:
            reasons.append(
                f"Scan rotation amplitude "
                f"({math.degrees(scan_fit.amplitude_rad):.3f}°) is "
                f"below the minimum threshold "
                f"({math.degrees(MIN_FIT_AMPLITUDE_RAD):.3f}°). "
                f"Sample may be too flat to align reliably."
            )
        if n >= MARGINAL_FIT_THRESHOLD and scan_fit.r_squared < MIN_R_SQUARED:
            reasons.append(
                f"Scan rotation fit R-squared "
                f"({scan_fit.r_squared:.3f}) is below the minimum "
                f"threshold ({MIN_R_SQUARED:.2f})."
            )
        if n >= MARGINAL_FIT_THRESHOLD and tilt_fit.r_squared < MIN_R_SQUARED:
            reasons.append(
                f"Stage tilt fit R-squared ({tilt_fit.r_squared:.3f}) "
                f"is below the minimum threshold ({MIN_R_SQUARED:.2f})."
            )
        return reasons

    @staticmethod
    def _collect_consistency_warnings(scan_fit: SinusoidFit,
                                      tilt_fit: SinusoidFit) -> list:
        """Collect cross-fit consistency warnings; they never change status.

        Both sinusoids measure the sample's intrinsic tilt, so their
        amplitudes should agree to within a factor and their phases
        should sit in quadrature (a scan-rotation zero crossing is a
        stage-tilt extremum). The amplitude check runs whenever either
        fit shows real signal (catching "tilt varies but scan rotation
        was never adjusted"); the quadrature check needs both phases to
        be meaningful, so it requires both amplitudes above the floor.
        """
        warnings: list = []
        larger = max(scan_fit.amplitude_rad, tilt_fit.amplitude_rad)
        smaller = min(scan_fit.amplitude_rad, tilt_fit.amplitude_rad)
        if larger >= MIN_FIT_AMPLITUDE_RAD and (
                smaller <= 0.0
                or larger / smaller > FIT_AMPLITUDE_RATIO_MAX):
            warnings.append(
                f"Scan-rotation and stage-tilt fit amplitudes disagree "
                f"({math.degrees(scan_fit.amplitude_rad):.2f}° vs "
                f"{math.degrees(tilt_fit.amplitude_rad):.2f}°); were "
                f"stage tilt and scan rotation both adjusted at every "
                f"position?"
            )
        if (scan_fit.amplitude_rad >= MIN_FIT_AMPLITUDE_RAD
                and tilt_fit.amplitude_rad >= MIN_FIT_AMPLITUDE_RAD):
            delta = (scan_fit.phase_rad - tilt_fit.phase_rad) % math.pi
            quadrature_deviation_deg = abs(math.degrees(delta) - 90.0)
            if quadrature_deviation_deg > QUADRATURE_TOLERANCE_DEG:
                warnings.append(
                    f"Scan-rotation and stage-tilt fits are "
                    f"{quadrature_deviation_deg:.1f}° out of "
                    f"quadrature (expected ~90° phase offset); were "
                    f"stage tilt and scan rotation both adjusted at "
                    f"every position?"
                )
        return warnings

    # -----------------------------------------------------------------
    # Math helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _rotation_span_rad(rotations_rad: Sequence[float]) -> float:
        """Circular span covered by the stage rotations.

        Computed as 2*pi minus the largest gap between consecutive
        sorted (wrapped) rotations.
        """
        if len(rotations_rad) < 2:
            return 0.0
        two_pi = 2 * math.pi
        wrapped = sorted(angle % two_pi for angle in rotations_rad)
        gaps = [b - a for a, b in zip(wrapped, wrapped[1:])]
        gaps.append(wrapped[0] + two_pi - wrapped[-1])
        return two_pi - max(gaps)

    @staticmethod
    def _fit_sinusoid(x: np.ndarray, y: np.ndarray) -> SinusoidFit:
        """Linear least-squares fit of ``y = a1*sin(x) + a2*cos(x) + C``.

        The model is rewritten in amplitude/phase form on return:
        ``y = A * sin(x - phi0) + C`` with ``A = sqrt(a1^2 + a2^2)``
        and ``phi0 = atan2(-a2, a1)``. Using the linear basis means
        no nonlinear initial guess is needed and the solution is
        unique up to phase wrapping.

        Args:
            x: Independent variable values, radians.
            y: Dependent variable values, radians.

        Returns:
            A populated ``SinusoidFit``.
        """
        n = len(x)
        if n < MIN_POSITIONS:
            raise ValueError(
                f"Sinusoid fit requires at least {MIN_POSITIONS} points; "
                f"got {n}."
            )

        design = np.column_stack([np.sin(x), np.cos(x), np.ones(n)])
        coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
        a1, a2, c = coeffs

        amplitude = float(math.hypot(a1, a2))
        phase = float(math.atan2(-a2, a1))
        offset = float(c)

        # Coefficient of determination.
        y_pred = design @ coeffs
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        if ss_tot < 1e-15:
            r_squared = 1.0 if ss_res < 1e-15 else 0.0
        else:
            r_squared = 1.0 - ss_res / ss_tot
        # For exactly-determined fits the residual is ~0 by construction
        # and R-squared isn't meaningful — report it as 1.0 explicitly
        # so floating-point noise doesn't produce odd values.
        if n == MIN_POSITIONS:
            r_squared = 1.0

        return SinusoidFit(
            amplitude_rad=amplitude,
            phase_rad=phase,
            offset_rad=offset,
            r_squared=r_squared,
        )

    @staticmethod
    def _find_zero_crossings(fit: SinusoidFit) -> Optional[Tuple[float, float]]:
        """Solve ``A * sin(x - phi0) + C = 0`` for x in [0, 2*pi).

        Returns:
            A pair of solutions (x1, x2), each in [0, 2*pi). Returns
            ``None`` if the amplitude is effectively zero or if
            ``|C/A| > 1`` (no real solutions).
        """
        if fit.amplitude_rad < 1e-12:
            return None
        ratio = -fit.offset_rad / fit.amplitude_rad
        if abs(ratio) > 1.0:
            return None
        base = math.asin(ratio)
        two_pi = 2 * math.pi
        x1 = (fit.phase_rad + base) % two_pi
        x2 = (fit.phase_rad + (math.pi - base)) % two_pi
        return (x1, x2)

    @staticmethod
    def _wrap_to_signed_pi(angle_rad: float) -> float:
        """Wrap an angle into the half-open interval (-pi, pi].

        Used so that displayed stage rotations are reported as small
        signed values (e.g. -177 deg instead of 183 deg) which match
        the convention used elsewhere in the application.
        """
        wrapped = (angle_rad + math.pi) % (2 * math.pi) - math.pi
        # The modulo can return -pi exactly; canonicalize to +pi so
        # the half-open interval (-pi, pi] is respected.
        if wrapped == -math.pi:
            wrapped = math.pi
        return wrapped


# -----------------------------------------------------------------
# Measured Perpendicular Candidates
# -----------------------------------------------------------------

# A measured position counts as "already perpendicular in rotation" when
# its recorded FIB scan rotation is within this tolerance of zero.
MEASURED_SCAN_ROTATION_TOLERANCE_RAD: float = math.radians(0.01)

# Source categories for the SEM positions table.
SOURCE_CALCULATED: str = "Calculated (primary)"
SOURCE_ALTERNATE: str = "Calculated (alternate)"
SOURCE_MEASURED: str = "Measured"


@dataclass(frozen=True)
class SemPositionCandidate:
    """One row of the SEM positions table (SI radians).

    ``source`` is one of the SOURCE_* categories; ``source_detail``
    carries provenance beyond the category (the image file name for
    measured candidates) and surfaces in the row's tooltip.
    """
    source: str
    stage_rotation_rad: float
    stage_tilt_rad: float
    source_detail: str = ""


def measured_perpendicular_candidates_from_inputs(
    inputs: SEMGeometryInputs,
    details: Sequence[str] = (),
    tolerance_rad: float = MEASURED_SCAN_ROTATION_TOLERANCE_RAD,
) -> list[SemPositionCandidate]:
    """Measured positions whose |folded scan rotation| <= tolerance.

    Physics note (confirm with a domain expert): scan rotation ~ 0 means the
    surface normal already lies in the FIB-SEM plane at that stage
    rotation, but the position was captured at the *milling* tilt
    (grazing angle alpha). The same closed-form correction used for the
    fitted candidates therefore still applies to its tilt:

        theta_final = theta_measured + radians(38 - alpha)

    The comparison uses the per-record fold about 0 (ellipse orientation
    is pi-periodic, so an untouched 180-baseline position qualifies
    exactly like a 0-baseline one) — deliberately not the cluster-
    anchored fold: whether one position is perpendicular must not depend
    on which other positions were loaded alongside it.

    The stage rotation is the measured value unchanged (wrapped to
    (-pi, pi] for display consistency). Rounding matches the fitted
    candidates (INTERNAL_RAD_PRECISION). Order follows the inputs. A
    position whose scan rotation was simply never adjusted also
    qualifies — by design, the page reports the data it has; the
    cross-fit consistency warning is the flag for that situation.
    ``details`` (optional, parallel to the inputs) fills each row's
    ``source_detail`` — file names on the SEM page, position labels on
    the alignment page.
    """
    delta_theta_rad = math.radians(
        FIB_ANGLE_FROM_STAGE_PLANE_DEG - inputs.target_milling_angle_deg)
    candidates: list[SemPositionCandidate] = []
    triples = zip(inputs.stage_rotations_rad, inputs.stage_tilts_rad,
                  inputs.scan_rotations_rad)
    for index, (stage_r, stage_t, scan_r) in enumerate(triples):
        if abs(fold_scan_rotation_rad(scan_r)) > tolerance_rad:
            continue
        candidates.append(SemPositionCandidate(
            source=SOURCE_MEASURED,
            stage_rotation_rad=round(
                SEMGeometryCalculator._wrap_to_signed_pi(stage_r),
                INTERNAL_RAD_PRECISION),
            stage_tilt_rad=round(
                stage_t + delta_theta_rad,
                INTERNAL_RAD_PRECISION),
            source_detail=details[index] if index < len(details) else "",
        ))
    return candidates


def measured_perpendicular_candidates(
    records: Sequence[SpinMillImageMetadata],
    target_milling_angle_deg: float,
    tolerance_rad: float = MEASURED_SCAN_ROTATION_TOLERANCE_RAD,
) -> list[SemPositionCandidate]:
    """Record-based convenience wrapper (the SEM Angle Calc page's
    path): builds the inputs from parsed image records and passes the
    file names through as the rows' provenance details."""
    inputs = SEMGeometryInputs.from_records(records,
                                            target_milling_angle_deg)
    return measured_perpendicular_candidates_from_inputs(
        inputs,
        details=[record.file_name for record in records],
        tolerance_rad=tolerance_rad,
    )
