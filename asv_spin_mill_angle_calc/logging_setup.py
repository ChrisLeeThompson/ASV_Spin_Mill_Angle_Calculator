"""Application-wide logging configuration.

Single place that configures the root logger. Every other module obtains its
own logger with ``logging.getLogger(__name__)`` and never calls
``basicConfig`` itself, so the format and level are set once, here.
"""
from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger for the application.

    Args:
        level: Root log level. Pass ``logging.DEBUG`` for verbose diagnostics
            during development.
    """
    logging.basicConfig(
        format="%(asctime)s:\t%(levelname)s:\t%(name)s\t%(funcName)s:\t%(message)s",
        level=level,
        force=True,
    )