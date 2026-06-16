"""
modules/drive_manager.py — Google Drive read/write via rclone mount.

The rclone mount makes Google Drive appear as a local directory
at /mnt/gdrive (or the configured GDRIVE_MOUNT path).
This module provides clean path helpers and file I/O methods.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

from config import GDRIVE_BASE, CHANNEL_NAMES
from modules.logger import get_logger

log = get_logger("drive_manager")


class DriveManager:
    """Manages all file I/O for the Google Drive (rclone mount) storage."""

    def __init__(self):
        self.base = GDRIVE_BASE

    # ─── Path helpers ────────────────────────────────────────────────────────
    def month_dir(self, month: str) -> Path:
        return self.base / f"month_{month}"

    def channel_dir(self, month: str, channel: str) -> Path:
        return self.month_dir(month) / channel

    def short_dir(self, month: str, channel: str, short_num: int, day: int | None = None) -> Path:
        """
        Returns the directory for a specific short.
        short_num is 1-based (1..60).
        If day is None, it's calculated from short_num (2 per day).
        """
        if day is None:
            day = ((short_num - 1) // 2) + 1
            s_in_day = ((short_num - 1) % 2) + 1
        else:
            s_in_day = short_num
        return self.channel_dir(month, channel) / f"day_{day:02d}_short_{s_in_day:02d}"

    def audio_path(self, month: str, channel: str, short_num: int) -> Path:
        return self.short_dir(month, channel, short_num) / "audio.mp3"

    def scenes_dir(self, month: str, channel: str, short_num: int) -> Path:
        return self.short_dir(month, channel, short_num)  # scenes stored in same dir

    def clips_dir(self, month: str, channel: str, short_num: int) -> Path:
        return self.short_dir(month, channel, short_num)  # clips stored in same dir

    def final_video_path(self, month: str, channel: str, short_num: int) -> Path:
        return self.short_dir(month, channel, short_num) / "final_short.mp4"

    def thumbnail_path(self, month: str, channel: str, short_num: int) -> Path:
        return self.short_dir(month, channel, short_num) / "thumbnail.png"

    def logs_dir(self) -> Path:
        return self.base / "run_logs"

    # ─── Story management ────────────────────────────────────────────────────
    def save_stories(self, month: str, channel: str, stories: list[dict]):
        ch_dir = self.channel_dir(month, channel)
        ch_dir.mkdir(parents=True, exist_ok=True)
        out_path = ch_dir / "stories_raw.json"
        out_path.write_text(json.dumps(stories, indent=2, ensure_ascii=False))
        log.info(f"[{channel}] Saved {len(stories)} stories → {out_path}")

    def load_stories(self, month: str, channel: str) -> list[dict]:
        path = self.channel_dir(month, channel) / "stories_raw.json"
        if not path.exists():
            log.warning(f"[{channel}] No stories file: {path}")
            return []
        return json.loads(path.read_text())

    # ─── Script management ───────────────────────────────────────────────────
    def save_script(self, month: str, channel: str, short_num: int, script: str):
        d = self.short_dir(month, channel, short_num)
        d.mkdir(parents=True, exist_ok=True)
        (d / "script.txt").write_text(script, encoding="utf-8")

    def load_scripts(self, month: str, channel: str) -> list[str]:
        ch_dir = self.channel_dir(month, channel)
        if not ch_dir.exists():
            return []
        scripts = []
        for short_dir in sorted(ch_dir.iterdir()):
            if short_dir.is_dir():
                script_file = short_dir / "script.txt"
                if script_file.exists():
                    scripts.append(script_file.read_text(encoding="utf-8"))
        return scripts

    # ─── SEO management ──────────────────────────────────────────────────────
    def save_seo(self, month: str, channel: str, short_num: int, seo: dict):
        d = self.short_dir(month, channel, short_num)
        d.mkdir(parents=True, exist_ok=True)
        (d / "seo.json").write_text(json.dumps(seo, indent=2))

    def load_seo(self, month: str, channel: str, short_num: int) -> dict:
        path = self.short_dir(month, channel, short_num) / "seo.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    # ─── Month initialization ────────────────────────────────────────────────
    def init_month_structure(self, month: str):
        """Pre-create all directory structure for a month."""
        for channel in CHANNEL_NAMES:
            for day in range(1, 31):
                for s in range(1, 3):
                    d = self.channel_dir(month, channel) / f"day_{day:02d}_short_{s:02d}"
                    d.mkdir(parents=True, exist_ok=True)
        log.info(f"Month structure created: month_{month}")

    # ─── Status checking ─────────────────────────────────────────────────────
    def count_ready(self, month: str, channel: str) -> int:
        ch_dir = self.channel_dir(month, channel)
        if not ch_dir.exists():
            return 0
        return sum(1 for d in ch_dir.iterdir()
                   if d.is_dir() and (d / "final_short.mp4").exists())

    def get_month_summary(self, month: str) -> dict:
        summary = {}
        for ch in CHANNEL_NAMES:
            summary[ch] = {
                "ready": self.count_ready(month, ch),
                "target": 60,
            }
        return summary
