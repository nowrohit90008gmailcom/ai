"""
modules/logger.py — Structured logging using loguru.

All modules use get_logger(__name__) to get a named logger.
Logs go to:
  - console (INFO+)
  - data/logs/app.log (DEBUG+, rotating 10MB)
  - data/logs/errors.log (ERROR+ only)
  - data/logs/posts.log (posting events only, JSON-lines)
  - data/logs/bulk_runs.log (bulk run events)
"""

import json
import sys
from pathlib import Path
from datetime import datetime

from loguru import logger as _loguru

from config import LOGS_DIR

# ─── Ensure log directories exist ────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Remove default handler ──────────────────────────────────────────────────
_loguru.remove()

# ─── Console handler (colorized) ─────────────────────────────────────────────
_loguru.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[name]}</cyan> — {message}",
    colorize=True,
)

# ─── App log (all levels, rotating) ──────────────────────────────────────────
_loguru.add(
    str(LOGS_DIR / "app.log"),
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[name]} — {message}",
    enqueue=True,
)

# ─── Error log ────────────────────────────────────────────────────────────────
_loguru.add(
    str(LOGS_DIR / "errors.log"),
    level="ERROR",
    rotation="5 MB",
    retention="60 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[name]} — {message}\n{exception}",
    enqueue=True,
)

# ─── Public API ──────────────────────────────────────────────────────────────
def get_logger(name: str):
    """Return a logger bound with the module name."""
    return _loguru.bind(name=name)


def log_post_event(channel: str, day: int, short_num: int, platform: str,
                   status: str, url: str = None, error: str = None):
    """Write a JSON-line entry to posts.log for calendar/analytics tracking."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "channel": channel,
        "day": day,
        "short_num": short_num,
        "platform": platform,
        "status": status,
        "youtube_url": url,
        "error": error,
        "posted_at": datetime.utcnow().isoformat() + "Z",
    }
    with open(LOGS_DIR / "posts.log", "a") as f:
        f.write(json.dumps(entry) + "\n")


def log_bulk_event(event: str, data: dict = None):
    """Write a JSON-line entry to bulk_runs.log."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": event,
        **(data or {}),
    }
    with open(LOGS_DIR / "bulk_runs.log", "a") as f:
        f.write(json.dumps(entry) + "\n")
