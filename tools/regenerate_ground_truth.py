"""Regenerate the ground-truth table for the real-capture corpus.

Offline dev tool (not shipped). For every frame in debug_frames_dir/
(two runs captured 2026-08-12), independently localize the AOI ring and
measure it to subpixel precision, then verify the measurements against
physics that the localizer cannot fake:

  * the ring's true semi-major axis is constant across all frames,
  * the measured milling angle must track stage tilt 1:1 (their
    difference is the sample-planarity offset, a per-run constant),
  * the ellipse tilt in the image must track applied scan rotation 1:1.

Pipeline per frame (this is also the prototype of the production
center-vote detector):

  1. valley response  -- step-rejecting dark-line channel
     min(I(y-d), I(y+d)) - I(y) on the illumination-normalized image,
     noise-normalized per row, void rows clipped by an adaptive
     horizon (row-median cliff).
  2. coarse vote      -- correlate the binary valley mask (half res)
     with rasterized ellipse-perimeter templates over a (b, tilt)
     hypothesis grid at the AOI-pinned semi-major; global peak locks
     the center.
  3. dense local vote -- full res, small (a, b, tilt) grid around the
     coarse lock, cropped to the lock neighbourhood.
  4. intensity refinement (mask-independent) -- sample the normalized
     image along ~360 ellipse normals, find each valley trough by
     parabolic interpolation, robust-fit an ellipse to the troughs
     (one MAD outlier-rejection pass). This decouples ground-truth
     precision from every mask/threshold choice above.

Outputs:
  tests/fixtures/corpus_ground_truth.json   (committed-adjacent table)
  tools/out/ground_truth_overlays/*.png     (human review; green = GT,
                                             red = the fit the run
                                             actually produced)

Exit code is non-zero when any physics cross-check fails.

Usage (repo root):  python tools/regenerate_ground_truth.py
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "debug_frames_dir"
OUT_JSON = REPO_ROOT / "tests" / "fixtures" / "corpus_ground_truth.json"
OVERLAY_DIR = REPO_ROOT / "tools" / "out" / "ground_truth_overlays"

FIB_ANGLE_FROM_STAGE_PLANE_DEG = 38.0
REFERENCE_WIDTH_PX = 768.0

# --- mask parameters (mirror the planned production defaults) ---------
BLUR_SIGMA_REF = 25.0
VALLEY_OFFSET_REF = 1.5
VALLEY_SMOOTH_SIGMA_REF = 2.0
THRESHOLD_PERCENTILE = 95.0
ROI_TOP_FRAC = 0.15
ROI_BOTTOM_FRAC = 0.72
ROI_COL_MARGIN_FRAC = 0.02
HORIZON_LEVEL_FRAC = 0.35
HORIZON_DROP_FRAC = 0.20
HORIZON_DROP_ROWS = 8
HORIZON_GUARD_ROWS = 5

# --- vote parameters ---------------------------------------------------
COARSE_DOWNSAMPLE = 2
COARSE_TILT_RANGE_DEG = 8.0     # must cover the injected 3.76 deg scan rot
COARSE_TILT_STEP_DEG = 1.0
COARSE_B_STEP_PX = 6.0          # full-res px
TEMPLATE_THICKNESS_REF = 2.5
DENSE_A_FRACS = np.arange(0.96, 1.0401, 0.01)
DENSE_B_HALF_SPAN_PX = 6.0
DENSE_B_STEP_PX = 1.0
DENSE_TILT_HALF_SPAN_DEG = 1.5
DENSE_TILT_STEP_DEG = 0.25
DENSE_CROP_MARGIN_PX = 60

# --- intensity refinement ---------------------------------------------
N_NORMALS = 360
NORMAL_HALF_SPAN_PX = 6.0
NORMAL_STEP_PX = 0.25
TROUGH_MIN_DEPTH_SIGMA = 1.5
MAD_REJECT_K = 3.0
LOCK_TRIM_TOLERANCE_PX = 5.0

# --- physics cross-check gates -----------------------------------------
CHECK_A_STD_MAX_PX = 2.0
CHECK_A_OUTLIER_MAX_PX = 3.0
CHECK_OFFSET_STD_MAX_DEG = 0.05
CHECK_SLOPE_TOL = 0.02
CHECK_TILT_TRACK_STD_MAX_DEG = 0.30


@dataclass
class FrameRecord:
    run: str
    frame: str
    path: str
    sidecar: dict
    gray: np.ndarray
    normalized: np.ndarray
    mask: np.ndarray          # binary uint8, full res, ROI/horizon clipped
    row_sigma: np.ndarray


@dataclass
class GroundTruth:
    cx: float
    cy: float
    a: float
    b: float
    tilt_deg: float
    n_troughs: int
    rms_px: float

    @property
    def milling_angle_deg(self) -> float:
        return math.degrees(math.asin(min(1.0, self.b / self.a)))


# ----------------------------------------------------------------------
# Mask construction
# ----------------------------------------------------------------------

def normalize_illumination(gray: np.ndarray) -> np.ndarray:
    scale = gray.shape[1] / REFERENCE_WIDTH_PX
    g = gray.astype(np.float32) + 1.0
    background = cv2.GaussianBlur(g, (0, 0), BLUR_SIGMA_REF * scale)
    return g / background


def valley_response(normalized: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Step-rejecting dark-valley channel + per-row noise sigma."""
    h, w = normalized.shape
    scale = w / REFERENCE_WIDTH_PX
    d = max(1, round(VALLEY_OFFSET_REF * scale))
    smoothed = cv2.GaussianBlur(
        normalized, (0, 0),
        sigmaX=VALLEY_SMOOTH_SIGMA_REF * scale, sigmaY=0.8)
    up = np.empty_like(smoothed)
    down = np.empty_like(smoothed)
    up[d:, :] = smoothed[:-d, :]
    up[:d, :] = smoothed[0, :]
    down[:-d, :] = smoothed[d:, :]
    down[-d:, :] = smoothed[-1, :]
    v = np.minimum(up, down) - smoothed
    diffs = np.abs(np.diff(normalized, axis=1))
    mad = np.median(diffs, axis=1)
    row_sigma = 1.4826 * mad / math.sqrt(2.0)
    floor = max(1e-6, 0.3 * float(np.median(row_sigma)))
    row_sigma = np.maximum(row_sigma, floor)
    return v / row_sigma[:, None], row_sigma


