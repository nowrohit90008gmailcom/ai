"""
modules/meta_poster.py — Post Reels to Facebook and Instagram via Meta Graph API.

One Meta app handles both platforms.
Facebook: Direct video upload to Page
Instagram: 2-step (create container → publish)
"""

import time
from pathlib import Path

import requests

from config import META_CREDENTIALS, META_API_VERSION
from modules.logger import get_logger, log_post_event

log = get_logger("meta_poster")

GRAPH_BASE = f"https://graph.facebook.com/{META_API_VERSION}"


class MetaPoster:
    """Posts Reels to Facebook Pages and Instagram accounts."""

    def post_facebook(self, channel: str, video_path: str, caption: str,
                       day: int, short_num: int) -> dict:
        """Upload a Reel to the channel's Facebook Page."""
        creds = META_CREDENTIALS.get(channel, {})
        page_id    = creds.get("page_id")
        token      = creds.get("access_token")

        if not page_id or not token:
            err = f"[{channel}] Facebook credentials not configured"
            log.error(err)
            return {"success": False, "error": err}

        video_file = Path(video_path)
        if not video_file.exists():
            err = f"Video not found: {video_path}"
            log.error(err)
            return {"success": False, "error": err}

        try:
            response = requests.post(
                f"{GRAPH_BASE}/{page_id}/videos",
                data={
                    "description": caption,
                    "access_token": token,
                },
                files={"source": open(str(video_file), "rb")},
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            video_id = data.get("id", "")
            url = f"https://facebook.com/{page_id}/videos/{video_id}"
            log.info(f"[{channel}] ✅ Facebook: {url}")
            log_post_event(channel, day, short_num, "facebook", "success", url=url)
            return {"success": True, "video_id": video_id, "url": url}
        except Exception as e:
            log.error(f"[{channel}] Facebook post failed: {e}")
            log_post_event(channel, day, short_num, "facebook", "error", error=str(e))
            return {"success": False, "error": str(e)}

    def post_instagram(self, channel: str, video_path: str, caption: str,
                        day: int, short_num: int) -> dict:
        """
        Upload a Reel to the channel's Instagram account.
        Step 1: Create media container
        Step 2: Publish the container
        """
        creds = META_CREDENTIALS.get(channel, {})
        ig_id  = creds.get("ig_account_id")
        token  = creds.get("access_token")

        if not ig_id or not token:
            err = f"[{channel}] Instagram credentials not configured"
            log.error(err)
            return {"success": False, "error": err}

        video_file = Path(video_path)
        if not video_file.exists():
            return {"success": False, "error": f"Video not found: {video_path}"}

        try:
            # Step 1 — Create container
            r1 = requests.post(
                f"{GRAPH_BASE}/{ig_id}/media",
                data={
                    "media_type": "REELS",
                    "caption": caption,
                    "access_token": token,
                },
                files={"video": open(str(video_file), "rb")},
                timeout=300,
            )
            r1.raise_for_status()
            container_id = r1.json().get("id")

            if not container_id:
                raise ValueError(f"No container_id returned: {r1.json()}")

            # Wait for container processing
            time.sleep(15)

            # Step 2 — Publish
            r2 = requests.post(
                f"{GRAPH_BASE}/{ig_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": token,
                },
                timeout=60,
            )
            r2.raise_for_status()
            media_id = r2.json().get("id", "")
            url = f"https://instagram.com/p/{media_id}"
            log.info(f"[{channel}] ✅ Instagram: {url}")
            log_post_event(channel, day, short_num, "instagram", "success", url=url)
            return {"success": True, "media_id": media_id, "url": url}
        except Exception as e:
            log.error(f"[{channel}] Instagram post failed: {e}")
            log_post_event(channel, day, short_num, "instagram", "error", error=str(e))
            return {"success": False, "error": str(e)}
