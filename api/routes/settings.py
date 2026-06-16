"""
api/routes/settings.py — Configuration management endpoints.

Read and update runtime settings: API keys status, posting flags,
schedule adjustments, and notification preferences.
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_auth
from config import (
    CHANNELS, POST_TO_YOUTUBE, POST_TO_FACEBOOK, POST_TO_INSTAGRAM,
    CEREBRAS_API_KEY, DEEPGRAM_API_KEY, VAST_API_KEY,
    GMAIL_ADDRESS, NTFY_TOPIC, DATA_DIR
)

router = APIRouter()
SETTINGS_FILE = DATA_DIR / "settings_override.json"

def _load_overrides() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {}

def _save_overrides(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))

# ─── Models ───────────────────────────────────────────────────────────────────
class PostingFlagsUpdate(BaseModel):
    post_to_youtube: bool | None = None
    post_to_facebook: bool | None = None
    post_to_instagram: bool | None = None

class NotificationUpdate(BaseModel):
    gmail_address: str | None = None
    ntfy_topic: str | None = None

# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_settings(user: dict = Depends(require_auth)):
    """Return current settings (API keys masked)."""
    overrides = _load_overrides()

    def _mask(key: str) -> str:
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}" if len(key) > 12 else "****"

    # YouTube connection status per channel
    from config import CREDENTIALS_DIR
    channel_connections = {}
    for ch, cfg in CHANNELS.items():
        token_path = CREDENTIALS_DIR / ch / "token.pickle"
        channel_connections[ch] = {
            "name": cfg["name"],
            "google_account": cfg["google_account"],
            "youtube_connected": token_path.exists(),
            "meta_connected": bool(cfg.get("page_id") if hasattr(cfg, "get") else False),
        }

    return {
        "api_keys": {
            "cerebras": _mask(CEREBRAS_API_KEY) if CEREBRAS_API_KEY != "YOUR_CEREBRAS_KEY" else "NOT_SET",
            "deepgram": _mask(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY != "YOUR_DEEPGRAM_KEY" else "NOT_SET",
            "vast_ai":  _mask(VAST_API_KEY)     if VAST_API_KEY     != "YOUR_VAST_KEY"      else "NOT_SET",
        },
        "posting_flags": {
            "post_to_youtube":   overrides.get("post_to_youtube",   POST_TO_YOUTUBE),
            "post_to_facebook":  overrides.get("post_to_facebook",  POST_TO_FACEBOOK),
            "post_to_instagram": overrides.get("post_to_instagram", POST_TO_INSTAGRAM),
        },
        "notifications": {
            "gmail_address": GMAIL_ADDRESS,
            "ntfy_topic":    NTFY_TOPIC,
        },
        "channels": channel_connections,
    }

@router.patch("/settings/posting-flags")
async def update_posting_flags(body: PostingFlagsUpdate, user: dict = Depends(require_auth)):
    overrides = _load_overrides()
    if body.post_to_youtube is not None:
        overrides["post_to_youtube"] = body.post_to_youtube
    if body.post_to_facebook is not None:
        overrides["post_to_facebook"] = body.post_to_facebook
    if body.post_to_instagram is not None:
        overrides["post_to_instagram"] = body.post_to_instagram
    _save_overrides(overrides)
    return {"message": "Posting flags updated", "flags": overrides}

@router.patch("/settings/notifications")
async def update_notifications(body: NotificationUpdate, user: dict = Depends(require_auth)):
    overrides = _load_overrides()
    if body.gmail_address:
        overrides["gmail_address"] = body.gmail_address
    if body.ntfy_topic:
        overrides["ntfy_topic"] = body.ntfy_topic
    _save_overrides(overrides)
    return {"message": "Notification settings updated"}

@router.post("/settings/test-notification")
async def test_notification(user: dict = Depends(require_auth)):
    """Send a test notification via email + ntfy.sh."""
    from modules.notifier import Notifier
    n = Notifier()
    n.push("Test notification from YouTube Content Factory ✅")
    n.email("Test — YouTube Factory", "This is a test notification from your dashboard.")
    return {"message": "Test notification sent"}

@router.get("/settings/cron-status")
async def get_cron_status(user: dict = Depends(require_auth)):
    """Check if cron jobs are installed."""
    import subprocess
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        cron_list = result.stdout
        jobs_installed = "post.py" in cron_list
        return {"installed": jobs_installed, "crontab": cron_list if jobs_installed else ""}
    except Exception as e:
        return {"installed": False, "error": str(e)}

@router.post("/settings/install-cron")
async def install_cron(user: dict = Depends(require_auth)):
    """Trigger cron job installation."""
    import subprocess, sys
    result = subprocess.run([sys.executable, "cron_setup.py"], capture_output=True, text=True)
    return {
        "message": "Cron setup executed",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