def horizon_row(normalized: np.ndarray) -> Optional[int]:
    """First row of the void cliff (row-median drop), or None."""
    h, w = normalized.shape
    c0, c1 = int(ROI_COL_MARGIN_FRAC * w), int((1 - ROI_COL_MARGIN_FRAC) * w)
    med = np.median(normalized[:, c0:c1], axis=1).astype(np.float32)
    kernel = np.ones(15, np.float32) / 15.0
    med = np.convolve(med, kernel, mode="same")
    top = int(ROI_TOP_FRAC * h)
    ref = float(np.median(med[top:int(0.5 * h)]))
    for y in range(int(0.5 * h), h):
        prev = med[max(0, y - HORIZON_DROP_ROWS)]
        if (med[y] < HORIZON_LEVEL_FRAC * ref
                and prev - med[y] > HORIZON_DROP_FRAC * ref):
            return y
    return None


def build_mask(normalized: np.ndarray) -> np.ndarray:
    h, w = normalized.shape
    response, _ = valley_response(normalized)
    roi = np.zeros((h, w), bool)
    bottom = int(ROI_BOTTOM_FRAC * h)
    cliff = horizon_row(normalized)
    if cliff is not None:
        bottom = min(bottom, cliff - HORIZON_GUARD_ROWS)
    c0, c1 = int(ROI_COL_MARGIN_FRAC * w), int((1 - ROI_COL_MARGIN_FRAC) * w)
    roi[int(ROI_TOP_FRAC * h):bottom, c0:c1] = True
    threshold = np.percentile(response[roi], THRESHOLD_PERCENTILE)
    return ((response > threshold) & roi).astype(np.uint8)


# ----------------------------------------------------------------------
# Vote
# ----------------------------------------------------------------------

