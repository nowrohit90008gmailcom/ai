"""
api/routes/analytics.py — Performance analytics endpoints.

Reads performance data stored by performance_tracker.py and returns
structured data for Chart.js charts on the analytics page.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import require_auth
from config import DATA_DIR, CHANNELS

router = APIRouter()

ANALYTICS_FILE = DATA_DIR / "analytics.json"

def _load_analytics() -> dict:
    if ANALYTICS_FILE.exists():
        return json.loads(ANALYTICS_FILE.read_text())
    # Return skeleton data if no real data yet
    return {
        ch: {
            "views": [],         # list of {"date": "...", "value": N}
            "watch_time": [],
            "subscribers": [],
            "posts": 0,
            "total_views": 0,
            "total_watch_time_mins": 0,
            "total_subs_gained": 0,
            "platform_breakdown": {
                "youtube": 0,
                "facebook": 0,
                "instagram": 0,
            },
            "top_videos": [],
        }
        for ch in CHANNELS
    }

@router.get("/analytics/overview")
async def get_analytics_overview(user: dict = Depends(require_auth)):
    """Return high-level analytics across all channels."""
    data = _load_analytics()
    overview = {}
    for ch_key, ch_data in data.items():
        overview[ch_key] = {
            "name": CHANNELS[ch_key]["name"],
            "color": CHANNELS[ch_key]["color_theme"],
            "total_views": ch_data.get("total_views", 0),
            "total_watch_time_mins": ch_data.get("total_watch_time_mins", 0),
            "total_subs_gained": ch_data.get("total_subs_gained", 0),
            "posts": ch_data.get("posts", 0),
            "platform_breakdown": ch_data.get("platform_breakdown", {}),
        }
    return overview

@router.get("/analytics/channel/{channel}")
async def get_channel_analytics(
    channel: str,
    days: int = Query(default=30, ge=7, le=90),
    user: dict = Depends(require_auth),
):
    """Return time-series analytics for a specific channel."""
    data = _load_analytics()
    ch_data = data.get(channel, {})
    return {
        "channel": channel,
        "channel_name": CHANNELS.get(channel, {}).get("name", channel),
        "days_requested": days,
        "views": ch_data.get("views", [])[-days:],
        "watch_time": ch_data.get("watch_time", [])[-days:],
        "subscribers": ch_data.get("subscribers", [])[-days:],
        "top_videos": ch_data.get("top_videos", [])[:5],
        "platform_breakdown": ch_data.get("platform_breakdown", {}),
    }

@router.get("/analytics/top-videos")
async def get_top_videos(
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(require_auth),
):
    """Return top performing videos across all channels."""
    data = _load_analytics()
    all_videos = []
    for ch_key, ch_data in data.items():
        for v in ch_data.get("top_videos", []):
            v["channel"] = ch_key
            v["channel_name"] = CHANNELS[ch_key]["name"]
            all_videos.append(v)

    all_videos.sort(key=lambda x: x.get("views", 0), reverse=True)
    return all_videos[:limit]

@router.post("/analytics/update")
async def trigger_analytics_update(user: dict = Depends(require_auth)):
    """Manually trigger a performance data refresh from YouTube/Meta APIs."""
    from modules.performance_tracker import PerformanceTracker
    tracker = PerformanceTracker()
    tracker.update_all()
    return {"message": "Analytics refresh triggered"}
