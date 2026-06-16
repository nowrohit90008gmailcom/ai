"""
modules/youtube_poster.py — Upload and publish videos to YouTube via Data API v3.

Handles all 3 channel accounts. Each upload costs ~1,600 API units.
With 3 separate Google Cloud projects we have 30,000 units/day free.
"""

import os
import time
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from config import CHANNELS
from modules.auth_manager import AuthManager
from modules.logger import get_logger, log_post_event

log = get_logger("youtube_poster")


class YouTubePoster:
    """Posts videos to YouTube for all 3 channels."""

    def __init__(self):
        self.auth = AuthManager()

    def post(self, channel: str, video_path: str, seo: dict, day: int, short_num: int) -> dict:
        """
        Upload a video to the channel's YouTube account.
        Returns: {"success": bool, "video_id": str, "url": str, "error": str}
        """
        ch_cfg = CHANNELS[channel]
        video_file = Path(video_path)

        if not video_file.exists():
            err = f"Video file not found: {video_path}"
            log.error(err)
            log_post_event(channel, day, short_num, "youtube", "error", error=err)
            return {"success": False, "error": err}

        try:
            youtube = self.auth.get_youtube_service(channel)
            body = {
                "snippet": {
                    "title": seo.get("title_clickbait", "Untitled"),
                    "description": seo.get("description", ""),
                    "tags": seo.get("tags", []),
                    "categoryId": ch_cfg["youtube_category_id"],
                    "defaultLanguage": "en-US",
                    "defaultAudioLanguage": "en-US",
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": ch_cfg["is_kids"],
                    "madeForKids": ch_cfg["is_kids"],
                },
            }

            media = MediaFileUpload(
                str(video_file),
                mimetype="video/mp4",
                resumable=True,
                chunksize=5 * 1024 * 1024,  # 5MB chunks
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    log.info(f"[{channel}] YouTube upload: {pct}%")

            video_id = response.get("id", "")
            url = f"https://youtube.com/shorts/{video_id}"
            log.info(f"[{channel}] ✅ YouTube: {url}")
            log_post_event(channel, day, short_num, "youtube", "success", url=url)
            return {"success": True, "video_id": video_id, "url": url}

        except Exception as e:
            log.error(f"[{channel}] YouTube upload failed: {e}")
            log_post_event(channel, day, short_num, "youtube", "error", error=str(e))
            return {"success": False, "error": str(e)}
