"""List model for the Position Alignment page's confirmed positions.

Qt layer only — rows are the :class:`PositionRecord` readbacks the
Confirm button captures from the microscope. Values are stored in
AutoScript SI units (radians / meters); conversion to display units
happens in the QML delegates.

Role names are the contract with ``PositionResultsTable.qml``'s
``required property`` delegates — the ``SpinMillPositionsModel``
contract minus ``fileName`` (confirmed rows have no source image).
Unlike the SEM page's load-everything models, this one appends row by
row (``beginInsertRows``, no reset) so the table never snaps its scroll
position as positions accumulate.
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

from asv_spin_mill_angle_calc.microscope_ops import PositionRecord


class ConfirmedPositionsModel(QAbstractListModel):
    """Confirmed spin mill position rows (one per Confirm press)."""

    StageRRole = Qt.UserRole + 1
    StageTRole = Qt.UserRole + 2
    StageXRole = Qt.UserRole + 3
    StageYRole = Qt.UserRole + 4
    BeamXRole = Qt.UserRole + 5
    BeamYRole = Qt.UserRole + 6
    ScanRRole = Qt.UserRole + 7
    WdRole = Qt.UserRole + 8

    countChanged = Signal()

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._records: List[PositionRecord] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._records)):
            return None
        record = self._records[index.row()]
        return {
            self.StageRRole: record.stage_r_rad,
            self.StageTRole: record.stage_t_rad,
            self.StageXRole: record.stage_x_m,
            self.StageYRole: record.stage_y_m,
            self.BeamXRole: record.beam_x_m,
            self.BeamYRole: record.beam_y_m,
            self.ScanRRole: record.scan_r_rad,
            self.WdRole: record.wd_m,
        }.get(role)

    def roleNames(self) -> Dict[int, QByteArray]:
        return {
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

    def records(self) -> List[PositionRecord]:
        """Snapshot of the confirmed rows (for the SEM recompute)."""
        return list(self._records)

    def append_row(self, record: PositionRecord) -> None:
        row = len(self._records)
        self.beginInsertRows(QModelIndex(), row, row)
        self._records.append(record)
        self.endInsertRows()
        self.countChanged.emit()

    def clear(self) -> None:
        if not self._records:
            return
        self.beginResetModel()
        self._records = []
        self.endResetModel()
        self.countChanged.emit()
