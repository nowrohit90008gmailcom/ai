"""
modules/performance_tracker.py — Fetch and store YouTube + Meta analytics.

Queries YouTube Analytics API and stores results in data/analytics.json.
Run daily to keep the dashboard analytics page current.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from config import DATA_DIR, CHANNELS
from modules.auth_manager import AuthManager
from modules.logger import get_logger

log = get_logger("performance_tracker")

ANALYTICS_FILE = DATA_DIR / "analytics.json"


class PerformanceTracker:
    """Fetches and aggregates performance metrics from YouTube."""

    def __init__(self):
        self.auth = AuthManager()

    def update_all(self):
        """Refresh analytics for all channels and save to analytics.json."""
        data = self._load()
        for channel in CHANNELS:
            try:
                channel_data = self._fetch_youtube_analytics(channel)
                data[channel] = channel_data
                log.info(f"[{channel}] Analytics updated")
            except Exception as e:
                log.error(f"[{channel}] Analytics fetch failed: {e}")
        self._save(data)

    def _fetch_youtube_analytics(self, channel: str) -> dict:
        """Fetch last 30 days of analytics from YouTube Analytics API."""
        try:
            from googleapiclient.discovery import build as gapi_build
            yt_service = self.auth.get_youtube_service(channel)
            # Get channel ID first
            ch_response = yt_service.channels().list(part="id,statistics", mine=True).execute()
            items = ch_response.get("items", [])
            if not items:
                return self._empty_analytics()

            stats = items[0].get("statistics", {})
            ch_id = items[0]["id"]

            return {
                "channel_id": ch_id,
                "total_views": int(stats.get("viewCount", 0)),
                "total_subs": int(stats.get("subscriberCount", 0)),
                "total_videos": int(stats.get("videoCount", 0)),
                "total_watch_time_mins": 0,    # Needs Analytics API
                "total_subs_gained": 0,
                "posts": 0,
                "views": [],
                "watch_time": [],
                "subscribers": [],
                "platform_breakdown": {
                    "youtube": int(stats.get("viewCount", 0)),
                    "facebook": 0,
                    "instagram": 0,
                },
                "top_videos": self._fetch_top_videos(yt_service),
            }
        except Exception as e:
            log.warning(f"[{channel}] YouTube stats fetch error: {e}")
            return self._empty_analytics()

    def _fetch_top_videos(self, yt_service, max_results: int = 5) -> list[dict]:
        """Get top 5 videos by view count."""
        try:
            response = yt_service.videos().list(
                part="snippet,statistics",
                myRating="like",
                maxResults=max_results,
            ).execute()
            return [
                {
                    "title": item["snippet"].get("title", ""),
                    "video_id": item["id"],
                    "views": int(item.get("statistics", {}).get("viewCount", 0)),
                    "likes": int(item.get("statistics", {}).get("likeCount", 0)),
                    "url": f"https://youtube.com/shorts/{item['id']}",
                }
                for item in response.get("items", [])
            ]
        except Exception:
            return []

    def record_post(self, channel: str, platform: str):
        """Increment post count after a successful post."""
        data = self._load()
        if channel not in data:
            data[channel] = self._empty_analytics()
        data[channel]["posts"] = data[channel].get("posts", 0) + 1
        data[channel]["platform_breakdown"][platform] = (
            data[channel]["platform_breakdown"].get(platform, 0) + 1
        )
        self._save(data)

    @staticmethod
    def _empty_analytics() -> dict:
        return {
            "total_views": 0,
            "total_watch_time_mins": 0,
            "total_subs_gained": 0,
            "posts": 0,
            "views": [],
            "watch_time": [],
            "subscribers": [],
            "platform_breakdown": {"youtube": 0, "facebook": 0, "instagram": 0},
            "top_videos": [],
        }

    def _load(self) -> dict:
        if ANALYTICS_FILE.exists():
            return json.loads(ANALYTICS_FILE.read_text())
        return {ch: self._empty_analytics() for ch in CHANNELS}

    def _save(self, data: dict):
        ANALYTICS_FILE.write_text(json.dumps(data, indent=2))
