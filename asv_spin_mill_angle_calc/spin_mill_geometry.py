"""Spin-mill FIB geometry — the milling-angle math, shared and Qt-free.

This module is deliberately dependency-free (only the standard-library
``math``) so it can be imported by *both* consumers of the same geometry:

* the FIB Angle Calculator page's controller (manual calculation), and
* the semi-automated Position Alignment page, whose ellipse finder and
  AutoScript stage-tilt loop run in Python and need the identical,
  unit-tested functions.

Derivation (confirmed with the domain expert)
---------------------------------------------
On the Hydra Bio dual-beam the FIB column sits ``FIB_ANGLE_FROM_SEM_DEG``
(52 deg) off the SEM/vertical axis, i.e. ``FIB_ANGLE_FROM_STAGE_PLANE_DEG``
(38 deg) above the untilted stage plane. A circular AOI is milled into the
sample surface with the stage tilted so the surface faces the FIB (stage
+52 deg). Imaged at the milling orientation the circle foreshortens to an
ellipse whose *minor axis* ``h`` (height) relates to the FIB-to-surface
grazing angle ``beta`` by simple projection::

    h = D * sin(beta)   ->   beta = asin(h / D)

The milling angle *is* that grazing angle ``beta`` (e.g. stage -34 deg gives
a 4 deg milling angle, matching ``beta = stage_tilt + 38``). The 52 deg beam
tilt is already embodied in the physical stage tilt, so it does **not** enter
the scalar result -- ``asin(h / D)`` is complete.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# --- Instrument geometry (single source of truth) -------------------------
# Angle between the FIB and SEM beam axes, confirmed by the image-metadata
# field <IonBeamTiltAngle> (~52.0 deg) on the Hydra Bio UX.
FIB_ANGLE_FROM_SEM_DEG: float = 52.0
# Complement: the FIB's angle above the untilted stage plane. This is the
# milling angle when the stage tilt is zero (beta = stage_tilt + 38).
FIB_ANGLE_FROM_STAGE_PLANE_DEG: float = 90.0 - FIB_ANGLE_FROM_SEM_DEG  # 38.0


@dataclass(frozen=True)
class MillingResult:
    """Result of :func:`compute` for one set of inputs."""

    calculated_milling_angle_deg: float
    tilt_stage_by_deg: float
    # False for degenerate geometry (height >= diameter, i.e. ratio >= 1).
    # The UI clamps the height max to the diameter so this is normally True;
    # it lets a caller (e.g. the automation) notice a bad measurement.
    valid: bool


def calculated_milling_angle_deg(diameter_um: float, ellipse_height_um: float) -> float:
    """Milling (FIB-to-surface grazing) angle from the measured ellipse.

    ``beta = degrees(asin(height / diameter))``. The ratio is clamped to the
    asin domain ``[-1, 1]`` so a degenerate ``height >= diameter`` saturates
    to 90 deg rather than raising (see :func:`compute`'s ``valid`` flag).
    """
    ratio = max(-1.0, min(1.0, ellipse_height_um / diameter_um))
    return math.degrees(math.asin(ratio))


def tilt_stage_by_deg(target_deg: float, calculated_deg: float) -> float:
    """How far to tilt the stage to reach ``target`` from the measured angle.

    Signed; matches the stage's tilt direction (positive tilt rotates the
    surface normal toward the FIB, increasing the grazing angle).
    """
    return target_deg - calculated_deg


def compute(target_deg: float, diameter_um: float, ellipse_height_um: float) -> MillingResult:
    """Full FIB calculation for the two displayed results."""
    calculated = calculated_milling_angle_deg(diameter_um, ellipse_height_um)
    tilt = tilt_stage_by_deg(target_deg, calculated)
    valid = 0.0 < ellipse_height_um < diameter_um
    return MillingResult(calculated, tilt, valid)


def stage_tilt_for_milling_angle_deg(target_deg: float) -> float:
    """Absolute stage tilt that yields a given milling angle (inverse model).

    From ``beta = stage_tilt + 38``: ``stage_tilt = target - 38``. Lets the
    Position Alignment automation move straight to the tilt for a target
    (e.g. 4 deg -> -34 deg) instead of iterating.
    """
    return target_deg - FIB_ANGLE_FROM_STAGE_PLANE_DEG


def ellipse_height_for_angle_um(diameter_um: float, angle_deg: float) -> float:
    """Forward model: ellipse height for a given milling angle.

    ``h = D * sin(angle)``. Useful for validating the ellipse finder against
    an expected angle. Exact inverse of :func:`calculated_milling_angle_deg`.
    """
    return diameter_um * math.sin(math.radians(angle_deg))


def fold_scan_rotation_deg(deg: float) -> float:
    """FIB scan rotation folded into (-90, 90] deg.

    The milled ellipse's image orientation is a line orientation — it is
    pi-periodic, so a 180 deg raster rotation maps the ellipse onto
    itself. An instrument whose session baseline scan rotation is 180 deg
    (as on the Hydra Bio UX) is therefore at the same physical
    orientation as 0 deg, and every consumer of scan rotation as an
    *orientation* (the SEM geometry sinusoid, the detector's tilt prior)
    must fold before using it.
    The -90 edge canonicalizes to +90 so the interval stays half-open.
    """
    folded = (deg + 90.0) % 180.0 - 90.0
    if folded == -90.0:
        folded = 90.0
    return folded


def fold_scan_rotation_rad(rad: float) -> float:
    """Radian twin of :func:`fold_scan_rotation_deg`: (-pi/2, pi/2]."""
    half_pi = math.pi / 2.0
    folded = (rad + half_pi) % math.pi - half_pi
    if folded == -half_pi:
        folded = half_pi
    return folded
