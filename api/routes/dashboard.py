"""
api/routes/dashboard.py — Home / Control Center API endpoints.

Returns overall system status, per-channel progress, next scheduled post,
and system health metrics.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from api.auth import require_auth
from config import CHANNELS, DATA_DIR, GDRIVE_BASE

router = APIRouter()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def load_run_state() -> dict:
    path = DATA_DIR / "run_state.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"status": "idle", "stage": 0, "completed_shorts": {}, "completed_stages": []}

def load_posts_log() -> list[dict]:
    path = DATA_DIR / "logs" / "posts.log"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines()[-100:]:  # last 100 lines
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries

def count_ready_videos(channel: str, month: str) -> int:
    """Count final_short.mp4 files in Google Drive for this channel/month."""
    channel_dir = GDRIVE_BASE / f"month_{month}" / channel
    if not channel_dir.exists():
        return 0
    return sum(1 for d in channel_dir.iterdir()
               if d.is_dir() and (d / "final_short.mp4").exists())

# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/dashboard/status")
async def get_status(user: dict = Depends(require_auth)):
    """Return overall system status for the dashboard home page."""
    run_state = load_run_state()
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y_%m")

    channels_status = {}
    for ch_key, ch_cfg in CHANNELS.items():
        ready = count_ready_videos(ch_key, month)
        channels_status[ch_key] = {
            "name": ch_cfg["name"],
            "color": ch_cfg["color_theme"],
            "ready_videos": ready,
            "target_videos": 60,
            "percent_complete": round((ready / 60) * 100, 1),
            "post_times_est": ch_cfg["post_times_est"],
        }

    # Recent post activity
    recent_posts = load_posts_log()[-10:]

    # Next scheduled post
    next_post = _get_next_post()

    return {
        "run_state": run_state,
        "channels": channels_status,
        "recent_posts": recent_posts,
        "next_post": next_post,
        "month": month,
        "server_time_utc": now.isoformat(),
    }

@router.get("/dashboard/summary")
async def get_summary(user: dict = Depends(require_auth)):
    """High-level KPI summary cards for the dashboard."""
    run_state = load_run_state()
    posts = load_posts_log()

    total_posted = sum(1 for p in posts if p.get("status") == "success")
    total_failed  = sum(1 for p in posts if p.get("status") == "error")

    completed = run_state.get("completed_shorts", {})
    total_ready = sum(completed.values())

    return {
        "total_posted_this_month": total_posted,
        "total_failed_this_month":  total_failed,
        "total_ready_videos":       total_ready,
        "bulk_run_status":          run_state.get("status", "idle"),
        "bulk_run_stage":           run_state.get("stage", 0),
        "bulk_run_stage_name":      _stage_name(run_state.get("stage", 0)),
    }

# ─── Internal helpers ─────────────────────────────────────────────────────────
STAGE_NAMES = {
    0: "Idle",
    1: "Scraping Stories",
    2: "Generating Scripts",
    3: "Generating SEO",
    4: "Generating Audio",
    5: "Generating Images",
    6: "Generating Video Clips",
    7: "Assembling Finals",
    8: "Uploading to Drive",
    9: "Complete",
}

def _stage_name(stage: int) -> str:
    return STAGE_NAMES.get(stage, "Unknown")

def _get_next_post() -> dict | None:
    """Find the next scheduled post time across all channels."""
    now = datetime.now(timezone.utc)
    candidates = []
    for ch_key, ch_cfg in CHANNELS.items():
        for time_utc in ch_cfg["post_times_utc"]:
            h, m = map(int, time_utc.split(":"))
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                # Move to tomorrow
                from datetime import timedelta
                candidate += timedelta(days=1)
            candidates.append({
                "channel": ch_key,
                "channel_name": ch_cfg["name"],
                "time_utc": candidate.isoformat(),
                "time_est": time_utc,  # approximate
                "delta_seconds": int((candidate - now).total_seconds()),
            })
    if not candidates:
        return None
    return min(candidates, key=lambda x: x["delta_seconds"])
