"""TFS spin-mill PNG metadata parsing — Qt-free, stateless.

Thermo Fisher xT saves an XML ``<Metadata>`` block inside the PNG byte
stream. The block is located by byte slicing (no PNG chunk walking needed)
and decoded latin-1: the XML declares utf-8 but contains a raw 0xB5 (µ)
byte after ``IonBeamTiltAngle``; latin-1 never fails and every tag and
number we read is pure ASCII. Slicing from ``<Metadata`` (past the XML
declaration) also keeps ``ElementTree`` happy with a decoded str.

Deliberately stateless module functions (no results accumulate across
loads) and deliberately Qt-free so :mod:`sem_geometry_calculator` can
import it alongside :mod:`spin_mill_geometry`.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

logger = logging.getLogger(__name__)

_METADATA_OPEN = b"<Metadata"
_METADATA_CLOSE = b"</Metadata>"


class ImageMetadataError(ValueError):
    """A single image's embedded metadata could not be parsed."""


@dataclass(frozen=True)
class SpinMillImageMetadata:
    """Metadata for one spin-mill position image. SI units (rad / m)."""

    file_name: str
    file_path: str
    stage_rotation_rad: float        # .//StagePosition/Rotation
    stage_tilt_rad: float            # .//StagePosition/Tilt/Alpha (stage T)
    stage_x_m: float                 # .//StagePosition/X
    stage_y_m: float                 # .//StagePosition/Y
    stage_z_m: float                 # .//StagePosition/Z (kept for automation)
    scan_rotation_rad: float         # .//ScanSettings/ScanRotation
    working_distance_m: float        # .//Optics/WorkingDistance
    beam_shift_x_m: float            # .//BeamShift/X
    beam_shift_y_m: float            # .//BeamShift/Y
    scan_field_of_view_x_m: float    # .//Optics/ScanFieldOfView/X (px scale)


def parse_spin_mill_image(path: str | Path) -> SpinMillImageMetadata:
    """Parse one image. Raises :class:`ImageMetadataError` with a reason."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ImageMetadataError(f"could not read file: {exc}") from exc

    start = data.find(_METADATA_OPEN)
    if start < 0:
        raise ImageMetadataError(
            "no embedded <Metadata> XML block (not a TFS xT image?)")
    end = data.find(_METADATA_CLOSE, start)
    if end < 0:
        raise ImageMetadataError("embedded <Metadata> block is truncated")

    xml_text = data[start:end + len(_METADATA_CLOSE)].decode("latin-1")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ImageMetadataError(f"metadata XML failed to parse: {exc}") from exc

    def field(element_path: str) -> float:
        element = root.find(element_path)
        if element is None or element.text is None:
            raise ImageMetadataError(f"missing metadata element {element_path}")
        try:
            return float(element.text)
        except ValueError as exc:
            raise ImageMetadataError(
                f"non-numeric value {element.text!r} at {element_path}") from exc

    return SpinMillImageMetadata(
        file_name=path.name,
        file_path=str(path),
        stage_rotation_rad=field(".//StagePosition/Rotation"),
        stage_tilt_rad=field(".//StagePosition/Tilt/Alpha"),
        stage_x_m=field(".//StagePosition/X"),
        stage_y_m=field(".//StagePosition/Y"),
        stage_z_m=field(".//StagePosition/Z"),
        scan_rotation_rad=field(".//ScanSettings/ScanRotation"),
        working_distance_m=field(".//Optics/WorkingDistance"),
        beam_shift_x_m=field(".//BeamShift/X"),
        beam_shift_y_m=field(".//BeamShift/Y"),
        scan_field_of_view_x_m=field(".//Optics/ScanFieldOfView/X"),
    )


def _natural_sort_key(path: str | Path) -> tuple:
    """Case-insensitive natural key on the file name (Position2 < Position10).

    Gated on isdecimal(), not isdigit(): isdigit() also accepts characters
    int() rejects (e.g. superscript digits), which re.split's ``\\d`` never
    isolates — a file name like ``area²2.png`` would raise ValueError and
    abort the whole batch. isdecimal() matches exactly what int() parses.
    """
    name = Path(path).name.lower()
    return tuple(int(part) if part.isdecimal() else part
                 for part in re.split(r"(\d+)", name))


def parse_spin_mill_images(
    paths: Iterable[str | Path],
) -> Tuple[List[SpinMillImageMetadata], List[str]]:
    """Batch parse, natural-sorted by file name.

    Continues past bad files rather than aborting the whole batch on the
    first failure. Returns ``(records, errors)`` where each error string
    is ``"name: reason"``. Duplicate file names from different
    directories are all kept, in sorted order.
    """
    records: List[SpinMillImageMetadata] = []
    errors: List[str] = []
    for p in sorted(paths, key=_natural_sort_key):
        try:
            records.append(parse_spin_mill_image(p))
        except ImageMetadataError as exc:
            errors.append(f"{Path(p).name}: {exc}")
            logger.warning("Image metadata parse failed for %s: %s", p, exc)
    return records, errors
