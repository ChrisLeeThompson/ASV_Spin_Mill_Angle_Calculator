"""
Module detects the milled fiducial ellipse in grazing-incidence FIB images.

The detector locates the thin ring left by the spin mill fiducial
circle when viewed by the FIB at grazing incidence, and fits an ellipse
to it. The minor/major axis ratio gives the actual milling angle at
that position directly: alpha = asin(b / a), independent of pixel
calibration.

Depending on the surface, the ring may appear dark on a light
background or bright on a dark background; the detector handles both
polarities (see ``EllipseDetectorConfig.polarity``).

Dependencies are restricted to packages guaranteed present in the
AutoScript Python environment (numpy and OpenCV are mandatory
dependencies of the AutoScript client packages, per the AutoScript
reference manual's environment setup). No scipy, no scikit-image, no
Qt. The class is stateless and side-effect free, so it can run
unchanged inside an AutoScript session on the support PC::

    from autoscript_sdb_microscope_client.structures import AdornedImage
    image = AdornedImage.load(path)          # or imaging.grab_frame()
    fit = FiducialEllipseDetector().detect(image.data)

or inside the desktop application with an array loaded any other way.

Pipeline
--------
1. Illumination normalization (divide by heavy Gaussian blur) removes
   the vertical brightness gradient and vignetting. The candidate ROI
   additionally clips everything below the sample-edge -> void cliff
   (adaptive horizon, row-median drop) so near-black void noise never
   floods the candidate set at high stage tilt.
2. Two channels enhance the thin ring, per polarity (dark ring on a
   light surface, or bright on dark; ``auto`` runs both):
   - a step-rejecting valley response ``min(I(y-d), I(y+d)) - I(y)``,
     noise-normalized per row, feeds the center-vote path;
   - hat morphology (black-hat / top-hat) feeds the RANSAC path.
3. Percentile threshold over the ROI yields candidate points (the
   RANSAC channel additionally keeps only elongated components).
4. Detection:
   - **Known-shape center-vote** (primary when the caller pins the
     semi-major axis from the AOI diameter): rasterized ellipse-
     perimeter templates over a (b, tilt) grid are correlated with
     the max-pooled valley mask (``cv2.matchTemplate``); peak
     candidates are verified at full resolution and ranked by
     arc-sector coverage, then locally refined with shrinking
     tolerances. Several distinct hypotheses can be returned so the
     caller's gates can fall back past a clutter winner.
   - **Guided RANSAC** (AOI unknown, or vote found nothing): samples
     spread across horizontal bins, fitted with
     ``cv2.fitEllipseDirect``, gated by geometry priors, scored by
     inliers times sector coverage, three refinement rounds. Inlier
     gating uses the Sampson (first-order geometric) distance of the
     conic, computed in pure numpy.
5. All fits are ranked by (coverage, inliers, -rms) — arc-coverage
   first, because inlier count alone rewards clutter harvesting on
   real frames.

Angles follow the application's conventions: degrees at 2 decimal
places for display; the ellipse tilt is the major-axis angle from the
image x-axis in (-90, 90].
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


logger = logging.getLogger(__name__)


# Polarity names accepted by EllipseDetectorConfig.polarity. "dark"
# means a dark ring on a light surface (black-hat response), "bright"
# the reverse (top-hat), and "auto" tries both and keeps the
# better-scoring fit at roughly double the runtime.
POLARITY_DARK: str = "dark"
POLARITY_BRIGHT: str = "bright"
POLARITY_AUTO: str = "auto"

_MORPH_BY_POLARITY = {
    POLARITY_DARK: cv2.MORPH_BLACKHAT,
    POLARITY_BRIGHT: cv2.MORPH_TOPHAT,
}

# Intensity-trough refinement of vote locks (algorithm constants, not
# hardware tunables): the normalized image is sampled along ellipse
# normals; each normal contributes one subpixel valley trough when its
# depth clears the per-row noise. The trough fraction is a true
# arc-coverage measure — unlike point-mask sector occupancy it cannot
# saturate on dense clutter. Spans are in reference-width pixels.
_TROUGH_NORMALS = 360
_TROUGH_HALF_SPAN_REF_PX = 3.0
_TROUGH_STEP_REF_PX = 0.125
_TROUGH_MIN_DEPTH_SIGMA = 1.5
_TROUGH_STRONG_DEPTH_SIGMA = 3.0
_TROUGH_TRIM_REF_PX = 2.5
_TROUGH_MIN_COUNT = 30
# A real milled groove is continuous around the perimeter; a pair of
# horizontal clutter bands spaced ~2b mimics the flat arcs but leaves
# two ~100-degree holes around the tips. Reject fits whose troughs
# have a larger contiguous parametric gap than this.
_TROUGH_MAX_GAP_DEG = 90.0
# Minimum strong-trough fraction for a vote fit to be credible at all:
# pure noise yields scattered shallow troughs (fractions well under
# 0.05), the weakest real corpus lock measured 0.27.
_VOTE_MIN_STRONG_COVERAGE = 0.10


# -----------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------

@dataclass(frozen=True)
class EllipseDetectorConfig:
    """
    Tunable parameters and geometry priors for the detector.

    The default priors describe the spin mill fiducial as imaged by
    the ASV workflow: a wide, very flat, near-horizontal ellipse
    roughly centered in the field of view. Fractions are relative to
    image width/height; pixel-denominated tunables were tuned at
    ``reference_width_px`` and are rescaled by (width / reference)
    at detect time, so both survive resolution changes.
    """
    # Preprocessing (pixel values at reference_width_px, rescaled)
    blur_sigma: float = 25.0
    hat_kernel_px: int = 9
    threshold_percentile: float = 95.0
    roi_top_frac: float = 0.15
    roi_bottom_frac: float = 0.72
    polarity: str = POLARITY_AUTO
    # Valley channel (feeds the center-vote path). The step-rejecting
    # response min(I(y-d), I(y+d)) - I(y) zeroes one-sided steps such
    # as the sample-edge -> void boundary that the hat morphology
    # scores highly; per-row noise normalization is floored so the
    # near-black void cannot re-amplify quantization noise.
    valley_offset_px: float = 1.5
    valley_smooth_sigma_px: float = 2.0
    # Adaptive void clip: rows below the row-median cliff (the sample
    # edge against the void at high stage tilt) are excluded from the
    # ROI, in addition to the static roi_bottom_frac.
    horizon_clip_enabled: bool = True
    horizon_level_frac: float = 0.35
    horizon_drop_frac: float = 0.20
    horizon_guard_rows: int = 5
    # Known-shape center-vote: the primary detection path when the
    # caller pins the semi-major axis via ExpectedGeometry. Perimeter
    # templates over a (center) x (b, tilt) grid are correlated with
    # the valley mask; peaks are verified at full resolution by
    # arc-sector coverage. RANSAC remains the AOI-unknown fallback.
    vote_downsample: int = 2
    vote_template_thickness_px: float = 2.5
    vote_b_step_px: float = 3.0
    vote_tilt_range_deg: float = 4.0   # must cover injected scan rot
    vote_tilt_step_deg: float = 1.0
    vote_a_frac_offsets: Tuple[float, ...] = (1.0,)
    vote_peaks_per_hypothesis: int = 5
    vote_max_candidates: int = 12
    vote_top_k: int = 5
    refine_capture_tolerance_px: float = 5.0
    # In auto polarity, skip the second polarity when the first one
    # already produced a lock whose strong-trough coverage clears this
    # bar (the ring cannot be dark and bright at once). Set above 1.0
    # to always run both.
    vote_short_circuit_coverage: float = 0.5
    # Component filter (pixel values at reference_width_px, rescaled)
    min_component_area_px: int = 8
    min_component_length_px: int = 30
    # RANSAC
    n_iterations: int = 1500
    sample_bins: int = 6
    inlier_tolerance_px: float = 2.5   # at reference_width_px, rescaled
    coverage_sectors: int = 36
    refinement_rounds: int = 3
    random_seed: Optional[int] = 42
    # Width at which the pixel-denominated tunables above were tuned.
    reference_width_px: int = 768
    # Geometry priors
    center_x_frac: Tuple[float, float] = (0.30, 0.70)
    center_y_frac: Tuple[float, float] = (0.20, 0.75)
    semi_major_frac: Tuple[float, float] = (0.25, 0.60)
    # The semi-minor axis is bounded through the b/a ratio (resolution
    # proof), not absolute pixels: min_axis_ratio ~ asin 1.7 deg sits
    # below the 2 deg minimum target angle and rejects the degenerate
    # near-flat fits that horizontal band content produces on real
    # frames; max_axis_ratio ~ asin 20.5 deg caps the working range.
    min_axis_ratio: float = 0.03
    max_axis_ratio: float = 0.35
    semi_minor_floor_px: float = 2.0   # absolute hairline floor
    max_tilt_deg: float = 12.0
    # Half-width of the semi-major band around an ExpectedGeometry
    # hint, replacing semi_major_frac when the caller knows the AOI.
    # Looser than the sequence's +/-10% width gate on purpose: the
    # detector proposes, the gate disposes.
    expected_semi_major_tolerance_frac: float = 0.15


@dataclass(frozen=True)
class ExpectedGeometry:
    """
    Optional per-frame priors from the caller's physical model.

    Attributes:
        semi_major_px: Expected semi-major axis in pixels (AOI radius
            over pixel size). The major axis is tilt-invariant, so a
            caller that knows the AOI diameter knows this exactly; it
            replaces the static ``semi_major_frac`` band with
            ``semi_major_px * (1 +/- expected_semi_major_tolerance_frac)``.
        axis_ratio: Expected (low, high) band for b/a, e.g.
            ``sin(model angle +/- plausibility window)``; intersected
            with ``[min_axis_ratio, max_axis_ratio]``. Constraining the
            ratio inside RANSAC lets the true ring win the fit where a
            degenerate flat hypothesis would otherwise out-score it.
        max_abs_tilt_deg: Expected upper bound on the ring's |image
            tilt|. The ellipse tilt tracks the applied scan rotation
            1:1 (verified on the real corpus), so a caller that knows
            its own applied scan rotation can bound the vote's tilt
            search: ~2 deg of intrinsic ring rotation plus |scan
            rotation|. Sign-agnostic on purpose — the tracking
            polarity is instrument-dependent. None falls back to
            ``vote_tilt_range_deg``.
    """
    semi_major_px: Optional[float] = None
    axis_ratio: Optional[Tuple[float, float]] = None
    max_abs_tilt_deg: Optional[float] = None


# -----------------------------------------------------------------
# Result bundle
# -----------------------------------------------------------------

@dataclass(frozen=True)
class EllipseFit:
    """
    Immutable result of a fiducial ellipse detection.

    Attributes:
        center_x_px, center_y_px: Ellipse center in image pixels.
        semi_major_px: Semi-major axis ``a`` in pixels.
        semi_minor_px: Semi-minor axis ``b`` in pixels.
        tilt_deg: Major-axis angle from the image x-axis, degrees,
            in (-90, 90].
        n_inliers: Number of candidate points within tolerance of the
            fitted curve.
        coverage: Fraction of angular sectors around the ellipse that
            contain at least one inlier (0-1). Low coverage means the
            fit rests on a short arc and should be treated with
            caution.
        rms_px: RMS geometric distance of inliers to the fitted
            curve, pixels.
        polarity: Which ring polarity produced the fit ("dark" or
            "bright").
        method: Which detection path produced the fit ("vote" for the
            known-shape center-vote, "ransac" for the sampling
            fallback). Observability only; gates never read it.
    """
    center_x_px: float
    center_y_px: float
    semi_major_px: float
    semi_minor_px: float
    tilt_deg: float
    n_inliers: int
    coverage: float
    rms_px: float
    polarity: str = POLARITY_DARK
    method: str = "ransac"

    @property
    def milling_angle_deg(self) -> float:
        """Actual milling angle implied by foreshortening: asin(b/a)."""
        return round(math.degrees(
            math.asin(self.semi_minor_px / self.semi_major_px)), 2)

    @property
    def score(self) -> float:
        """RANSAC quality score (inliers times sector coverage)."""
        return self.n_inliers * self.coverage

    def axes_um(self, um_per_px: float) -> Tuple[float, float]:
        """Full axes (2a, 2b) in micrometers for a given pixel size."""
        return (round(2 * self.semi_major_px * um_per_px, 2),
                round(2 * self.semi_minor_px * um_per_px, 2))


# -----------------------------------------------------------------
# Detector
# -----------------------------------------------------------------

class FiducialEllipseDetector:
    """
    Stateless fiducial-ellipse detector (numpy + OpenCV only).

    A single public method ``detect`` consumes a 2D grayscale image
    array and returns an ``EllipseFit`` or ``None`` when no ellipse
    satisfying the geometry priors is found.
    """

    def __init__(self, config: EllipseDetectorConfig = None):
        self._cfg = config or EllipseDetectorConfig()
        if (self._cfg.polarity not in _MORPH_BY_POLARITY
                and self._cfg.polarity != POLARITY_AUTO):
            raise ValueError(
                f"Unknown polarity {self._cfg.polarity!r}; expected "
                f"{POLARITY_DARK!r}, {POLARITY_BRIGHT!r} or "
                f"{POLARITY_AUTO!r}")

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def detect(self, image: np.ndarray,
               expected: Optional[ExpectedGeometry] = None,
               ) -> Optional[EllipseFit]:
        """
        Detect the fiducial ellipse in a grayscale image.

        Args:
            image: 2D uint8/uint16/float array. Color images are
                converted with ``cv2.cvtColor``.
            expected: Optional physical-model priors (see
                ``ExpectedGeometry``).

        Returns:
            The best-scoring ``EllipseFit``, or ``None`` if detection
            failed under every polarity the configuration allows.
        """
        fits = self.detect_all(image, expected)
        return fits[0] if fits else None

    def detect_all(self, image: np.ndarray,
                   expected: Optional[ExpectedGeometry] = None,
                   ) -> Tuple[EllipseFit, ...]:
        """
        Detect under every allowed polarity, ranked best first by
        (coverage, inliers, -rms) — arc-coverage first, because on real
        frames the inlier count rewards clutter harvesting.

        When the caller pins the semi-major axis (ExpectedGeometry from
        a known AOI diameter) the known-shape center-vote is the
        primary path and may return several distinct hypotheses per
        polarity, so a caller with its own acceptance gates can fall
        back to a runner-up instead of losing the whole frame. Without
        that prior, guided RANSAC runs as before (AOI-unknown mode).
        """
        cfg = self._cfg
        gray = self._to_gray(image)
        h, w = gray.shape
        scale = w / cfg.reference_width_px
        normalized = self._normalize_illumination(gray, scale)
        roi = self._roi_mask(normalized, scale)
        fits = []
        for polarity in self._polarities():
            if expected is not None and expected.semi_major_px is not None:
                vote_fits = self._vote_detect(normalized, roi, polarity,
                                              scale, w, h, expected)
                if vote_fits:
                    fits.extend(vote_fits)
                    if (max(f.coverage for f in vote_fits)
                            >= cfg.vote_short_circuit_coverage):
                        # A strong groove lock is decisive: the ring
                        # cannot be dark and bright at once.
                        break
                    continue
                logger.info(
                    "Ellipse detection (%s ring): center-vote found no "
                    "candidate; falling back to RANSAC", polarity)
            points = self._candidate_points(normalized, roi, polarity,
                                            scale)
            if len(points) < 50:
                logger.warning(
                    "Ellipse detection (%s ring): only %d candidate "
                    "points", polarity, len(points))
                continue
            fit = self._ransac_fit(points, w, h, polarity, expected)
            if fit is not None:
                fits.append(fit)
        ranked = sorted(fits, key=lambda fit: (fit.coverage, fit.n_inliers,
                                               -fit.rms_px), reverse=True)
        return tuple(self._drop_duplicates(ranked, w, scale))

    def _drop_duplicates(self, ranked, w: int, scale: float):
        """Cross-polarity / cross-path dedup: keep the better-ranked of
        two fits describing the same hypothesis."""
        cfg = self._cfg
        kept = []
        for fit in ranked:
            duplicate = any(
                math.hypot(fit.center_x_px - other.center_x_px,
                           fit.center_y_px - other.center_y_px) < 0.02 * w
                and abs(fit.semi_minor_px - other.semi_minor_px)
                < 2.0 * cfg.vote_b_step_px * scale
                and abs(fit.tilt_deg - other.tilt_deg)
                < cfg.vote_tilt_step_deg
                for other in kept)
            if not duplicate:
                kept.append(fit)
        return kept

    def _polarities(self) -> Tuple[str, ...]:
        if self._cfg.polarity == POLARITY_AUTO:
            return (POLARITY_DARK, POLARITY_BRIGHT)
        return (self._cfg.polarity,)

    # -----------------------------------------------------------------
    # Preprocessing
    # -----------------------------------------------------------------

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if image.dtype != np.uint8:
            lo, hi = float(image.min()), float(image.max())
            scale = 255.0 / (hi - lo) if hi > lo else 1.0
            image = ((image.astype(np.float32) - lo) * scale).astype(np.uint8)
        return image

    def _normalize_illumination(self, gray: np.ndarray,
                                scale: float) -> np.ndarray:
        """Divide by a heavy Gaussian estimate of the background:
        removes the vertical brightness gradient and vignetting."""
        g = gray.astype(np.float32) + 1.0
        background = cv2.GaussianBlur(g, (0, 0),
                                      self._cfg.blur_sigma * scale)
        return g / background

    def _horizon_row(self, normalized: np.ndarray) -> Optional[int]:
        """First row of the sample-edge -> void cliff (smoothed
        row-median drop below half height), or None when the frame has
        no void."""
        cfg = self._cfg
        h, w = normalized.shape
        c0, c1 = int(0.02 * w), int(0.98 * w)
        med = np.median(normalized[:, c0:c1], axis=1).astype(np.float32)
        med = np.convolve(med, np.ones(15, np.float32) / 15.0, mode="same")
        top = int(cfg.roi_top_frac * h)
        ref = float(np.median(med[top:int(0.5 * h)]))
        drop_rows = 8
        for y in range(int(0.5 * h), h):
            prev = med[max(0, y - drop_rows)]
            if (med[y] < cfg.horizon_level_frac * ref
                    and prev - med[y] > cfg.horizon_drop_frac * ref):
                return y
        return None

    def _roi_mask(self, normalized: np.ndarray, scale: float) -> np.ndarray:
        """Candidate-point ROI: static band plus the adaptive horizon
        clip. Shared by the vote and RANSAC paths."""
        cfg = self._cfg
        h, w = normalized.shape
        bottom = int(cfg.roi_bottom_frac * h)
        if cfg.horizon_clip_enabled:
            cliff = self._horizon_row(normalized)
            if cliff is not None:
                guard = int(round(cfg.horizon_guard_rows * scale))
                bottom = min(bottom, cliff - guard)
        roi = np.zeros((h, w), dtype=bool)
        if bottom > int(cfg.roi_top_frac * h):
            roi[int(cfg.roi_top_frac * h):bottom,
                int(0.02 * w):int(0.98 * w)] = True
        return roi

    @staticmethod
    def _row_noise_sigma(normalized: np.ndarray) -> np.ndarray:
        """Robust per-row noise estimate (MAD of horizontal first
        differences), floored so near-black void rows cannot be
        amplified into signal by normalization."""
        diffs = np.abs(np.diff(normalized, axis=1))
        mad = np.median(diffs, axis=1)
        row_sigma = 1.4826 * mad / math.sqrt(2.0)
        floor = max(1e-6, 0.3 * float(np.median(row_sigma)))
        return np.maximum(row_sigma, floor)

    def _valley_mask(self, normalized: np.ndarray, roi: np.ndarray,
                     polarity: str, scale: float,
                     row_sigma: np.ndarray) -> np.ndarray:
        """Binary mask from the step-rejecting valley response,
        noise-normalized per row. No component filter: the vote itself
        is the structure filter, and the filter would delete the faint
        broken tip fragments the vote can still use."""
        cfg = self._cfg
        d = max(1, int(round(cfg.valley_offset_px * scale)))
        smoothed = cv2.GaussianBlur(
            normalized, (0, 0),
            sigmaX=cfg.valley_smooth_sigma_px * scale, sigmaY=0.8)
        up = np.empty_like(smoothed)
        down = np.empty_like(smoothed)
        up[d:, :] = smoothed[:-d, :]
        up[:d, :] = smoothed[0, :]
        down[:-d, :] = smoothed[d:, :]
        down[-d:, :] = smoothed[-1, :]
        if polarity == POLARITY_DARK:
            response = np.minimum(up, down) - smoothed
        else:
            response = smoothed - np.maximum(up, down)
        response = response / row_sigma[:, None]
        threshold = np.percentile(response[roi], cfg.threshold_percentile)
        return ((response > threshold) & roi).astype(np.uint8)

    def _candidate_points(self, normalized: np.ndarray, roi: np.ndarray,
                          polarity: str, scale: float) -> np.ndarray:
        cfg = self._cfg
        # Pixel-denominated tunables were tuned at reference_width_px;
        # rescale so features keep their sample-relative size at any
        # scan resolution (exact no-op at the reference width).
        kernel_px = max(3, int(round(cfg.hat_kernel_px * scale)) | 1)
        min_area = cfg.min_component_area_px * scale * scale
        min_length = cfg.min_component_length_px * scale
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_px, kernel_px))
        ridges = cv2.morphologyEx(
            normalized, _MORPH_BY_POLARITY[polarity], kernel)
        threshold = np.percentile(ridges[roi], cfg.threshold_percentile)
        mask = ((ridges > threshold) & roi).astype(np.uint8)

        # Keep elongated / thin components; drop compact debris blobs.
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        keep = np.zeros(n, dtype=bool)
        for i in range(1, n):
            _x, _y, bw, bh, area = stats[i]
            if area < min_area:
                continue
            fill = area / float(bw * bh)
            elongated = (bw >= 4 * bh) or (bh >= 4 * bw)
            long_enough = max(bw, bh) >= min_length
            if ((elongated and long_enough)
                    or (long_enough and fill < 0.45)
                    or bw >= 4 * min_length):
                keep[i] = True
        ys, xs = np.nonzero(keep[labels])
        return np.column_stack([xs, ys]).astype(np.float32)

    # -----------------------------------------------------------------
    # Known-shape center-vote
    # -----------------------------------------------------------------

    @staticmethod
    def _perimeter_template(a: float, b: float, tilt_deg: float,
                            thickness: int) -> np.ndarray:
        """Rasterized ellipse perimeter sized to the rotated bounding
        box; the stroke thickness is the vote's spatial tolerance."""
        pad = thickness + 2
        theta = math.radians(tilt_deg)
        half_w = math.hypot(a * math.cos(theta), b * math.sin(theta))
        half_h = math.hypot(a * math.sin(theta), b * math.cos(theta))
        tw = int(2 * math.ceil(half_w) + 2 * pad + 1)
        th = int(2 * math.ceil(half_h) + 2 * pad + 1)
        template = np.zeros((th, tw), np.float32)
        cv2.ellipse(template, ((tw - 1) // 2, (th - 1) // 2),
                    (int(round(a)), max(1, int(round(b)))),
                    tilt_deg, 0, 360, 1.0, thickness)
        return template

    def _expected_ratio_band(
            self, expected: ExpectedGeometry) -> Tuple[float, float]:
        cfg = self._cfg
        ratio_lo, ratio_hi = cfg.min_axis_ratio, cfg.max_axis_ratio
        if expected.axis_ratio is not None:
            ratio_lo = max(ratio_lo, expected.axis_ratio[0])
            ratio_hi = min(ratio_hi, expected.axis_ratio[1])
        if ratio_hi <= ratio_lo:
            return cfg.min_axis_ratio, cfg.max_axis_ratio
        return ratio_lo, ratio_hi

    def _vote_detect(self, normalized: np.ndarray, roi: np.ndarray,
                     polarity: str, scale: float, w: int, h: int,
                     expected: ExpectedGeometry) -> list:
        """Primary AOI-known path: valley mask -> template vote ->
        full-resolution arc-coverage verification -> local refinement.
        Returns up to ``vote_top_k`` distinct fits, unranked (the
        caller ranks all fits globally)."""
        cfg = self._cfg
        row_sigma = self._row_noise_sigma(normalized)
        mask = self._valley_mask(normalized, roi, polarity, scale,
                                 row_sigma)
        if int(mask.sum()) < 50:
            logger.warning(
                "Ellipse detection (%s ring): only %d valley points",
                polarity, int(mask.sum()))
            return []
        candidates = self._vote_candidates(mask, scale, w, h, expected)
        fits = []
        for params in candidates:
            fit = self._refine_vote_fit(normalized, row_sigma, params,
                                        scale, w, h, expected, polarity)
            if fit is not None:
                fits.append(fit)
        fits.sort(key=lambda f: (f.coverage, f.n_inliers, -f.rms_px),
                  reverse=True)
        return self._drop_duplicates(fits, w, scale)[:cfg.vote_top_k]

    @staticmethod
    def _pooled(mask: np.ndarray, ds: int) -> np.ndarray:
        h2, w2 = mask.shape[0] // ds, mask.shape[1] // ds
        return (mask[:h2 * ds, :w2 * ds]
                .reshape(h2, ds, w2, ds).max(axis=(1, 3))
                .astype(np.float32))

    def _vote_candidates(self, mask: np.ndarray, scale: float,
                         w: int, h: int,
                         expected: ExpectedGeometry) -> list:
        """Template vote over the full (b, tilt) hypothesis grid at the
        AOI-pinned semi-major axis.

        The grid is NOT strided or coarsened: both were tried against
        the real corpus and rejected — coarser max-pooling fills
        clutter-band gaps into solid runs faster than it thickens the
        thin ring, and striding both dimensions loses weak rings whose
        (b, tilt) falls between samples. Cost is contained instead by
        bounding the tilt range with the caller's scan-rotation prior
        and cropping the correlation domain to rows where the center
        prior allows a center. Deterministic: fixed grid order,
        first-occurrence argmax, square-window NMS.
        """
        cfg = self._cfg
        ratio_lo, ratio_hi = self._expected_ratio_band(expected)
        b_step = max(1.0, cfg.vote_b_step_px * scale)
        tilt_limit = min(
            cfg.vote_tilt_range_deg
            if expected.max_abs_tilt_deg is None
            else expected.max_abs_tilt_deg,
            cfg.max_tilt_deg)
        tilts = np.arange(-tilt_limit, tilt_limit + 1e-6,
                          cfg.vote_tilt_step_deg)
        cx_lo, cx_hi = cfg.center_x_frac[0] * w, cfg.center_x_frac[1] * w
        cy_lo, cy_hi = cfg.center_y_frac[0] * h, cfg.center_y_frac[1] * h

        ds = cfg.vote_downsample
        pooled = self._pooled(mask, ds)
        thickness = max(1, int(round(
            cfg.vote_template_thickness_px * scale / ds)))

        # Rows outside the center prior (plus the tallest template's
        # half-height) can never host a peak we would keep — crop them
        # out of every correlation.
        a_max = expected.semi_major_px * max(cfg.vote_a_frac_offsets)
        b_max = ratio_hi * a_max
        half_h_max = math.hypot(a_max * math.sin(math.radians(tilt_limit)),
                                b_max) / ds
        row0 = max(0, int(cy_lo / ds - half_h_max - thickness - 3))
        row1 = min(pooled.shape[0],
                   int(cy_hi / ds + half_h_max + thickness + 3) + 1)
        pooled = pooled[row0:row1]

        peaks = []  # (score, hypothesis index, cy, cx, a, b, tilt)
        hyp = 0
        for a_frac in cfg.vote_a_frac_offsets:
            a = expected.semi_major_px * a_frac
            b_values = np.arange(
                max(ratio_lo * a, cfg.semi_minor_floor_px),
                ratio_hi * a + 1e-6, b_step)
            for b in b_values:
                for tilt in tilts:
                    hyp += 1
                    template = self._perimeter_template(
                        a / ds, b / ds, float(tilt), thickness)
                    if (template.shape[0] > pooled.shape[0]
                            or template.shape[1] > pooled.shape[1]):
                        continue
                    response = cv2.matchTemplate(pooled, template,
                                                 cv2.TM_CCORR)
                    response /= max(float(template.sum()), 1.0)
                    ty = (template.shape[0] - 1) // 2 + row0
                    tx = (template.shape[1] - 1) // 2
                    for _ in range(cfg.vote_peaks_per_hypothesis):
                        index = int(np.argmax(response))
                        py, px = divmod(index, response.shape[1])
                        value = float(response[py, px])
                        if value <= 0.0:
                            break
                        response[max(0, py - 12):py + 13,
                                 max(0, px - 12):px + 13] = 0.0
                        cx_full = float((px + tx) * ds)
                        cy_full = float((py + ty) * ds)
                        if (cx_lo < cx_full < cx_hi
                                and cy_lo < cy_full < cy_hi):
                            peaks.append((value, hyp, cy_full, cx_full,
                                          a, float(b), float(tilt)))
        peaks.sort(key=lambda p: (-p[0], p[1], p[2], p[3]))
        kept = []
        for value, _, cy_full, cx_full, a, b, tilt in peaks:
            duplicate = any(
                math.hypot(cx_full - k[0], cy_full - k[1]) < 10.0 * ds
                and abs(b - k[3]) < 2.0 * b_step
                for k in kept)
            if duplicate:
                continue
            kept.append((cx_full, cy_full, a, b, tilt))
            if len(kept) >= cfg.vote_max_candidates:
                break
        return kept

    def _collect_troughs(self, normalized: np.ndarray,
                         row_sigma: np.ndarray, params,
                         scale: float) -> np.ndarray:
        """Subpixel intensity-valley troughs along the ellipse's
        normals: one point per normal whose valley depth clears the
        per-row noise. Independent of the vote mask, so the refinement
        measures the image rather than the thresholding choices."""
        cx, cy, a, b, tilt_deg = params
        h = normalized.shape[0]
        theta = math.radians(tilt_deg)
        ct, st = math.cos(theta), math.sin(theta)
        t = np.linspace(0.0, 2.0 * math.pi, _TROUGH_NORMALS,
                        endpoint=False)
        ex, ey = a * np.cos(t), b * np.sin(t)
        px = cx + ex * ct - ey * st
        py = cy + ex * st + ey * ct
        nx0, ny0 = np.cos(t) / a, np.sin(t) / b
        norm = np.hypot(nx0, ny0)
        nx0, ny0 = nx0 / norm, ny0 / norm
        nx = nx0 * ct - ny0 * st
        ny = nx0 * st + ny0 * ct
        offsets = np.arange(-_TROUGH_HALF_SPAN_REF_PX * scale,
                            _TROUGH_HALF_SPAN_REF_PX * scale + 1e-6,
                            _TROUGH_STEP_REF_PX * scale,
                            dtype=np.float32)
        map_x = (px[:, None] + offsets[None, :] * nx[:, None]) \
            .astype(np.float32)
        map_y = (py[:, None] + offsets[None, :] * ny[:, None]) \
            .astype(np.float32)
        profiles = cv2.remap(normalized, map_x, map_y, cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=float("nan"))
        points = []
        depths = []
        n = len(offsets)
        for k in range(_TROUGH_NORMALS):
            profile = profiles[k]
            if np.isnan(profile).any():
                continue
            i = int(np.argmin(profile[1:n - 1])) + 1
            yk = int(np.clip(round(py[k]), 0, h - 1))
            depth_sigma = (0.5 * (profile[0] + profile[-1])
                           - profile[i]) / row_sigma[yk]
            if depth_sigma < _TROUGH_MIN_DEPTH_SIGMA:
                continue
            y0, y1, y2 = profile[i - 1], profile[i], profile[i + 1]
            denominator = y0 - 2 * y1 + y2
            sub = (0.5 * (y0 - y2) / denominator
                   if abs(denominator) > 1e-9 else 0.0)
            sub = float(np.clip(sub, -1.0, 1.0))
            off = offsets[i] + sub * _TROUGH_STEP_REF_PX * scale
            points.append((px[k] + off * nx[k], py[k] + off * ny[k]))
            depths.append(depth_sigma)
        return (np.array(points, np.float32).reshape(-1, 2),
                np.array(depths, np.float32))

    @staticmethod
    def _largest_trough_gap_deg(points: np.ndarray, params) -> float:
        """Largest contiguous hole, in parametric degrees, in the
        troughs' angular coverage of the ellipse."""
        cx, cy, a, b, theta_deg = params
        c, s = math.cos(math.radians(theta_deg)), math.sin(
            math.radians(theta_deg))
        dx, dy = points[:, 0] - cx, points[:, 1] - cy
        u = (dx * c + dy * s) / a
        v = (-dx * s + dy * c) / b
        angles = np.sort(np.degrees(np.arctan2(v, u)))
        if len(angles) < 2:
            return 360.0
        gaps = np.diff(angles)
        wrap = angles[0] + 360.0 - angles[-1]
        return float(max(gaps.max(), wrap))

    def _refine_vote_fit(self, normalized: np.ndarray,
                         row_sigma: np.ndarray, params0, scale: float,
                         w: int, h: int, expected: ExpectedGeometry,
                         polarity: str) -> Optional[EllipseFit]:
        """Intensity-trough refinement + scoring of one vote lock.

        Two rounds: collect troughs around the current parameters,
        trim against them (structured outliers — debris on the arc, a
        parallel groove edge — are spatially coherent and would drag
        the algebraic fit), free-fit, one MAD rejection pass.
        ``coverage`` becomes the STRONG-trough fraction: the share of
        perimeter normals whose valley depth clears
        ``_TROUGH_STRONG_DEPTH_SIGMA``. Unlike point-mask sector
        occupancy this cannot saturate on dense clutter, and shallow
        texture valleys do not count — it ranks competing hypotheses
        by actual groove evidence.

        Flat-ellipse guard: cv2.fitEllipseDirect is unstable on
        near-degenerate rings, so a fit that leaves the geometry
        priors (or jumps the semi-major axis) reverts to the analytic
        vote lock, which is legal by construction.
        """
        params = params0
        troughs = None
        depths = None
        previous = None
        for _ in range(3):
            collected, collected_depths = self._collect_troughs(
                normalized, row_sigma, params, scale)
            if len(collected) < _TROUGH_MIN_COUNT:
                break
            trim = _TROUGH_TRIM_REF_PX * scale
            near = self._sampson_distance(collected, params) < trim
            if int(near.sum()) < _TROUGH_MIN_COUNT:
                break
            kept, kept_depths = collected[near], collected_depths[near]
            troughs, depths = kept, kept_depths
            refined = self._fit_direct(kept)
            if (refined is None
                    or not self._geometry_ok(refined, w, h, expected)
                    or abs(refined[2] - params0[2]) > 0.08 * params0[2]):
                break
            residuals = self._sampson_distance(kept, refined)
            mad = float(np.median(np.abs(residuals - np.median(residuals))))
            keep = residuals <= np.median(residuals) + 3.0 * 1.4826 \
                * max(mad, 1e-3)
            if keep.sum() >= _TROUGH_MIN_COUNT and not keep.all():
                refit = self._fit_direct(kept[keep])
                if (refit is not None
                        and self._geometry_ok(refit, w, h, expected)
                        and abs(refit[2] - params0[2])
                        <= 0.08 * params0[2]):
                    refined = refit
                    troughs, depths = kept[keep], kept_depths[keep]
            params = refined
            if (previous is not None
                    and math.hypot(params[0] - previous[0],
                                   params[1] - previous[1]) < 0.3 * scale
                    and abs(params[3] - previous[3]) < 0.3 * scale):
                break  # converged; further rounds cannot move it
            previous = params
        if troughs is None or len(troughs) < _TROUGH_MIN_COUNT:
            return None
        strong_mask = depths >= _TROUGH_STRONG_DEPTH_SIGMA
        strong = int(strong_mask.sum())
        if strong < _VOTE_MIN_STRONG_COVERAGE * _TROUGH_NORMALS:
            logger.info(
                "Ellipse candidate rejected (%s ring): only %d strong "
                "troughs — noise, not a groove", polarity, strong)
            return None
        # Gap criterion over STRONG troughs only: shallow noise minima
        # pass the acceptance threshold often enough (extreme-value
        # statistics of the sampled profile) to plug the tip holes a
        # clutter-band pair leaves — deep groove evidence does not lie.
        if self._largest_trough_gap_deg(troughs[strong_mask], params) \
                > _TROUGH_MAX_GAP_DEG:
            logger.info(
                "Ellipse candidate rejected (%s ring): strong-trough "
                "coverage has a hole larger than %.0f deg — clutter "
                "arcs, not a closed groove", polarity,
                _TROUGH_MAX_GAP_DEG)
            return None
        cx, cy, a, b, theta = params
        rms = float(np.sqrt(np.mean(
            self._sampson_distance(troughs, params) ** 2)))
        fit = EllipseFit(
            center_x_px=round(cx, 2),
            center_y_px=round(cy, 2),
            semi_major_px=round(a, 2),
            semi_minor_px=round(b, 2),
            tilt_deg=round(theta, 2),
            n_inliers=len(troughs),
            coverage=round(strong / _TROUGH_NORMALS, 3),
            rms_px=round(rms, 3),
            polarity=polarity,
            method="vote",
        )
        logger.info(
            "Ellipse locked by center-vote (%s ring): center=(%.1f, "
            "%.1f) px, 2a=%.1f px, 2b=%.1f px, tilt=%.2f deg, "
            "inliers=%d, coverage=%.2f, rms=%.2f px",
            fit.polarity, fit.center_x_px, fit.center_y_px,
            2 * fit.semi_major_px, 2 * fit.semi_minor_px, fit.tilt_deg,
            fit.n_inliers, fit.coverage, fit.rms_px,
        )
        return fit

    # -----------------------------------------------------------------
    # Geometry helpers (pure numpy)
    # -----------------------------------------------------------------

    @staticmethod
    def _normalize_axes(d1: float, d2: float,
                        angle: float) -> Tuple[float, float, float]:
        """Return (a, b, major-axis angle in (-90, 90])."""
        if d1 >= d2:
            a, b, theta = d1 / 2.0, d2 / 2.0, angle
        else:
            a, b, theta = d2 / 2.0, d1 / 2.0, angle + 90.0
        theta = (theta + 90.0) % 180.0 - 90.0
        return a, b, theta

    @staticmethod
    def _conic_coefficients(cx, cy, a, b, theta_deg):
        """Conic Q(x,y)=Ax^2+Bxy+Cy^2+Dx+Ey+F for the ellipse."""
        c, s = math.cos(math.radians(theta_deg)), math.sin(
            math.radians(theta_deg))
        ia2, ib2 = 1.0 / (a * a), 1.0 / (b * b)
        A = c * c * ia2 + s * s * ib2
        B = 2.0 * c * s * (ia2 - ib2)
        C = s * s * ia2 + c * c * ib2
        D = -2.0 * A * cx - B * cy
        E = -B * cx - 2.0 * C * cy
        F = A * cx * cx + B * cx * cy + C * cy * cy - 1.0
        return A, B, C, D, E, F

    @classmethod
    def _sampson_distance(cls, points: np.ndarray, params) -> np.ndarray:
        """
        First-order geometric (Sampson) distance from points to the
        ellipse, vectorized in numpy. Accurate near the curve, which
        is exactly where the inlier tolerance operates.
        """
        A, B, C, D, E, F = cls._conic_coefficients(*params)
        x, y = points[:, 0], points[:, 1]
        q = A * x * x + B * x * y + C * y * y + D * x + E * y + F
        gx = 2.0 * A * x + B * y + D
        gy = B * x + 2.0 * C * y + E
        grad = np.sqrt(gx * gx + gy * gy)
        return np.abs(q) / np.maximum(grad, 1e-12)

    def _sector_coverage(self, points: np.ndarray, params) -> float:
        """Fraction of parametric sectors containing an inlier."""
        cx, cy, a, b, theta_deg = params
        c, s = math.cos(math.radians(theta_deg)), math.sin(
            math.radians(theta_deg))
        dx, dy = points[:, 0] - cx, points[:, 1] - cy
        u = (dx * c + dy * s) / a
        v = (-dx * s + dy * c) / b
        t = np.arctan2(v, u)
        sectors = ((t + math.pi) / (2 * math.pi)
                   * self._cfg.coverage_sectors).astype(int)
        sectors = np.clip(sectors, 0, self._cfg.coverage_sectors - 1)
        return float(len(np.unique(sectors))) / self._cfg.coverage_sectors

    def _geometry_ok(self, params, w: int, h: int,
                     expected: Optional[ExpectedGeometry] = None) -> bool:
        cfg = self._cfg
        cx, cy, a, b, theta = params
        a_lo, a_hi = cfg.semi_major_frac[0] * w, cfg.semi_major_frac[1] * w
        ratio_lo, ratio_hi = cfg.min_axis_ratio, cfg.max_axis_ratio
        if expected is not None:
            if expected.semi_major_px is not None:
                tolerance = cfg.expected_semi_major_tolerance_frac
                a_lo = expected.semi_major_px * (1.0 - tolerance)
                a_hi = expected.semi_major_px * (1.0 + tolerance)
            if expected.axis_ratio is not None:
                ratio_lo = max(ratio_lo, expected.axis_ratio[0])
                ratio_hi = min(ratio_hi, expected.axis_ratio[1])
        return (cfg.center_x_frac[0] * w < cx < cfg.center_x_frac[1] * w
                and cfg.center_y_frac[0] * h < cy < cfg.center_y_frac[1] * h
                and a_lo < a < a_hi
                and b > cfg.semi_minor_floor_px
                and ratio_lo < b / a < ratio_hi
                and abs(theta) < cfg.max_tilt_deg)

    # -----------------------------------------------------------------
    # RANSAC core
    # -----------------------------------------------------------------

    def _fit_direct(self, sample: np.ndarray):
        try:
            (cx, cy), (d1, d2), angle = cv2.fitEllipseDirect(
                sample.astype(np.float32))
        except cv2.error:
            return None
        if not np.isfinite([cx, cy, d1, d2, angle]).all() or min(d1, d2) <= 0:
            return None
        a, b, theta = self._normalize_axes(d1, d2, angle)
        return (float(cx), float(cy), a, b, theta)

    def _ransac_fit(self, points: np.ndarray, w: int, h: int,
                    polarity: str,
                    expected: Optional[ExpectedGeometry] = None,
                    ) -> Optional[EllipseFit]:
        cfg = self._cfg
        tolerance_px = (cfg.inlier_tolerance_px
                        * w / cfg.reference_width_px)
        rng = np.random.default_rng(cfg.random_seed)
        order = np.argsort(points[:, 0])
        bins = [b for b in np.array_split(order, cfg.sample_bins) if len(b)]

        best_score, best_inliers, best_params = -1.0, None, None
        for _ in range(cfg.n_iterations):
            picks = [points[rng.choice(b)] for b in bins]
            extra = points[rng.choice(len(points), size=3, replace=False)]
            sample = np.vstack([picks, extra])
            if len(np.unique(sample, axis=0)) < 6:
                continue
            params = self._fit_direct(sample)
            if params is None or not self._geometry_ok(params, w, h,
                                                       expected):
                continue
            distances = self._sampson_distance(points, params)
            inliers = distances < tolerance_px
            n_in = int(inliers.sum())
            if n_in < 20:
                continue
            score = n_in * self._sector_coverage(points[inliers], params)
            if score > best_score:
                best_score, best_inliers, best_params = score, inliers, params

        if best_params is None:
            logger.warning("Ellipse detection (%s ring): RANSAC found no "
                           "candidate satisfying the geometry priors",
                           polarity)
            return None

        # Refinement rounds on inliers.
        params, inliers = best_params, best_inliers
        for _ in range(cfg.refinement_rounds):
            subset = points[inliers]
            if len(subset) < 20:
                break
            refined = self._fit_direct(subset)
            if refined is None or not self._geometry_ok(refined, w, h,
                                                        expected):
                break
            params = refined
            inliers = self._sampson_distance(points, params) \
                < tolerance_px

        cx, cy, a, b, theta = params
        inlier_pts = points[inliers]
        rms = float(np.sqrt(np.mean(
            self._sampson_distance(inlier_pts, params) ** 2)))
        fit = EllipseFit(
            center_x_px=round(cx, 2),
            center_y_px=round(cy, 2),
            semi_major_px=round(a, 2),
            semi_minor_px=round(b, 2),
            tilt_deg=round(theta, 2),
            n_inliers=int(inliers.sum()),
            coverage=round(self._sector_coverage(inlier_pts, params), 3),
            rms_px=round(rms, 3),
            polarity=polarity,
        )
        logger.info(
            "Ellipse detected (%s ring): center=(%.1f, %.1f) px, "
            "2a=%.1f px, 2b=%.1f px, tilt=%.2f deg, inliers=%d, "
            "coverage=%.2f, rms=%.2f px",
            fit.polarity, fit.center_x_px, fit.center_y_px,
            2 * fit.semi_major_px, 2 * fit.semi_minor_px, fit.tilt_deg,
            fit.n_inliers, fit.coverage, fit.rms_px,
        )
        return fit
