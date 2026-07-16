"""QObject controller for the microscope connection lifecycle.

Drives the Position Alignment page's Connect To Microscope switch and the
StatusBar's right-corner indicator. Thin Qt orchestration over the Qt-free
:mod:`asv_spin_mill_angle_calc.microscope_client`; the same idioms as the
sibling controllers (functional ``Signal`` class attribute, single ``changed``
notify, ``camelCase`` QML surface, ``_snake_case`` backing fields).

Threading (the repo's first — mirrors Hydra's connect worker):
``SdbMicroscopeClient.connect()`` blocks 1-3 s on a fast failure and up to
~30 s on a slow timeout, so each connection attempt runs in a single-shot
``_ConnectWorker`` on its own ``QThread``; results marshal back to the GUI
thread through a queued signal. ``disconnect()`` is fast and stays synchronous.

State machine: disconnected -> connecting -> connected | error;
connected -> disconnected (user toggle-off); error -> connecting (re-toggle
retries). Error is a real, terminal-until-retry state — unlike Hydra there is
no silent simulation fallback, because a user-driven switch must not quietly
become something other than what the user asked for.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot

from asv_spin_mill_angle_calc.microscope_client import (
    MICROSCOPE_HOST,
    MicroscopeClient,
    create_client,
)
from asv_spin_mill_angle_calc.microscope_ops import MicroscopeOps

logger = logging.getLogger(__name__)

# --- States (module-private string constants) ------------------------------
_STATE_DISCONNECTED = "disconnected"
_STATE_CONNECTING = "connecting"
_STATE_CONNECTED = "connected"
_STATE_ERROR = "error"

# Display strings, both composed here (repo convention — the SEM controller's
# statusText precedent): the card label is a sentence, the StatusBar's
# right-corner indicator is terse.
_CARD_TEXT = {
    _STATE_DISCONNECTED: "Disconnected from microscope",
    _STATE_CONNECTING: "Connecting to microscope...",
    _STATE_CONNECTED: "Connected to microscope",
    _STATE_ERROR: "Connection error (see console log)",
}
_INDICATOR_TEXT = {
    _STATE_DISCONNECTED: "Disconnected",
    _STATE_CONNECTING: "Connecting...",
    _STATE_CONNECTED: "Connected",
    _STATE_ERROR: "Connection error",
}


class _ConnectWorker(QObject):
    """Single-shot worker for one connection attempt. Do not reuse.

    All exceptions are caught here and logged — the ERROR-level tracebacks
    below are the "(see console log)" target the UI points at. ``finished``
    carries the connected client, or None on any failure (exceptions must not
    cross the thread boundary).
    """

    finished = Signal(object)  # MicroscopeClient | None

    def __init__(self, client_factory: Callable[[], MicroscopeClient],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client_factory = client_factory
        # Stashed immediately BEFORE finished is emitted on success; read by
        # MicroscopeController.shutdown() to recover a client produced by a
        # connect that completed inside the shutdown race window (plain
        # Python attribute — safe to read even after deleteLater).
        self.client: MicroscopeClient | None = None

    @Slot()
    def run(self) -> None:
        try:
            client = self._client_factory()
        except Exception:
            logger.error(
                "Could not create the microscope client; is AutoScript "
                "installed on this machine?", exc_info=True)
            self.finished.emit(None)
            return
        try:
            client.connect()
        except Exception:
            logger.error("Could not connect to microscope", exc_info=True)
            self.finished.emit(None)
            return
        self.client = client
        self.finished.emit(client)


class MicroscopeController(QObject):
    """Microscope connection lifecycle for the Position Alignment page."""

    # Single notify signal (repo idiom): every property derives from _state.
    changed = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        client_factory: Callable[[], MicroscopeClient] = create_client,
        start_worker: Callable[[_ConnectWorker], None] | None = None,
    ) -> None:
        """``client_factory`` and ``start_worker`` are test seams.

        ``start_worker`` replaces the production QThread launch: tests pass
        ``lambda w: w.run()`` for synchronous, same-thread delivery (no event
        loop needed), or capture the worker to hold the controller in the
        connecting state and drive completion later.
        """
        super().__init__(parent)
        self._client_factory = client_factory
        self._start_worker = start_worker
        self._state: str = _STATE_DISCONNECTED
        self._client: Optional[MicroscopeClient] = None
        self._connect_thread: Optional[QThread] = None
        self._connect_worker: Optional[_ConnectWorker] = None
        self._shutting_down: bool = False
        self._busy_guard: Optional[Callable[[], bool]] = None

    def set_busy_guard(self, guard: Callable[[], bool]) -> None:
        """Refuse user disconnects while the guard reports the client is
        in use (the Position Alignment worker). The QML switch is also
        disabled during a run — this is the defensive backstop against
        stranding the stage mid-automation."""
        self._busy_guard = guard

    # --- Outputs (bound by QML) -------------------------------------------
    @Property(bool, notify=changed)
    def isConnected(self) -> bool:
        return self._state == _STATE_CONNECTED

    @Property(bool, notify=changed)
    def isConnecting(self) -> bool:
        return self._state == _STATE_CONNECTING

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """Card label text (the verbose, sentence form)."""
        if self._state == _STATE_CONNECTED and self._is_simulated():
            return _CARD_TEXT[_STATE_CONNECTED] + " (simulated)"
        return _CARD_TEXT[self._state]

    @Property(str, notify=changed)
    def connectionStatus(self) -> str:
        """StatusBar right-corner indicator text (the terse form)."""
        if self._state == _STATE_CONNECTED and self._is_simulated():
            return _INDICATOR_TEXT[_STATE_CONNECTED] + " (sim)"
        return _INDICATOR_TEXT[self._state]

    def _is_simulated(self) -> bool:
        """A simulated session must never masquerade as hardware."""
        return bool(getattr(self._client, "is_simulated", False))

    # --- Ops access for the Position Alignment backend ----------------------
    def current_ops(self) -> Optional[MicroscopeOps]:
        """Hardware ops bundle while connected; None otherwise.

        GUI-thread accessor: the alignment controller fetches a fresh
        bundle at each Start, so a reconnect invalidates nothing.
        """
        if self._state == _STATE_CONNECTED and self._client is not None:
            return self._client.ops()
        return None

    # --- Actions (invoked from QML) ---------------------------------------
    # Named connectMicroscope/disconnectMicroscope — NOT connect/disconnect,
    # which would shadow QObject.connect/QObject.disconnect.

    @Slot()
    def connectMicroscope(self) -> None:
        """Start a threaded connection attempt (switch toggled on)."""
        if self._state in (_STATE_CONNECTING, _STATE_CONNECTED):
            logger.warning("Connect requested while %s; ignoring", self._state)
            return
        logger.info("Connecting to microscope (host=%s)...",
                    MICROSCOPE_HOST or "<AutoScript default>")
        self._set_state(_STATE_CONNECTING)

        worker = _ConnectWorker(self._client_factory)
        worker.finished.connect(self._on_connect_finished)
        self._connect_worker = worker

        if self._start_worker is not None:  # test seam: run synchronously
            self._start_worker(worker)
            return

        # Canonical single-shot worker-thread wiring (Hydra pattern).
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Identity-guarded ref cleanup (deliberate divergence from Hydra,
        # which connects only once): this controller reconnects repeatedly,
        # and an old thread's late `finished` must not null a NEW attempt's
        # refs — that would break shutdown()'s quit-race recovery.
        def _clear_refs(t: QThread = thread) -> None:
            if self._connect_thread is t:
                self._connect_thread = None
                self._connect_worker = None
        thread.finished.connect(_clear_refs)

        self._connect_thread = thread
        thread.start()

    @Slot()
    def disconnectMicroscope(self) -> None:
        """Disconnect (switch toggled off). Synchronous — disconnect is fast."""
        if self._state == _STATE_CONNECTING:
            logger.warning("Disconnect requested during a connect attempt; "
                           "ignoring (a blocking connect cannot be cancelled)")
            return
        if self._busy_guard is not None and self._busy_guard():
            logger.warning("Disconnect requested while the microscope is "
                           "in use by the alignment automation; ignoring")
            return
        if self._state != _STATE_CONNECTED or self._client is None:
            logger.debug("Disconnect requested but not connected; ignoring")
            return
        try:
            self._client.disconnect()  # wrapper guards + logs internally
        finally:
            self._client = None
            self._set_state(_STATE_DISCONNECTED)

    # --- Worker result (GUI thread via queued connection) ------------------
    @Slot(object)
    def _on_connect_finished(self, client: Optional[MicroscopeClient]) -> None:
        if self._shutting_down:
            # Quit-race tail: the app is tearing down; don't resurrect UI
            # state. Disconnect is idempotent — safe even if shutdown()
            # already disconnected this client via worker.client.
            if client is not None:
                client.disconnect()
            return
        if client is not None:
            self._client = client
            self._set_state(_STATE_CONNECTED)
        else:
            self._set_state(_STATE_ERROR)

    # --- App-quit teardown --------------------------------------------------
    @Slot()
    def shutdown(self) -> None:
        """Disconnect cleanly at app quit. Wired to app.aboutToQuit."""
        self._shutting_down = True
        if self._connect_thread is not None and self._connect_thread.isRunning():
            logger.info("Connect thread still running at shutdown; "
                        "waiting briefly...")
            if not self._connect_thread.wait(1000):
                logger.warning("Connect thread did not finish in time; "
                               "process exit will terminate it")
        # QThread.wait() does not spin the event loop, so a connect that
        # completed during the wait never ran the queued _on_connect_finished
        # and self._client is still None — recover the client off the worker.
        if self._client is None and self._connect_worker is not None:
            pending = getattr(self._connect_worker, "client", None)
            if pending is not None:
                logger.info(
                    "Shutdown: disconnecting client from an in-flight connect")
                try:
                    pending.disconnect()
                except Exception:
                    logger.exception(
                        "Error disconnecting in-flight client (non-fatal)")
        if self._client is not None and self._client.is_connected:
            logger.info("Shutting down — disconnecting microscope")
            try:
                self._client.disconnect()
            except Exception:
                logger.exception("Error during shutdown disconnect (non-fatal)")

    # --- Shared state transition ---------------------------------------------
    def _set_state(self, state: str) -> None:
        if self._state == state:
            return
        logger.info("Microscope connection state: %s -> %s", self._state, state)
        self._state = state
        self.changed.emit()
