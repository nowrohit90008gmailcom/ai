"""
modules/drive_sync.py — Upload finals from VPS 2 (Vast.ai) to Google Drive via rclone.

After VPS 2 finishes assembly, this syncs all final_short.mp4 and
thumbnail.png files up to the Google Drive mount so VPS 1 can access them.
"""

import subprocess
from pathlib import Path

from config import GDRIVE_MOUNT, RCLONE_REMOTE, CHANNEL_NAMES
from modules.logger import get_logger

log = get_logger("drive_sync")


class DriveSync:
    """Syncs local output to Google Drive using rclone."""

    def sync_finals(self, month: str, local_base: Path = None):
        """
        Upload all final_short.mp4 + thumbnail.png files for a month to Drive.
        Uses rclone copy to only transfer new/changed files.
        """
        if local_base is None:
            local_base = Path(f"/workspace/output/month_{month}")

        remote_path = f"{RCLONE_REMOTE}:youtube_factory/month_{month}"

        log.info(f"Starting rclone sync: {local_base} → {remote_path}")

        result = subprocess.run(
            [
                "rclone", "copy",
                str(local_base),
                remote_path,
                "--include", "final_short.mp4",
                "--include", "thumbnail.png",
                "--include", "seo.json",
                "--include", "script.txt",
                "--include", "audio.mp3",
                "--progress",
                "--transfers", "4",
                "--checkers", "8",
            ],
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
        )

        if result.returncode == 0:
            log.info(f"✅ Sync complete for month_{month}")
        else:
            log.error(f"rclone sync failed: {result.stderr[-500:]}")

        return result.returncode == 0

    def sync_logs(self, month: str, log_file: Path):
        """Upload run log to Google Drive."""
        remote_path = f"{RCLONE_REMOTE}:youtube_factory/run_logs/{log_file.name}"
        subprocess.run(
            ["rclone", "copyto", str(log_file), remote_path],
            capture_output=True,
            timeout=60,
        )
        log.info(f"Log synced: {log_file.name}")

    def check_mount(self) -> bool:
        """Verify Google Drive is mounted and accessible."""
        test_path = GDRIVE_MOUNT / "youtube_factory"
        try:
            return test_path.exists()
        except Exception:
            return False

    def rclone_ls(self, month: str, channel: str) -> list[str]:
        """List files in a channel/month directory on Google Drive."""
        remote_path = f"{RCLONE_REMOTE}:youtube_factory/month_{month}/{channel}"
        result = subprocess.run(
            ["rclone", "ls", remote_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.splitlines()
        return []

    def download_job(self, month: str, channel: str, short_dir_name: str, local_dir: Path) -> bool:
        """Download a specific short's raw files from Google Drive."""
        remote_path = f"{RCLONE_REMOTE}:youtube_factory/month_{month}/{channel}/{short_dir_name}"
        local_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Downloading job from {remote_path} to {local_dir}")
        result = subprocess.run(
            [
                "rclone", "copy",
                remote_path,
                str(local_dir),
                "--include", "script.txt",
                "--include", "seo.json",
                "--include", "audio.mp3",
                "--include", "idea.json",
            ],
            capture_output=True, text=True, timeout=600
        )
        return result.returncode == 0

    def upload_final(self, month: str, channel: str, short_dir_name: str, local_dir: Path) -> bool:
        """Upload a specific short's completed assets to Google Drive."""
        remote_path = f"{RCLONE_REMOTE}:youtube_factory/month_{month}/{channel}/{short_dir_name}"
        log.info(f"Uploading final job from {local_dir} to {remote_path}")
        result = subprocess.run(
            [
                "rclone", "copy",
                str(local_dir),
                remote_path,
                "--include", "final_short.mp4",
                "--include", "thumbnail.png",
                "--include", "seo.json",
                "--include", "script.txt",
                "--include", "generation_log.json",
            ],
            capture_output=True, text=True, timeout=1200
        )
        return result.returncode == 0
