"""
Logging configuration for video-mcp.

Configures:
- Human-readable rotating log file: `video-mcp.log`
- Structured JSONL events log: `events.jsonl`

Defaults to `~/Downloads/videos/logs` (or `OUTPUT_DIR/logs` when `OUTPUT_DIR` is set).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from ..config.paths import get_log_directory
from ..config.settings import get_settings

_CONFIGURED = False


def _has_rotating_file_handler(logger: logging.Logger, file_path: Path) -> bool:
    target = str(file_path)
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and getattr(handler, "baseFilename", "") == target
        ):
            return True
    return False


def _has_console_handler(logger: logging.Logger) -> bool:
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            return True
    return False


def configure_logging() -> None:
    """Configure application logging (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    human_formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # Console logs (for MCP host capture)
    if not _has_console_handler(root_logger):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(human_formatter)
        root_logger.addHandler(stream_handler)

    # File logs
    try:
        log_dir = get_log_directory()
        log_file = log_dir / "video-mcp.log"
        events_file = log_dir / "events.jsonl"

        # Rotating file logs
        if not _has_rotating_file_handler(root_logger, log_file):
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(human_formatter)
            root_logger.addHandler(file_handler)

        # Structured JSONL events log (pure JSON per line)
        events_logger = logging.getLogger("video_mcp.events")
        events_logger.setLevel(level)
        events_logger.propagate = False
        if not _has_rotating_file_handler(events_logger, events_file):
            events_handler = RotatingFileHandler(
                events_file,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8",
            )
            events_handler.setLevel(level)
            events_handler.setFormatter(logging.Formatter("%(message)s"))
            events_logger.addHandler(events_handler)
    except Exception:
        root_logger.exception(
            "Failed to initialize file logging; continuing with console logging only"
        )

    _CONFIGURED = True


def log_event(event: str, **fields: Any) -> None:
    """Write a structured event to the JSONL events log."""
    try:
        configure_logging()

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }

        logging.getLogger("video_mcp.events").info(
            json.dumps(payload, ensure_ascii=False, default=str)
        )
    except Exception:
        logging.getLogger(__name__).debug("Failed to write events log entry", exc_info=True)
