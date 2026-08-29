"""Format SEM geometry calculation results for display and logging.

The formatter takes a populated ``SEMGeometryResult`` and produces two
strings: a short status line suitable for the page's status label, and a
multi-line log block suitable for the application logger. Both are pure
functions of the result — no Qt dependencies, no side effects, no further
computation. This keeps formatting decisions out of the calculator (which
only does math) and out of the controller (which only routes signals).
"""
from __future__ import annotations

import math

from asv_spin_mill_angle_calc.sem_geometry_calculator import (
    SEMGeometryResult,
    SEMGeometryStatus,
)


def status_line(result: SEMGeometryResult) -> str:
    """Return a short, single-line message for the page's status label."""
    return result.status_message


def log_block(result: SEMGeometryResult) -> str:
    """Return a multi-line log entry summarizing the calculation.

    A header plus indented sections keeps successive entries distinct
    and fields easy to grep for; the raw input triples are included so
    a calculation can be reproduced from the log alone, without the
    original images.
    """
    lines: list = ["SEM geometry calculation"]
    lines.append(f"  Status: {result.status.value}")
    lines.append(f"  Status message: {result.status_message}")

    n = result.inputs.num_points
    lines.append(f"  Input positions: {n}")
    lines.append(
        f"  Target milling angle: "
        f"{result.inputs.target_milling_angle_deg:.2f}°"
    )

    lines.extend(_format_input_table(result))

    if result.scan_rotation_fit is not None:
        lines.extend(_format_fit("Scan rotation fit", result.scan_rotation_fit))

    if result.stage_tilt_fit is not None:
        lines.extend(_format_fit("Stage tilt fit", result.stage_tilt_fit))

    # Selected (primary) candidate, if any.
    if result.target_stage_rotation_rad is not None:
        lines.append("  Selected candidate:")
        lines.append(
            f"    Stage rotation: "
            f"{result.target_stage_rotation_deg:.2f}°"
        )
        lines.append(
            f"    Stage tilt: "
            f"{result.target_stage_tilt_deg:.2f}°"
        )
    elif result.status == SEMGeometryStatus.AMBIGUOUS:
        lines.append("  Selected candidate: none (result ambiguous)")

    # Alternate candidate, if computed (may be present even when the
    # primary was suppressed by the ambiguous-fit path).
    if result.alternate_stage_rotation_rad is not None:
        lines.append("  Alternate candidate:")
        lines.append(
            f"    Stage rotation: "
            f"{result.alternate_stage_rotation_deg:.2f}°"
        )
        lines.append(
            f"    Stage tilt: "
            f"{result.alternate_stage_tilt_deg:.2f}°"
        )

    if result.warnings:
        lines.append("  Warnings:")
        for warning in result.warnings:
            lines.append(f"    - {warning}")

    return "\n".join(lines)


def _format_input_table(result: SEMGeometryResult) -> list:
    lines: list = ["  Raw input data:"]
    lines.append(
        "    idx  stage_rot(deg)  stage_tilt(deg)  scan_rot(deg)"
        "  scan_rot_folded(deg)"
    )
    quads = zip(
        result.inputs.stage_rotations_rad,
        result.inputs.stage_tilts_rad,
        result.inputs.scan_rotations_rad,
        result.inputs.folded_scan_rotations_rad,
    )
    for index, (rotation_rad, tilt_rad, scan_rad, folded_rad) in \
            enumerate(quads):
        lines.append(
            f"    {index:3d}  "
            f"{math.degrees(rotation_rad):14.4f}  "
            f"{math.degrees(tilt_rad):15.4f}  "
            f"{math.degrees(scan_rad):13.4f}  "
            f"{math.degrees(folded_rad):20.4f}"
        )
    # The sinusoid is fitted on the folded column (ellipse orientation is
    # pi-periodic); note the branch when it is materially off 0.
    center_deg = math.degrees(
        result.inputs.scan_rotation_branch_center_rad)
    if abs(center_deg) > 1.0:
        lines.append(
            f"  Scan rotation branch: folded to the 0/180 reference "
            f"(branch center {center_deg:.2f}°)"
        )
    return lines


def _format_fit(label: str, fit) -> list:
    return [
        f"  {label}:",
        f"    Model: A * sin(stage_rot - phi0) + C",
        f"    Amplitude (A): {math.degrees(fit.amplitude_rad):.4f}°",
        f"    Phase (phi0):  {math.degrees(fit.phase_rad):.4f}°",
        f"    Offset (C):    {math.degrees(fit.offset_rad):.4f}°",
        f"    R-squared:     {fit.r_squared:.4f}",
    ]
