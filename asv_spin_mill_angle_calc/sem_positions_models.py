"""List models for the SEM Angle Calc page.

Qt layer only — the row records come from the Qt-free
:mod:`asv_spin_mill_angle_calc.image_metadata` and
:mod:`asv_spin_mill_angle_calc.sem_geometry_calculator` modules. Values
are stored in AutoScript SI units (radians / meters); conversion to
display units (degrees, mm, µm) happens in the QML delegates.

Role names are the contract with the QML tables' ``required property``
delegates — keep them in sync with SpinMillPositionsTable.qml and
SemPositionsTable.qml.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    Qt,
    Signal,
)

from asv_spin_mill_angle_calc.image_metadata import SpinMillImageMetadata
from asv_spin_mill_angle_calc.sem_geometry_calculator import SemPositionCandidate


class SpinMillPositionsModel(QAbstractListModel):
    """Parsed per-image rows for the Spin Mill Positions table."""

    FileNameRole = Qt.UserRole + 1
    StageRRole = Qt.UserRole + 2
    StageTRole = Qt.UserRole + 3
    StageXRole = Qt.UserRole + 4
    StageYRole = Qt.UserRole + 5
    BeamXRole = Qt.UserRole + 6
    BeamYRole = Qt.UserRole + 7
    ScanRRole = Qt.UserRole + 8
    WdRole = Qt.UserRole + 9

    # QAbstractListModel already notifies the view via rowsInserted /
    # modelReset; a QML `count` binding needs its own notify signal.
    countChanged = Signal()

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._records: List[SpinMillImageMetadata] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._records)):
            return None
        record = self._records[index.row()]
        return {
            self.FileNameRole: record.file_name,
            self.StageRRole: record.stage_rotation_rad,
            self.StageTRole: record.stage_tilt_rad,
            self.StageXRole: record.stage_x_m,
            self.StageYRole: record.stage_y_m,
            self.BeamXRole: record.beam_shift_x_m,
            self.BeamYRole: record.beam_shift_y_m,
            self.ScanRRole: record.scan_rotation_rad,
            self.WdRole: record.working_distance_m,
        }.get(role)

    def roleNames(self) -> Dict[int, QByteArray]:
        return {
            self.FileNameRole: QByteArray(b"fileName"),
            self.StageRRole: QByteArray(b"stageR"),
            self.StageTRole: QByteArray(b"stageT"),
            self.StageXRole: QByteArray(b"stageX"),
            self.StageYRole: QByteArray(b"stageY"),
            self.BeamXRole: QByteArray(b"beamX"),
            self.BeamYRole: QByteArray(b"beamY"),
            self.ScanRRole: QByteArray(b"scanR"),
            self.WdRole: QByteArray(b"wd"),
        }

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._records)

    def replace_all(self, records: List[SpinMillImageMetadata]) -> None:
        """Atomic reset — the only mutation path (controller-driven)."""
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()
        self.countChanged.emit()


class SemCandidatePositionsModel(QAbstractListModel):
    """Candidate SEM-perpendicular rows for the SEM positions table."""

    SourceRole = Qt.UserRole + 1
    StageRRole = Qt.UserRole + 2
    StageTRole = Qt.UserRole + 3
    SourceDetailRole = Qt.UserRole + 4

    countChanged = Signal()

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._candidates: List[SemPositionCandidate] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._candidates)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._candidates)):
            return None
        candidate = self._candidates[index.row()]
        return {
            self.SourceRole: candidate.source,
            self.StageRRole: candidate.stage_rotation_rad,
            self.StageTRole: candidate.stage_tilt_rad,
            self.SourceDetailRole: candidate.source_detail,
        }.get(role)

    def roleNames(self) -> Dict[int, QByteArray]:
        return {
            self.SourceRole: QByteArray(b"source"),
            self.StageRRole: QByteArray(b"stageR"),
            self.StageTRole: QByteArray(b"stageT"),
            self.SourceDetailRole: QByteArray(b"sourceDetail"),
        }

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._candidates)

    def replace_all(self, candidates: List[SemPositionCandidate]) -> None:
        """Atomic reset (destroys and recreates the view's delegates)."""
        self.beginResetModel()
        self._candidates = list(candidates)
        self.endResetModel()
        self.countChanged.emit()

    def update_or_replace(self, candidates: List[SemPositionCandidate]) -> None:
        """In-place tilt update when only the target angle moved.

        A target-angle change shifts every candidate's tilt but leaves
        the row structure (count, sources, rotations, details) intact —
        a full reset there would destroy the view's delegates and snap
        its scroll position to the top on every 0.1-degree spin-box
        tick. Anything structural (a load, a primary/alternate swap at
        the |tilt| tie point, clearing) falls back to the reset.
        """
        same_structure = (
            len(candidates) == len(self._candidates)
            and all(new.source == old.source
                    and new.stage_rotation_rad == old.stage_rotation_rad
                    and new.source_detail == old.source_detail
                    for new, old in zip(candidates, self._candidates))
        )
        if not same_structure:
            self.replace_all(candidates)
            return
        self._candidates = list(candidates)
        if self._candidates:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._candidates) - 1, 0),
                [self.StageTRole],
            )
