"""
bulk_run.py — Master bulk generation orchestrator for VPS 1 (CPU phases).

Runs Phase 1-4 of the pipeline on VPS 1:
  1. Scrape 180 stories
  2. Generate 180 video ideas (Cerebras)
  3. Generate 180 scripts (Cerebras)
  4. Generate 180 SEO packages (Cerebras)
  5. Generate 180 audio files (Deepgram)
  6. [Then triggers VPS 2 for GPU phases]

Usage:
  python bulk_run.py --month 2026_06
  python bulk_run.py --month 2026_06 --resume
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from config import CHANNEL_NAMES, DATA_DIR, GDRIVE_BASE
from modules.logger import get_logger, log_bulk_event
from modules.notifier import Notifier
from modules.scraper import ContentScraper
from modules.idea_generator import IdeaGenerator
from modules.script_generator import ScriptGenerator
from modules.seo_generator import SEOGenerator
from modules.voice_generator import VoiceGenerator
from modules.drive_manager import DriveManager

log = get_logger("bulk_run")
STATE_FILE = DATA_DIR / "run_state.json"


class BulkRunner:
    """Orchestrates all VPS 1 CPU phases of the bulk generation pipeline."""

    def __init__(self, month: str, count: int = 60):
        self.month = month
        self.count = count
        self.dm = DriveManager()
        self.notifier = Notifier()

    def run(self, resume: bool = False):
        log.info(f"🚀 Bulk run starting for month_{self.month}")
        self.notifier.bulk_run_started(self.month)
        log_bulk_event("bulk_start", {"month": self.month})

        state = self._load_state() if resume else self._init_state()
        completed = set(state.get("completed_stages", []))

        try:
            if 1 not in completed:
                self._stage_1_scrape(state)
            if 2 not in completed:
                self._stage_2_ideas(state)
            if 3 not in completed:
                self._stage_3_scripts(state)
            if 4 not in completed:
                self._stage_4_seo(state)
            if 5 not in completed:
                self._stage_5_audio(state)

            log.info("✅ VPS 1 phases complete — GPU factory can now start on VPS 2")
            self.notifier.bulk_run_complete(
                self.month,
                {ch: state["completed_shorts"].get(ch, 0) for ch in CHANNEL_NAMES}
            )
            log_bulk_event("bulk_vps1_complete", {"month": self.month})

        except Exception as e:
            log.error(f"Bulk run error: {e}")
            self.notifier.bulk_run_error(state.get("stage", 0), str(e))
            state["status"] = "error"
            self._save_state(state)
            sys.exit(1)

    # ─── Stage 1: Scraping ───────────────────────────────────────────────────
    def _stage_1_scrape(self, state: dict):
        log.info("── Stage 1: Scraping Stories ──")
        state["stage"] = 1
        for channel in CHANNEL_NAMES:
            scraper = ContentScraper(channel)
            stories = scraper.scrape_month(count=self.count)
            # Save to local disk first (reliable inter-stage handoff)
            local_ch = DATA_DIR / f"run_{self.month}" / channel
            local_ch.mkdir(parents=True, exist_ok=True)
            (local_ch / "stories_raw.json").write_text(
                json.dumps(stories, indent=2, ensure_ascii=False)
            )
            # Also save to Drive (for long-term archiving)
            self.dm.save_stories(self.month, channel, stories)
            log.info(f"  [{channel}] Scraped {len(stories)} stories")
        self._complete_stage(state, 1, "Scraping")
        self._sync_to_drive()

    # ─── Stage 2: Ideas ──────────────────────────────────────────────────────
    def _stage_2_ideas(self, state: dict):
        log.info("── Stage 2: Generating Ideas ──")
        state["stage"] = 2
        ig = IdeaGenerator()
        for channel in CHANNEL_NAMES:
            # Load stories from local disk (reliable)
            local_ch = DATA_DIR / f"run_{self.month}" / channel
            stories_path = local_ch / "stories_raw.json"
            if stories_path.exists():
                stories = json.loads(stories_path.read_text())
            else:
                stories = self.dm.load_stories(self.month, channel)
            ideas = ig.generate_batch(channel, stories)
            # Save ideas to local disk for stage 3 to pick up reliably
            local_ch.mkdir(parents=True, exist_ok=True)
            (local_ch / "ideas.json").write_text(json.dumps(ideas, indent=2))
            log.info(f"  [{channel}] {len(ideas)} ideas generated")
        self._complete_stage(state, 2, "Ideas")

    # ─── Stage 3: Scripts ────────────────────────────────────────────────────
    def _stage_3_scripts(self, state: dict):
        log.info("── Stage 3: Generating Scripts ──")
        state["stage"] = 3
        sg = ScriptGenerator()
        for channel in CHANNEL_NAMES:
            # Load ideas from local disk first (reliable)
            local_ch = DATA_DIR / f"run_{self.month}" / channel
            ideas_path = local_ch / "ideas.json"
            if ideas_path.exists():
                ideas = json.loads(ideas_path.read_text())
            else:
                # Fallback: try Drive mount
                ch_dir = self.dm.channel_dir(self.month, channel)
                fallback_ideas = ch_dir / "ideas.json"
                if fallback_ideas.exists():
                    ideas = json.loads(fallback_ideas.read_text())
                    log.warning(f"[{channel}] Loaded ideas from Drive mount (fallback)")
                else:
                    log.warning(f"[{channel}] No ideas file — using stories directly")
                    stories_path2 = local_ch / "stories_raw.json"
                    if stories_path2.exists():
                        stories = json.loads(stories_path2.read_text())
                    else:
                        stories = self.dm.load_stories(self.month, channel)
                    ideas = [{"raw_story": s, "angle": s.get("title", ""), "hook_preview": ""} for s in stories]

            for i, idea in enumerate(ideas):
                script = sg.generate(channel, idea)
                self.dm.save_script(self.month, channel, i + 1, script)
            log.info(f"  [{channel}] {len(ideas)} scripts generated")
        self._complete_stage(state, 3, "Scripts")
        self._sync_to_drive()

    # ─── Stage 4: SEO ────────────────────────────────────────────────────────
    def _stage_4_seo(self, state: dict):
        log.info("── Stage 4: Generating SEO ──")
        state["stage"] = 4
        seo_gen = SEOGenerator()
        for channel in CHANNEL_NAMES:
            scripts = self.dm.load_scripts(self.month, channel)
            if not scripts:
                log.warning(f"[{channel}] No scripts found — skipping SEO")
                continue
            for i, script in enumerate(scripts):
                seo = seo_gen.generate(channel, script)
                self.dm.save_seo(self.month, channel, i + 1, seo)
            log.info(f"  [{channel}] {len(scripts)} SEO packages generated")
        self._complete_stage(state, 4, "SEO")
        self._sync_to_drive()

    # ─── Stage 5: Audio ──────────────────────────────────────────────────────
    def _stage_5_audio(self, state: dict):
        log.info("── Stage 5: Generating Audio ──")
        state["stage"] = 5
        vg = VoiceGenerator()
        for channel in CHANNEL_NAMES:
            scripts = self.dm.load_scripts(self.month, channel)
            if not scripts:
                log.warning(f"[{channel}] No scripts found — skipping Audio")
                continue
            for i, script in enumerate(scripts):
                out_path = str(self.dm.audio_path(self.month, channel, i + 1))
                vg.generate_voice(script, channel, out_path)
                state["completed_shorts"][channel] = i + 1
                if (i + 1) % 10 == 0:
                    self._save_state(state)
                    log.info(f"  [{channel}] Audio: {i + 1}/{len(scripts)}")
        self._complete_stage(state, 5, "Audio")
        self._sync_to_drive()

    # ─── Force-sync to Google Drive ───────────────────────────────────────────
    def _sync_to_drive(self):
        """Force rclone to upload any cached files from the VFS mount to Google Drive."""
        import subprocess, shutil
        rclone_bin = shutil.which("rclone") or "/usr/bin/rclone"
        local_path = str(GDRIVE_BASE)
        log.info("☁  Syncing to Google Drive...")
        result = subprocess.run(
            [rclone_bin, "copy", local_path, "gdrive:youtube_factory",
             "--transfers=4", "--checkers=8", "--no-traverse", "--stats=0"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info("☁  Google Drive sync complete ✅")
        else:
            log.warning(f"☁  Google Drive sync warning: {result.stderr[:200]}")

    # ─── State helpers ────────────────────────────────────────────────────────
    def _init_state(self) -> dict:
        state = {
            "month": self.month,
            "stage": 0,
            "completed_stages": [],
            "completed_shorts": {ch: 0 for ch in CHANNEL_NAMES},
            "total_shorts": self.count * len(CHANNEL_NAMES),
            "started_at": datetime.utcnow().isoformat(),
            "last_checkpoint": None,
            "status": "running",
            "errors": [],
        }
        self._save_state(state)
        return state

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
        return self._init_state()

    def _save_state(self, state: dict):
        state["last_checkpoint"] = datetime.utcnow().isoformat()
        STATE_FILE.write_text(json.dumps(state, indent=2))

    def _complete_stage(self, state: dict, stage: int, name: str):
        state["completed_stages"].append(stage)
        self._save_state(state)
        self.notifier.stage_complete(name)
        log.info(f"  ✅ Stage {stage} ({name}) complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk generation orchestrator")
    parser.add_argument("--month", required=True, help="Month e.g. 2026_06")
    parser.add_argument("--count", type=int, default=60, help="Number of shorts per channel (default: 60)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    args = parser.parse_args()

    runner = BulkRunner(args.month, args.count)
    runner.run(resume=args.resume)
