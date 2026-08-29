"""List model for the Position Alignment page's spin mill position slots.

Qt layer only — filled slots pair the :class:`PositionRecord` readback
the Confirm button captures from the microscope with its measured
milling angle. Values are stored in AutoScript SI units (radians /
meters); conversion to display units happens in the QML delegates. Role
names are the contract with ``PositionResultsTable.qml``'s delegates.

The model is a fixed set of slots, mirroring ASV's *Define Spin Mill
Position* activity: the operator declares the Number of Spin Mill
Positions (N) up front, and positions 1..N have fixed identities. Three
deliberate properties follow:

* A slot's position number is its 1-based index and never changes,
  because slots never shift — there is no delete. Filling, re-filling
  (Re-confirm), and clearing all leave every slot in place, so our
  numbering can never slide against ASV's and send the operator to the
  wrong physical site.

* Lowering N deactivates rather than deletes: the slot list keeps
  ``max(N, 1 + highest filled index)`` entries, so filled slots beyond
  N survive as inactive overhang and come back when N is raised — only
  an all-pending tail is ever trimmed. Active-state is deliberately not
  a role: the table renders it from its ``activeCount`` property (a
  root-property change re-evaluates every delegate without any
  ``dataChanged`` discipline here), and Python consumers derive it at
  call time through the ``active_*`` snapshots.

* ``milling_angle_deg`` is the ellipse-measured angle (``asin(b/a)``)
  that armed the Confirm, or ``None`` (rendered as "NA") when no
  ellipse was measured — never faked from the stage tilt, because a
  tilt-derived angle is the open-loop model, not a measurement.

``fill_slot`` is an in-place ``dataChanged`` (no insert or remove), so
recording never destroys the view's delegates or snaps its scroll
position; ``set_slot_count`` inserts or trims only at the tail.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    Qt,
    Signal,
)

from asv_spin_mill_angle_calc.microscope_ops import PositionRecord

# Matches ASV's usual rosette; the page's spin box (3-10) is the range
# guard, following the aoiDiameter idiom of validating in QML only.
DEFAULT_SLOT_COUNT = 5


@dataclass(frozen=True)
class ConfirmedPosition:
    """One filled slot: the readback plus its measured angle.

    Deliberately identity-free. A slot's position number is its index in
    the model's slot list, and slots never move, so there is no copy of
    the number here to fall out of step. ``PositionRecord`` stays a pure
    AutoScript readback DTO; this wrapper carries the one thing the
    table needs that the instrument does not report.
    """

    record: PositionRecord
    milling_angle_deg: Optional[float] = None


class ConfirmedPositionsModel(QAbstractListModel):
    """Fixed spin mill position slots, pending until recorded.

    Rows exist for every slot ``1..max(N, highest filled slot)``; a
    pending slot serves ``None`` for the value roles and ``False`` for
    ``filled``. See the module docstring for the slot invariants.
    """

    StageRRole = Qt.UserRole + 1
    StageTRole = Qt.UserRole + 2
    StageXRole = Qt.UserRole + 3
    StageYRole = Qt.UserRole + 4
    BeamXRole = Qt.UserRole + 5
    BeamYRole = Qt.UserRole + 6
    ScanRRole = Qt.UserRole + 7
    WdRole = Qt.UserRole + 8
    AngleRole = Qt.UserRole + 9
    FilledRole = Qt.UserRole + 10

    countChanged = Signal()

    def __init__(self, parent: Optional[Any] = None,
                 slot_count: int = DEFAULT_SLOT_COUNT) -> None:
        super().__init__(parent)
        self._slot_count = slot_count
        self._slots: List[Optional[ConfirmedPosition]] = [None] * slot_count

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._slots)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._slots)):
            return None
        slot = self._slots[index.row()]
        if slot is None:
            # Pending: the delegate renders dashes off `filled` and never
            # reads the value roles, but a None keeps any stray read safe.
            return False if role == self.FilledRole else None
        record = slot.record
        # No position-number role: the delegate reads `index + 1`
        # directly, and with fixed slots that ordinal is a stable
        # identity — no mutation ever shifts a row.
        return {
            self.StageRRole: record.stage_r_rad,
            self.StageTRole: record.stage_t_rad,
            self.StageXRole: record.stage_x_m,
            self.StageYRole: record.stage_y_m,
            self.BeamXRole: record.beam_x_m,
            self.BeamYRole: record.beam_y_m,
            self.ScanRRole: record.scan_r_rad,
            self.WdRole: record.wd_m,
            self.AngleRole: slot.milling_angle_deg,
            self.FilledRole: True,
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
            self.AngleRole: QByteArray(b"millingAngleDeg"),
            self.FilledRole: QByteArray(b"filled"),
        }

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._slots)

    # --- Snapshots --------------------------------------------------------

    def slot_count(self) -> int:
        """The active slot count N (rows beyond it are inactive overhang)."""
        return self._slot_count

    def filled_count(self) -> int:
        """How many slots hold a recorded position, active or not."""
        return sum(1 for slot in self._slots if slot is not None)

    def is_filled(self, slot_number: int) -> bool:
        """Whether a slot holds a recorded position (False out of range)."""
        index = self.index_of_position(slot_number)
        return index >= 0 and self._slots[index] is not None

    def first_pending_active_slot(self) -> Optional[int]:
        """The lowest pending slot number within 1..N, or None when full.

        This is where the Confirm button's capture lands; None is what
        turns Confirm off while Re-confirm stays available.
        """
        for i, slot in enumerate(self._slots[:self._slot_count]):
            if slot is None:
                return i + 1
        return None

    def active_records(self) -> List[Tuple[int, PositionRecord]]:
        """(slot number, readback) for every filled active slot, ascending.

        The single paired snapshot for the SEM recompute: numbers and
        records come from one walk, so the SEM provenance labels can
        never drift against the SEM inputs under sparse fills (slot 4
        filled while 2-3 are pending must be labeled "Position 4").
        """
        return [(i + 1, slot.record)
                for i, slot in enumerate(self._slots[:self._slot_count])
                if slot is not None]

    def active_measured_angles(self) -> List[float]:
        """Measured angles of filled active slots, skipping unmeasured ones.

        Inactive overhang is excluded on purpose: a slot beyond N is out
        of the SEM calculation and the header average alike.
        """
        return [slot.milling_angle_deg
                for slot in self._slots[:self._slot_count]
                if slot is not None and slot.milling_angle_deg is not None]

    def index_of_position(self, position_number: int) -> int:
        """Slot index for a position number, or -1 when out of range.

        The single definition of "number -> slot". Bounds are the full
        slot list (overhang included) — activeness is a policy question
        the controller answers, not a bounds question.
        """
        index = position_number - 1
        return index if 0 <= index < len(self._slots) else -1

    def record_for_position(
            self, position_number: int) -> Optional[PositionRecord]:
        """The readback for a slot, or None when pending or out of range."""
        index = self.index_of_position(position_number)
        if index < 0 or self._slots[index] is None:
            return None
        return self._slots[index].record

    # --- Mutation ---------------------------------------------------------

    def set_slot_count(self, count: int) -> None:
        """Change N, preserving every recorded position.

        Growing appends pending rows. Shrinking trims only the
        all-pending tail down to ``max(count, 1 + highest filled
        index)`` — filled slots beyond the new N stay as inactive
        overhang rows, so lowering N is never destructive and raising
        it back restores them. Deliberately no ``dataChanged``: no
        row's data changes, and active-state is rendered from the
        table's ``activeCount`` property, not a role.
        """
        if count == self._slot_count:
            return
        if count > self._slot_count:
            self._slot_count = count
            if count > len(self._slots):
                first = len(self._slots)
                self.beginInsertRows(QModelIndex(), first, count - 1)
                self._slots.extend([None] * (count - first))
                self.endInsertRows()
                self.countChanged.emit()
            return
        self._slot_count = count
        new_length = max(count, self._highest_filled_index() + 1)
        if new_length < len(self._slots):
            # The trimmed tail is all-pending by construction: every
            # index >= new_length is above the highest filled index.
            self.beginRemoveRows(QModelIndex(), new_length,
                                 len(self._slots) - 1)
            del self._slots[new_length:]
            self.endRemoveRows()
            self.countChanged.emit()

    def fill_slot(self, slot_number: int, record: PositionRecord,
                  milling_angle_deg: Optional[float] = None) -> bool:
        """Record a position into one slot, pending or already filled.

        In-place (``dataChanged``, no insert) so recording never
        destroys the view's delegates or snaps its scroll position, and
        the slot's position number is untouched by construction.
        Mechanism only — whether the slot is active is the controller's
        policy check. Returns False when the slot number is out of
        range.
        """
        index = self.index_of_position(slot_number)
        if index < 0:
            return False
        self._slots[index] = ConfirmedPosition(
            record=record,
            milling_angle_deg=milling_angle_deg,
        )
        model_index = self.index(index, 0)
        self.dataChanged.emit(model_index, model_index, [
            self.StageRRole, self.StageTRole, self.StageXRole,
            self.StageYRole, self.BeamXRole, self.BeamYRole,
            self.ScanRRole, self.WdRole, self.AngleRole,
            self.FilledRole,
        ])
        return True

    def clear(self) -> None:
        """Reset every slot to pending, keeping N.

        Overhang rows disappear (the list returns to exactly N pending
        slots). No-op when nothing is filled — an all-pending model
        cannot have overhang, so there is nothing to reset.
        """
        if self.filled_count() == 0:
            return
        self.beginResetModel()
        self._slots = [None] * self._slot_count
        self.endResetModel()
        self.countChanged.emit()

    def _highest_filled_index(self) -> int:
        """Index of the highest filled slot, or -1 when none is filled."""
        return max((i for i, slot in enumerate(self._slots)
                    if slot is not None), default=-1)
