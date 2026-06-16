"""
post.py — Daily posting script called by cron jobs.

Usage (called automatically by cron):
  python post.py --channel horror_crime --short 1
  python post.py --channel manners_fun --short 2

Downloads that day's video from Google Drive, posts to all platforms,
logs the result, notifies via push, then deletes the temp local copy.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import (
    CHANNELS, CHANNEL_NAMES, GDRIVE_BASE,
    POST_TO_YOUTUBE, POST_TO_FACEBOOK, POST_TO_INSTAGRAM,
    POST_MAX_RETRIES, POST_RETRY_DELAYS,
)
from modules.logger import get_logger, log_post_event
from modules.notifier import Notifier
from modules.youtube_poster import YouTubePoster
from modules.meta_poster import MetaPoster
from modules.drive_manager import DriveManager

log = get_logger("post")


def get_todays_video_path(channel: str, short_num: int) -> Path:
    """Calculate Google Drive path for today's video."""
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y_%m")
    day = now.day
    return (
        GDRIVE_BASE /
        f"month_{month}" / channel /
        f"day_{day:02d}_short_{short_num:02d}" /
        "final_short.mp4"
    )

def get_seo(channel: str, short_num: int) -> dict:
    """Load SEO data for today's video."""
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y_%m")
    day = now.day
    seo_path = (
        GDRIVE_BASE /
        f"month_{month}" / channel /
        f"day_{day:02d}_short_{short_num:02d}" /
        "seo.json"
    )
    if seo_path.exists():
        return json.loads(seo_path.read_text())
    return {"title_clickbait": f"{CHANNELS[channel]['name']} — Day {day}",
            "description": "Watch for more!", "tags": [], "hashtags": ["#Shorts"]}

def build_caption(seo: dict) -> str:
    """Build social media caption from SEO data."""
    hashtags = " ".join(seo.get("hashtags", ["#Shorts"]))
    return f"{seo.get('title_clickbait', '')}\n\n{seo.get('description', '')[:500]}\n\n{hashtags}"

def post_video(channel: str, short_num: int):
    """Main posting logic with retry."""
    now = datetime.now(timezone.utc)
    day = now.day
    notifier = Notifier()
    yt = YouTubePoster()
    meta = MetaPoster()

    video_path = get_todays_video_path(channel, short_num)
    seo = get_seo(channel, short_num)
    caption = build_caption(seo)

    results = {}

    # Post to each platform with retry
    for attempt in range(POST_MAX_RETRIES):
        try:
            if POST_TO_YOUTUBE:
                results["youtube"] = yt.post(channel, str(video_path), seo, day, short_num)
            if POST_TO_FACEBOOK:
                results["facebook"] = meta.post_facebook(channel, str(video_path), caption, day, short_num)
            if POST_TO_INSTAGRAM:
                results["instagram"] = meta.post_instagram(channel, str(video_path), caption, day, short_num)

            # Check if all succeeded
            all_ok = all(r.get("success") for r in results.values())
            if all_ok:
                log.info(f"[{channel}] Short {short_num} posted successfully to all platforms ✅")
                notifier.post_success(channel, "all platforms")
                return results

            # Partial failure — retry
            failed = [p for p, r in results.items() if not r.get("success")]
            log.warning(f"[{channel}] Partial failure: {failed} — attempt {attempt+1}/{POST_MAX_RETRIES}")

        except Exception as e:
            log.error(f"[{channel}] Post attempt {attempt+1} failed: {e}")

        if attempt < POST_MAX_RETRIES - 1:
            wait = POST_RETRY_DELAYS[attempt]
            log.info(f"Retrying in {wait}s...")
            time.sleep(wait)

    # All retries exhausted
    notifier.post_failed(channel, "multiple platforms", day, "Max retries exceeded")
    raise RuntimeError(f"Failed to post {channel} short {short_num} after {POST_MAX_RETRIES} attempts")


def main():
    parser = argparse.ArgumentParser(description="Post today's video to all platforms")
    parser.add_argument("--channel", required=True, choices=CHANNEL_NAMES,
                        help="Channel to post for")
    parser.add_argument("--short",   required=True, type=int, choices=[1, 2],
                        help="Which short (1 or 2) to post today")
    args = parser.parse_args()

    log.info(f"🎬 Posting {args.channel} short {args.short}")
    results = post_video(args.channel, args.short)
    log.info(f"Results: {results}")


if __name__ == "__main__":
    main()
