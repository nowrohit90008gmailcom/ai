"""
api/routes/calendar.py — Monthly publishing calendar endpoints.

Returns the full month schedule showing which videos are scheduled,
published, or failed for each day and channel.
"""

import json
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from api.auth import require_auth
from config import CHANNELS, DATA_DIR, GDRIVE_BASE

router = APIRouter()

def _load_posts_log() -> list[dict]:
    path = DATA_DIR / "logs" / "posts.log"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries

@router.get("/calendar/{year}/{month_num}")
async def get_calendar(year: int, month_num: int, user: dict = Depends(require_auth)):
    """Return full month calendar with status for each slot."""
    month_str = f"{year}_{month_num:02d}"
    posts = _load_posts_log()

    # Index posts by (channel, day, short_num)
    post_index: dict[tuple, dict] = {}
    for p in posts:
        key = (p.get("channel"), p.get("day"), p.get("short_num"))
        post_index[key] = p

    days = _days_in_month(year, month_num)
    calendar = []

    for day in range(1, days + 1):
        day_slots = []
        for ch_key, ch_cfg in CHANNELS.items():
            for short_num, time_est in enumerate(ch_cfg["post_times_est"], start=1):
                key = (ch_key, day, short_num)
                post = post_index.get(key)

                # Check if video file exists on Drive
                video_path = (
                    GDRIVE_BASE /
                    f"month_{month_str}" /
                    ch_key /
                    f"day_{day:02d}_short_{short_num:02d}" /
                    "final_short.mp4"
                )
                video_ready = video_path.exists()

                if post:
                    status = post.get("status", "unknown")
                elif video_ready:
                    # File ready but not yet posted (future date)
                    slot_date = date(year, month_num, day)
                    if slot_date > date.today():
                        status = "scheduled"
                    else:
                        status = "ready"
                else:
                    status = "empty"

                day_slots.append({
                    "channel": ch_key,
                    "channel_name": ch_cfg["name"],
                    "short_num": short_num,
                    "time_est": time_est,
                    "status": status,
                    "youtube_url": post.get("youtube_url") if post else None,
                    "posted_at": post.get("posted_at") if post else None,
                    "color": ch_cfg["color_theme"],
                })

        calendar.append({
            "day": day,
            "date": f"{year}-{month_num:02d}-{day:02d}",
            "slots": day_slots,
        })

    return {
        "year": year,
        "month": month_num,
        "month_str": month_str,
        "days": days,
        "calendar": calendar,
    }

@router.get("/calendar/today")
async def get_today(user: dict = Depends(require_auth)):
    """Return today's posting schedule."""
    today = date.today()
    data = await get_calendar(today.year, today.month, user)
    day_data = next((d for d in data["calendar"] if d["day"] == today.day), None)
    return day_data or {}

def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, 12, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days