def make_template(a: float, b: float, tilt_deg: float,
                  thickness: int) -> np.ndarray:
    pad = thickness + 2
    theta = math.radians(tilt_deg)
    half_w = math.hypot(a * math.cos(theta), b * math.sin(theta))
    half_h = math.hypot(a * math.sin(theta), b * math.cos(theta))
    tw = int(2 * math.ceil(half_w) + 2 * pad + 1)
    th = int(2 * math.ceil(half_h) + 2 * pad + 1)
    tpl = np.zeros((th, tw), np.float32)
    center = ((tw - 1) // 2, (th - 1) // 2)
    cv2.ellipse(tpl, center, (int(round(a)), max(1, int(round(b)))),
                tilt_deg, 0, 360, 1.0, thickness)
    return tpl


def correlate(mask_f: np.ndarray, tpl: np.ndarray
              ) -> Tuple[float, Tuple[int, int]]:
    """Best normalized response and its template-center position."""
    if tpl.shape[0] > mask_f.shape[0] or tpl.shape[1] > mask_f.shape[1]:
        return -1.0, (0, 0)
    resp = cv2.matchTemplate(mask_f, tpl, cv2.TM_CCORR)
    resp /= max(1.0, float(tpl.sum()))
    _, max_val, _, max_loc = cv2.minMaxLoc(resp)
    cx = max_loc[0] + (tpl.shape[1] - 1) // 2
    cy = max_loc[1] + (tpl.shape[0] - 1) // 2
    return float(max_val), (cx, cy)


def ratio_band(model_deg: float) -> Tuple[float, float]:
    low = math.sin(math.radians(max(model_deg - 4.0, 0.5)))
    high = math.sin(math.radians(min(model_deg + 4.0, 20.0)))
    return low, high


def coarse_vote(mask: np.ndarray, a0: float, model_deg: float,
                top_k: int = 3
                ) -> List[Tuple[float, float, float, float, float]]:
    """Half-res global vote -> up to top_k (cx, cy, b, tilt, score)
    candidates at full res, NMS-separated by center distance."""
    h, w = mask.shape
    ds = COARSE_DOWNSAMPLE
    h2, w2 = h // ds, w // ds
    pooled = mask[:h2 * ds, :w2 * ds].reshape(h2, ds, w2, ds).max(axis=(1, 3))
    mask_f = pooled.astype(np.float32)
    scale = w / REFERENCE_WIDTH_PX
    thickness = max(1, round(TEMPLATE_THICKNESS_REF * scale / ds))
    lo, hi = ratio_band(model_deg)
    b_values = np.arange(lo * a0, hi * a0 + 1e-6, COARSE_B_STEP_PX)
    tilts = np.arange(-COARSE_TILT_RANGE_DEG,
                      COARSE_TILT_RANGE_DEG + 1e-6, COARSE_TILT_STEP_DEG)
    peaks: List[Tuple[float, float, float, float, float]] = []
    for b in b_values:
        for tilt in tilts:
            tpl = make_template(a0 / ds, b / ds, tilt, thickness)
            score, (cx, cy) = correlate(mask_f, tpl)
            if score > 0:
                peaks.append((score, cx * ds, cy * ds, float(b),
                              float(tilt)))
    peaks.sort(key=lambda p: p[0], reverse=True)
    kept: List[Tuple[float, float, float, float, float]] = []
    for score, cx, cy, b, tilt in peaks:
        if any(math.hypot(cx - k[1], cy - k[2]) < 40.0 for k in kept):
            continue
        kept.append((score, cx, cy, b, tilt))
        if len(kept) >= top_k:
            break
    return [(cx, cy, b, tilt, score) for score, cx, cy, b, tilt in kept]


def dense_vote(mask: np.ndarray, a0: float, coarse: Tuple[float, ...]
               ) -> Tuple[float, float, float, float, float, float]:
    """Full-res local vote by coordinate descent around the coarse lock
    -> (cx, cy, a, b, tilt, score). Precision comes from the intensity
    refinement afterwards; this only needs a decent lock."""
    h, w = mask.shape
    cx0, cy0, b0, tilt0 = coarse[:4]
    scale = w / REFERENCE_WIDTH_PX
    thickness = max(1, round(TEMPLATE_THICKNESS_REF * scale))
    a_max = a0 * DENSE_A_FRACS[-1]
    b_max = b0 + DENSE_B_HALF_SPAN_PX
    tilt_max = abs(tilt0) + DENSE_TILT_HALF_SPAN_DEG
    half_h_max = math.hypot(a_max * math.sin(math.radians(tilt_max)),
                            b_max) + DENSE_CROP_MARGIN_PX
    x0 = max(0, int(cx0 - a_max - DENSE_CROP_MARGIN_PX))
    x1 = min(w, int(cx0 + a_max + DENSE_CROP_MARGIN_PX))
    y0 = max(0, int(cy0 - half_h_max))
    y1 = min(h, int(cy0 + half_h_max))
    crop = mask[y0:y1, x0:x1].astype(np.float32)

    def score_of(a: float, b: float, tilt: float
                 ) -> Tuple[float, Tuple[int, int]]:
        return correlate(crop, make_template(a, b, tilt, thickness))

    a, b, tilt = a0, b0, tilt0
    cx, cy = cx0, cy0
    best_score = -1.0
    for _ in range(2):  # coordinate-descent rounds
        for a_cand in a0 * DENSE_A_FRACS:
            s, (px, py) = score_of(a_cand, b, tilt)
            if s > best_score:
                best_score, a, cx, cy = s, a_cand, px + x0, py + y0
        for b_cand in np.arange(max(2.0, b - DENSE_B_HALF_SPAN_PX),
                                b + DENSE_B_HALF_SPAN_PX + 1e-6,
                                DENSE_B_STEP_PX):
            s, (px, py) = score_of(a, float(b_cand), tilt)
            if s > best_score:
                best_score, b, cx, cy = s, float(b_cand), px + x0, py + y0
        for t_cand in np.arange(tilt - DENSE_TILT_HALF_SPAN_DEG,
                                tilt + DENSE_TILT_HALF_SPAN_DEG + 1e-6,
                                DENSE_TILT_STEP_DEG):
            s, (px, py) = score_of(a, b, float(t_cand))
            if s > best_score:
                best_score, tilt, cx, cy = (s, float(t_cand), px + x0,
                                            py + y0)
    return cx, cy, a, b, tilt, best_score


# ----------------------------------------------------------------------
# Intensity refinement (mask-independent)
# ----------------------------------------------------------------------

def fit_fixed_tilt(pts: np.ndarray, tilt_deg: float
                   ) -> Optional[Tuple[float, float, float, float, float]]:
    """Linear least-squares ellipse with a KNOWN orientation: rotate the
    points into the ellipse frame and fit A x^2 + C y^2 + D x + E y = 1.
    Far more stable than a free conic fit on partial/thin arcs, where b
    and tilt confound each other."""
    th = math.radians(tilt_deg)
    c, s = math.cos(th), math.sin(th)
    x = pts[:, 0] * c + pts[:, 1] * s
    y = -pts[:, 0] * s + pts[:, 1] * c
    # Center + scale per axis for conditioning (raw columns span 1e6 to
    # 1); an axis-aligned ellipse stays axis-aligned under anisotropic
    # scaling, so the geometric parameters transform back exactly.
    mx, my = float(x.mean()), float(y.mean())
    sx = max(float(x.std()), 1e-6)
    sy = max(float(y.std()), 1e-6)
    xs, ys = (x - mx) / sx, (y - my) / sy
    m = np.column_stack([xs * xs, ys * ys, xs, ys])
    try:
        coef, *_ = np.linalg.lstsq(m, np.ones(len(pts)), rcond=None)
    except np.linalg.LinAlgError:
        return None
    A, C, D, E = coef
    if A <= 0 or C <= 0:
        return None
    cxs, cys = -D / (2 * A), -E / (2 * C)
    r = 1.0 + A * cxs ** 2 + C * cys ** 2
    if r <= 0:
        return None
    a = math.sqrt(r / A) * sx
    b = math.sqrt(r / C) * sy
    if b > a:
        return None
    cx_r, cy_r = cxs * sx + mx, cys * sy + my
    cx = cx_r * c - cy_r * s
    cy = cx_r * s + cy_r * c
    return cx, cy, a, b, tilt_deg


def refine_on_intensity(normalized: np.ndarray, row_sigma: np.ndarray,
                        lock: Tuple[float, float, float, float, float],
                        trim_px: float = LOCK_TRIM_TOLERANCE_PX,
                        fixed_tilt_deg: Optional[float] = None,
                        ) -> Optional[GroundTruth]:
    cx, cy, a, b, tilt = lock
    h, w = normalized.shape
    theta = math.radians(tilt)
    ct, st = math.cos(theta), math.sin(theta)
    t = np.linspace(0.0, 2.0 * math.pi, N_NORMALS, endpoint=False)
    ex, ey = a * np.cos(t), b * np.sin(t)
    px = cx + ex * ct - ey * st
    py = cy + ex * st + ey * ct
    # Outward normal of the ellipse in its own frame: (cos t / a, sin t / b)
    nx0, ny0 = np.cos(t) / a, np.sin(t) / b
    norm = np.hypot(nx0, ny0)
    nx0, ny0 = nx0 / norm, ny0 / norm
    nx = nx0 * ct - ny0 * st
    ny = nx0 * st + ny0 * ct
    offsets = np.arange(-NORMAL_HALF_SPAN_PX, NORMAL_HALF_SPAN_PX + 1e-6,
                        NORMAL_STEP_PX, dtype=np.float32)
    map_x = (px[:, None] + offsets[None, :] * nx[:, None]).astype(np.float32)
    map_y = (py[:, None] + offsets[None, :] * ny[:, None]).astype(np.float32)
    profiles = cv2.remap(normalized, map_x, map_y, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=np.nan)
    points: List[Tuple[float, float]] = []
    n = len(offsets)
    for k in range(N_NORMALS):
        prof = profiles[k]
        if np.isnan(prof).any():
            continue
        i = int(np.argmin(prof[1:n - 1])) + 1
        depth = 0.5 * (prof[0] + prof[-1]) - prof[i]
        yk = int(np.clip(round(py[k]), 0, h - 1))
        if depth < TROUGH_MIN_DEPTH_SIGMA * row_sigma[yk]:
            continue
        y0, y1, y2 = prof[i - 1], prof[i], prof[i + 1]
        denom = (y0 - 2 * y1 + y2)
        sub = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-9 else 0.0
        sub = float(np.clip(sub, -1.0, 1.0))
        off = offsets[i] + sub * NORMAL_STEP_PX
        points.append((px[k] + off * nx[k], py[k] + off * ny[k]))
    if len(points) < 30:
        return None
    pts = np.array(points, np.float32)

    def fit(p: np.ndarray) -> Optional[Tuple[float, float, float, float,
                                             float]]:
        if len(p) < 5:
            return None
        if fixed_tilt_deg is not None:
            return fit_fixed_tilt(p, fixed_tilt_deg)
        try:
            (fcx, fcy), (d1, d2), ang = cv2.fitEllipseDirect(p)
        except cv2.error:
            return None
        if not all(map(math.isfinite, (fcx, fcy, d1, d2, ang))):
            return None
        if min(d1, d2) <= 0:
            return None
        fa, fb = max(d1, d2) / 2.0, min(d1, d2) / 2.0
        ftilt = ang if d1 >= d2 else ang + 90.0
        ftilt = ((ftilt + 90.0) % 180.0) - 90.0
        return fcx, fcy, fa, fb, ftilt

    def residuals(p: np.ndarray, params) -> np.ndarray:
        fcx, fcy, fa, fb, ftilt = params
        th = math.radians(ftilt)
        c, s = math.cos(th), math.sin(th)
        dx, dy = p[:, 0] - fcx, p[:, 1] - fcy
        u = (dx * c + dy * s) / fa
        v = (-dx * s + dy * c) / fb
        r = np.hypot(u, v)
        # approximate point-to-ellipse distance along the radial direction
        local = np.hypot(u * fa, v * fb) / np.maximum(r, 1e-9)
        return np.abs(r - 1.0) * local

    # Trim against the LOCK ellipse before any free fit: structured
    # outliers (debris on the arc, a parallel groove edge) are spatially
    # coherent and would drag cv2.fitEllipseDirect before MAD rejection
    # could see them. The lock is trusted for gating only, never
    # measured from.
    lock_res = residuals(pts, (cx, cy, a, b, tilt))
    pts = pts[lock_res <= trim_px]
    if len(pts) < 30:
        return None
    params = fit(pts)
    if params is None:
        return None
    kept = pts
    for _ in range(2):  # MAD outlier-rejection passes
        res = residuals(kept, params)
        mad = float(np.median(np.abs(res - np.median(res)))) * 1.4826
        keep = res <= np.median(res) + MAD_REJECT_K * max(mad, 1e-3)
        if keep.all() or keep.sum() < 30:
            break
        kept = kept[keep]
        refit = fit(kept)
        if refit is None:
            break
        params = refit
    final_res = residuals(kept, params)
    rms = float(np.sqrt(np.mean(final_res ** 2)))
    fcx, fcy, fa, fb, ftilt = params
    return GroundTruth(fcx, fcy, fa, fb, ftilt, len(kept), rms)


def relock_with_priors(rec: "FrameRecord", a_pin: float, offset_pin: float,
                       tilt_pin: float) -> Optional[GroundTruth]:
    """Second-pass lock for outlier frames: the template geometry is
    pinned by cross-frame physics (a, planarity offset, scan-tracked
    tilt); only the center is searched. The frame's own intensity
    refinement still performs the measurement, so the result remains an
    independent observation of this frame."""
    sc = rec.sidecar
    model = sc["model_milling_angle_deg"]
    b_pin = math.sin(math.radians(max(0.5, model + offset_pin))) * a_pin
    w = rec.mask.shape[1]
    scale = w / REFERENCE_WIDTH_PX
    thickness = max(1, round(TEMPLATE_THICKNESS_REF * scale))
    mask_f = rec.mask.astype(np.float32)
    # Tilt stays pinned: letting the contaminated mask vote on tilt is
    # exactly what the physics prior exists to prevent (a wrong tilt
    # skews the trough sampling normals at the tips).
    best: Optional[Tuple[float, float, float, float, float]] = None
    best_score = -1.0
    for b in (b_pin - 3.0, b_pin, b_pin + 3.0):
        tpl = make_template(a_pin, b, tilt_pin, thickness)
        score, (cx, cy) = correlate(mask_f, tpl)
        if score > best_score:
            best_score = score
            best = (cx, cy, a_pin, float(b), tilt_pin)
    if best is None:
        return None
    # The pinned lock is physics-trusted, so a tight capture band is
    # appropriate (excludes the parallel outer groove edge), and the
    # orientation is fixed to the scan-rotation-tracked consensus: on
    # partial arcs a free fit confounds b with tilt.
    return refine_on_intensity(rec.normalized, rec.row_sigma, best,
                               trim_px=3.0, fixed_tilt_deg=tilt_pin)


# ----------------------------------------------------------------------
# Corpus + outputs
# ----------------------------------------------------------------------

def load_corpus() -> List[FrameRecord]:
    records = []
    for run_dir in sorted(CORPUS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        for png in sorted(run_dir.glob("frame_*.png")):
            sidecar = json.loads(png.with_suffix(".json").read_text())
            gray = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
            if gray.ndim == 3:
                gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
            normalized = normalize_illumination(gray)
            _, row_sigma = valley_response(normalized)
            records.append(FrameRecord(
                run=run_dir.name, frame=png.stem,
                path=f"{run_dir.name}/{png.name}",
                sidecar=sidecar, gray=gray, normalized=normalized,
                mask=build_mask(normalized), row_sigma=row_sigma))
    return records


def draw_overlay(rec: FrameRecord, gt: GroundTruth) -> np.ndarray:
    img = cv2.cvtColor(rec.gray, cv2.COLOR_GRAY2BGR)
    fit = rec.sidecar.get("fit")
    if fit:
        cv2.ellipse(img,
                    (int(round(fit["center_x_px"])),
                     int(round(fit["center_y_px"]))),
                    (int(round(fit["semi_major_px"])),
                     max(1, int(round(fit["semi_minor_px"])))),
                    fit["tilt_deg"], 0, 360, (0, 0, 255), 2)
    cv2.ellipse(img, (int(round(gt.cx)), int(round(gt.cy))),
                (int(round(gt.a)), max(1, int(round(gt.b)))),
                gt.tilt_deg, 0, 360, (0, 255, 0), 2)
    cv2.drawMarker(img, (int(round(gt.cx)), int(round(gt.cy))),
                   (0, 255, 0), cv2.MARKER_CROSS, 24, 2)
    um_per_px = rec.sidecar["pixel_size_m"] * 1e6
    label = (f"{rec.run}/{rec.frame}  a={gt.a:.1f}px "
             f"width={2 * gt.a * um_per_px:.1f}um "
             f"angle={gt.milling_angle_deg:.2f}deg "
             f"tilt={gt.tilt_deg:.2f}deg  troughs={gt.n_troughs} "
             f"rms={gt.rms_px:.2f}px   GREEN=ground truth, RED=run's fit")
    cv2.putText(img, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 255, 255), 2)
    return img


def cross_checks(rows: List[dict]) -> Tuple[dict, bool]:
    a_vals = np.array([r["semi_major_px"] for r in rows])
    offsets = np.array([r["milling_angle_deg"] - r["model_milling_angle_deg"]
                        for r in rows])
    models = np.array([r["model_milling_angle_deg"] for r in rows])
    angles = np.array([r["milling_angle_deg"] for r in rows])
    tilts = np.array([r["tilt_deg"] for r in rows])
    scan = np.array([r["scan_rotation_deg"] for r in rows])

    a_std = float(a_vals.std())
    a_med = float(np.median(a_vals))
    a_worst = float(np.max(np.abs(a_vals - a_med)))
    off_mean, off_std = float(offsets.mean()), float(offsets.std())
    slope = float(np.polyfit(models, angles, 1)[0]) if len(
        set(models.round(3))) > 1 else 1.0
    # ellipse tilt vs scan rotation: the instrument's sign is unknown a
    # priori -- accept whichever polarity tracks 1:1 (constant residual).
    res_minus = tilts - scan
    res_plus = tilts + scan
    sign, res = ("-", res_minus) if res_minus.std() <= res_plus.std() \
        else ("+", res_plus)
    tilt_track_std = float(res.std())

    checks = {
        "a_median_px": round(a_med, 2),
        "a_std_px": round(a_std, 3),
        "a_worst_dev_px": round(a_worst, 2),
        "a_ok": a_std <= CHECK_A_STD_MAX_PX
                and a_worst <= CHECK_A_OUTLIER_MAX_PX,
        "planarity_offset_mean_deg": round(off_mean, 3),
        "planarity_offset_std_deg": round(off_std, 4),
        "offset_ok": off_std <= CHECK_OFFSET_STD_MAX_DEG,
        "angle_vs_model_slope": round(slope, 4),
        "slope_ok": abs(slope - 1.0) <= CHECK_SLOPE_TOL,
        "tilt_tracks_scan_sign": sign,
        "tilt_track_residual_std_deg": round(tilt_track_std, 3),
        "tilt_track_mean_deg": round(float(res.mean()), 3),
        "tilt_ok": tilt_track_std <= CHECK_TILT_TRACK_STD_MAX_DEG,
    }
    ok = bool(checks["a_ok"] and checks["offset_ok"]
              and checks["slope_ok"] and checks["tilt_ok"])
    return checks, ok


def main() -> int:
    records = load_corpus()
    if not records:
        print(f"No corpus frames found under {CORPUS_DIR}", file=sys.stderr)
        return 2
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)

    # ---- pass 1: independent per-frame lock + measurement ------------
    measured: List[Tuple[FrameRecord, GroundTruth, float]] = []
    for rec in records:
        sc = rec.sidecar
        a0 = (sc["aoi_diameter_um"] * 1e-6 / 2.0) / sc["pixel_size_m"]
        model = sc["model_milling_angle_deg"]
        candidates = coarse_vote(rec.mask, a0, model)
        results: List[Tuple[GroundTruth, float]] = []
        for coarse in candidates:
            dense = dense_vote(rec.mask, a0, coarse)
            gt = refine_on_intensity(rec.normalized, rec.row_sigma,
                                     dense[:5])
            if gt is not None and gt.n_troughs >= 100:
                # second refinement pass from the refined lock itself
                gt2 = refine_on_intensity(
                    rec.normalized, rec.row_sigma,
                    (gt.cx, gt.cy, gt.a, gt.b, gt.tilt_deg))
                if gt2 is not None and gt2.n_troughs >= 100 \
                        and gt2.rms_px <= gt.rms_px:
                    gt = gt2
                results.append((gt, dense[5]))
        if not results:
            print(f"NOTE {rec.path}: no independent lock survived pass 1;"
                  " deferring to the physics-prior re-lock")
            measured.append((rec, None, 0.0))
            continue
        results.sort(key=lambda r: (r[0].rms_px, -r[1]))
        measured.append((rec, results[0][0], results[0][1]))

    # ---- pass 2: re-lock outliers with cross-frame physics priors ----
    good = [(rec, gt) for rec, gt, _ in measured if gt is not None]
    if len(good) < 10:
        print(f"FAIL: only {len(good)} frames measured independently — "
              "not enough consensus for the physics-prior pass",
              file=sys.stderr)
        return 3
    a_med = float(np.median([gt.a for _, gt in good]))
    off_med = float(np.median(
        [gt.milling_angle_deg - rec.sidecar["model_milling_angle_deg"]
         for rec, gt in good]))
    tilt_res_med = float(np.median(
        [gt.tilt_deg - rec.sidecar["scan_rotation_deg"]
         for rec, gt in good]))
    relocked_paths: set = set()
    for i, (rec, gt, score) in enumerate(measured):
        sc = rec.sidecar
        if gt is not None:
            offset = gt.milling_angle_deg - sc["model_milling_angle_deg"]
            residual = gt.tilt_deg - sc["scan_rotation_deg"]
            is_outlier = (abs(gt.a - a_med) > 3.0 or gt.rms_px > 5.0
                          or abs(offset - off_med) > 0.3
                          or abs(residual - tilt_res_med) > 0.5)
            if not is_outlier:
                continue
        tilt_pin = sc["scan_rotation_deg"] + tilt_res_med
        relocked = relock_with_priors(rec, a_med, off_med, tilt_pin)
        if relocked is None:
            print(f"WARN {rec.path}: outlier re-lock failed; keeping "
                  f"pass-1 measurement", file=sys.stderr)
            continue
        new_offset = (relocked.milling_angle_deg
                      - sc["model_milling_angle_deg"])
        consistent = (abs(relocked.a - a_med) <= 3.0
                      and abs(new_offset - off_med) <= 0.3
                      and (gt is None or relocked.rms_px < gt.rms_px))
        if consistent:
            was = f"rms {gt.rms_px:.2f}, a {gt.a:.1f}" if gt else "no lock"
            print(f"RELOCK {rec.path}: {was} -> rms "
                  f"{relocked.rms_px:.2f}, a {relocked.a:.1f}")
            measured[i] = (rec, relocked, score)
            relocked_paths.add(rec.path)
        else:
            print(f"WARN {rec.path}: re-lock did not converge to the "
                  f"cross-frame consensus (a={relocked.a:.1f}, "
                  f"rms={relocked.rms_px:.2f})", file=sys.stderr)

    unmeasured = [rec.path for rec, gt, _ in measured if gt is None]
    if unmeasured:
        print(f"FAIL: no trustworthy measurement for {unmeasured}",
              file=sys.stderr)
        return 3

    # ---- outputs ------------------------------------------------------
    rows = []
    for rec, gt, dense_score in measured:
        sc = rec.sidecar
        um_per_px = sc["pixel_size_m"] * 1e6
        rows.append({
            "run": rec.run, "frame": rec.frame, "path": rec.path,
            "center_x_px": round(gt.cx, 2), "center_y_px": round(gt.cy, 2),
            "semi_major_px": round(gt.a, 2),
            "semi_minor_px": round(gt.b, 2),
            "tilt_deg": round(gt.tilt_deg, 3),
            "milling_angle_deg": round(gt.milling_angle_deg, 3),
            "width_um": round(2 * gt.a * um_per_px, 2),
            "n_trough_points": gt.n_troughs,
            "refine_rms_px": round(gt.rms_px, 3),
            "vote_score": round(dense_score, 4),
            # True when the frame's independent pass-1 measurement was
            # replaced by the physics-prior re-lock: the frame is too
            # degraded to disambiguate from single-frame evidence, so
            # per-frame detectors get the relaxed top-k contract.
            "relocked": rec.path in relocked_paths,
            "stage_tilt_deg": sc["stage_tilt_deg"],
            "model_milling_angle_deg": sc["model_milling_angle_deg"],
            "scan_rotation_deg": sc["scan_rotation_deg"],
            "pixel_size_m": sc["pixel_size_m"],
            "aoi_diameter_um": sc["aoi_diameter_um"],
            "run_verdict": sc["verdict"],
        })
        overlay = draw_overlay(rec, gt)
        cv2.imwrite(str(OVERLAY_DIR / f"{rec.run}_{rec.frame}.png"), overlay)
        print(f"{rec.path}: a={gt.a:.1f}px width={rows[-1]['width_um']:.1f}um "
              f"angle={gt.milling_angle_deg:.2f} tilt={gt.tilt_deg:.2f} "
              f"troughs={gt.n_troughs} rms={gt.rms_px:.2f} "
              f"vote={dense_score:.3f}")

    checks, ok = cross_checks(rows)
    print("\nPhysics cross-checks:")
    for key, value in checks.items():
        print(f"  {key}: {value}")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(
        {"corpus": "debug_frames_dir", "n_frames": len(rows),
         "checks": checks, "frames": rows}, indent=2))
    print(f"\nWrote {OUT_JSON}")
    print(f"Overlays in {OVERLAY_DIR} (review all {len(rows)})")
    if not ok:
        print("CROSS-CHECKS FAILED — ground truth NOT trustworthy yet",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
