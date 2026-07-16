"""Qt-free wrapper around AutoScript's SdbMicroscopeClient.

Owns the raw SDK object and the connect/disconnect lifecycle — including the
connected flag AutoScript lacks (the SDK exposes only ``server_host``, and its
``disconnect()`` raises if the client is not connected, so callers need a
guarded, idempotent surface). Mirrors the sibling Hydra project's
``microscope/client.py``; the ``ops()`` accessor hands the Position Alignment
backend its hardware seam (:mod:`asv_spin_mill_angle_calc.microscope_ops`).

``autoscript_sdb_microscope_client`` is imported lazily in ``__init__`` so this
module (and the whole app) still loads on dev machines without AutoScript —
the import error surfaces only when a connection is actually attempted, where
the controller reports it as a connection error.

``create_client`` is the connect-time simulation switch: setting the
``ASV_SIMULATED_MICROSCOPE=1`` environment variable makes it return a
:class:`SimulatedMicroscopeClient` instead. The switch is explicit and
env-scoped on purpose — never a silent fallback when AutoScript is missing —
and a simulated session is visibly badged "(sim)" in the UI.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from asv_spin_mill_angle_calc.microscope_ops import (
    MicroscopeOps,
    build_autoscript_ops,
)

logger = logging.getLogger(__name__)

# Host passed to SdbMicroscopeClient.connect(). None -> parameterless
# connect(), which uses AutoScript's default (192.168.0.1, the support-PC to
# microscope-PC link — matches the Hydra deployment). Set to e.g. "localhost"
# when running directly on the microscope PC (Local scripting configuration).
MICROSCOPE_HOST: str | None = None

# Environment switch for the simulated microscope ("1" enables), plus an
# optional directory of capture PNGs to replay instead of the physics
# renderer (open-loop; detector realism only).
ASV_SIM_ENV = "ASV_SIMULATED_MICROSCOPE"
ASV_SIM_FRAMES_ENV = "ASV_SIM_FRAMES_DIR"


class MicroscopeClient:
    """Narrow app-facing wrapper over one AutoScript client instance."""

    is_simulated: bool = False

    def __init__(self) -> None:
        # Lazy import — see module docstring.
        from autoscript_sdb_microscope_client import SdbMicroscopeClient
        self._sdb: Any = SdbMicroscopeClient()
        self._connected: bool = False
        self._host: str = ""

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def server_host(self) -> str:
        return self._host

    def connect(self) -> None:
        """Connect to the AutoScript server.

        Deliberately does NOT catch — exceptions propagate to the caller
        (the controller's connect worker), which is the single logging
        point for connection failures.
        """
        if self._connected:
            logger.warning("Already connected; ignoring connect() call")
            return
        if MICROSCOPE_HOST is None:
            self._sdb.connect()
        else:
            self._sdb.connect(MICROSCOPE_HOST)
        self._host = getattr(self._sdb, "server_host", "") or "<unknown>"
        self._connected = True
        logger.info("Connected to microscope at %s", self._host)

    def disconnect(self) -> None:
        """Disconnect; safe to call in any state (idempotent).

        AutoScript's disconnect() raises when the client is not connected,
        so the _connected guard is load-bearing — it also makes the
        shutdown-race double-disconnect (controller.shutdown) harmless.
        """
        if not self._connected:
            return
        try:
            self._sdb.disconnect()
            logger.info("Disconnected from microscope")
        except Exception:
            logger.exception("Error during microscope disconnect (non-fatal)")
        finally:
            self._connected = False
            self._host = ""

    def ops(self) -> MicroscopeOps:
        """The Position Alignment hardware seam. Requires a connection."""
        if not self._connected:
            raise RuntimeError("Microscope is not connected")
        return build_autoscript_ops(self._sdb)


def create_client():
    """Default client factory: real AutoScript, or simulated via env switch.

    Returns a ``MicroscopeClient``, or a ``SimulatedMicroscopeClient`` when
    ``ASV_SIMULATED_MICROSCOPE=1`` (with small artificial connect/move
    delays so the UI's transitional states stay visible offline).
    """
    if os.environ.get(ASV_SIM_ENV) == "1":
        from asv_spin_mill_angle_calc.simulated_microscope import (
            SimulatedMicroscopeClient,
        )
        client = SimulatedMicroscopeClient(
            frames_dir=os.environ.get(ASV_SIM_FRAMES_ENV) or None)
        client.state.connect_delay_s = 0.5
        client.state.move_delay_s = 0.2
        logger.info("%s=1 — using the SIMULATED microscope client",
                    ASV_SIM_ENV)
        return client
    return MicroscopeClient()
