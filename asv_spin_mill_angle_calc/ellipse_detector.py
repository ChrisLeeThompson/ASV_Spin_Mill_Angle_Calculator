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
   the vertical brightness gradient and vignetting.
2. Hat morphology enhances thin ridges: black-hat for a dark ring on a
   light surface, top-hat for a bright ring on a dark surface. In
   ``auto`` polarity both responses are processed and the
   better-scoring fit wins.
3. Percentile threshold restricted to the sharp central band of the
   image yields candidate points; a connected-component filter keeps
   elongated structures (ring arcs) and drops compact blobs (debris).
4. Guided RANSAC: samples are spread across horizontal bins so every
   candidate spans the ring, fitted with ``cv2.fitEllipseDirect``,
   gated by geometry priors, and scored by inlier count times angular
   sector coverage. Inlier gating uses the Sampson (first-order
   geometric) distance of the conic, computed in pure numpy.
5. Three refinement rounds re-fit on inliers.

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


# -----------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------

@dataclass(frozen=True)
class EllipseDetectorConfig:
    """
    Tunable parameters and geometry priors for the detector.

    The default priors describe the spin mill fiducial as imaged by
    the ASV workflow: a wide, very flat, near-horizontal ellipse
    roughly centered in the field of view. All fractions are relative
    to image width/height so the priors survive resolution changes.
    """
    # Preprocessing
    blur_sigma: float = 25.0
    hat_kernel_px: int = 9
    threshold_percentile: float = 98.0
    roi_top_frac: float = 0.15
    roi_bottom_frac: float = 0.80
    polarity: str = POLARITY_AUTO
    # Component filter
    min_component_area_px: int = 8
    min_component_length_px: int = 30
    # RANSAC
    n_iterations: int = 1500
    sample_bins: int = 6
    inlier_tolerance_px: float = 2.5
    coverage_sectors: int = 36
    refinement_rounds: int = 3
    random_seed: Optional[int] = 42
    # Geometry priors
    center_x_frac: Tuple[float, float] = (0.30, 0.70)
    center_y_frac: Tuple[float, float] = (0.20, 0.75)
    semi_major_frac: Tuple[float, float] = (0.25, 0.60)
    semi_minor_px: Tuple[float, float] = (4.0, 80.0)
    max_axis_ratio: float = 0.35
    max_tilt_deg: float = 12.0


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

    def detect(self, image: np.ndarray) -> Optional[EllipseFit]:
        """
        Detect the fiducial ellipse in a grayscale image.

        Args:
            image: 2D uint8/uint16/float array. Color images are
                converted with ``cv2.cvtColor``.

        Returns:
            An ``EllipseFit``, or ``None`` if detection failed under
            every polarity the configuration allows.
        """
        gray = self._to_gray(image)
        h, w = gray.shape
        best: Optional[EllipseFit] = None
        for polarity in self._polarities():
            points = self._candidate_points(gray, polarity)
            if len(points) < 50:
                logger.warning(
                    "Ellipse detection (%s ring): only %d candidate "
                    "points", polarity, len(points))
                continue
            fit = self._ransac_fit(points, w, h, polarity)
            if fit is not None and (best is None or fit.score > best.score):
                best = fit
        return best

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

    def _candidate_points(self, gray: np.ndarray,
                          polarity: str) -> np.ndarray:
        cfg = self._cfg
        h, w = gray.shape
        g = gray.astype(np.float32) + 1.0
        background = cv2.GaussianBlur(g, (0, 0), cfg.blur_sigma)
        normalized = g / background
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (cfg.hat_kernel_px, cfg.hat_kernel_px))
        ridges = cv2.morphologyEx(
            normalized, _MORPH_BY_POLARITY[polarity], kernel)

        roi = np.zeros_like(ridges, dtype=bool)
        roi[int(cfg.roi_top_frac * h):int(cfg.roi_bottom_frac * h),
            int(0.02 * w):int(0.98 * w)] = True
        threshold = np.percentile(ridges[roi], cfg.threshold_percentile)
        mask = ((ridges > threshold) & roi).astype(np.uint8)

        # Keep elongated / thin components; drop compact debris blobs.
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        keep = np.zeros(n, dtype=bool)
        for i in range(1, n):
            _x, _y, bw, bh, area = stats[i]
            if area < cfg.min_component_area_px:
                continue
            fill = area / float(bw * bh)
            elongated = (bw >= 4 * bh) or (bh >= 4 * bw)
            long_enough = max(bw, bh) >= cfg.min_component_length_px
            if ((elongated and long_enough)
                    or (long_enough and fill < 0.45)
                    or bw >= 4 * cfg.min_component_length_px):
                keep[i] = True
        ys, xs = np.nonzero(keep[labels])
        return np.column_stack([xs, ys]).astype(np.float32)

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

    def _geometry_ok(self, params, w: int, h: int) -> bool:
        cfg = self._cfg
        cx, cy, a, b, theta = params
        return (cfg.center_x_frac[0] * w < cx < cfg.center_x_frac[1] * w
                and cfg.center_y_frac[0] * h < cy < cfg.center_y_frac[1] * h
                and cfg.semi_major_frac[0] * w < a < cfg.semi_major_frac[1] * w
                and cfg.semi_minor_px[0] < b < cfg.semi_minor_px[1]
                and b / a < cfg.max_axis_ratio
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
                    polarity: str) -> Optional[EllipseFit]:
        cfg = self._cfg
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
            if params is None or not self._geometry_ok(params, w, h):
                continue
            distances = self._sampson_distance(points, params)
            inliers = distances < cfg.inlier_tolerance_px
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
            if refined is None or not self._geometry_ok(refined, w, h):
                break
            params = refined
            inliers = self._sampson_distance(points, params) \
                < cfg.inlier_tolerance_px

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
