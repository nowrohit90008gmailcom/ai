"""
modules/factory_runner.py — Streaming, parallel worker architecture for production.

Features:
- Checkpointing per short (never regenerate)
- Persistent queue (jobs.json)
- Parallel workers (1 Image, 2 Video, 1 Assembly, 1 Upload)
- Minimal disk usage (< 10GB via Upload worker cleanup)
- Auto recovery & auto shutdown
"""

import argparse
import json
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty

from modules.image_generator import ImageGenerator
from modules.video_generator import VideoGenerator
from modules.video_assembler import VideoAssembler
from modules.thumbnail_generator import ThumbnailGenerator
from modules.drive_sync import DriveSync
from modules.gpu_monitor import GpuMonitor
from modules.logger import get_logger, log_bulk_event
from config import CHANNEL_NAMES, TARGET_SCENE_DURATION, MAX_SCENES, RCLONE_REMOTE

log = get_logger("factory_runner")

_DONE = object()

class JobState:
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    IMAGES_DONE = "images_done"
    VIDEOS_DONE = "videos_done"
    ASSEMBLY_DONE = "assembly_done"
    COMPLETED = "completed"
    FAILED = "failed"

class FactoryRunner:
    def __init__(self, month: str):
        self.month = month
        self.workspace = Path("/workspace/output") / f"month_{month}"
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        self.ig = ImageGenerator()
        self.vg = VideoGenerator()
        self.va = VideoAssembler()
        self.tg = ThumbnailGenerator()
        self.ds = DriveSync()
        self.monitor = GpuMonitor()
        
        # Queues
        self.download_q = Queue()
        self.image_q = Queue()
        self.video_q = Queue()
        self.assembly_q = Queue()
        self.upload_q = Queue()
        
        self.queues = [self.download_q, self.image_q, self.video_q, self.assembly_q, self.upload_q]

        # Counters for benchmark
        self.total_images = 0
        self.total_clips = 0

        # Heartbeat tracking
        self.heartbeats = {}
        
        # We rely on local checkpoint.json files instead of a central state
        self.pending_jobs = []
        self.processing_jobs = set()

    def _get_short_dir(self, channel: str, short_id: str) -> Path:
        return self.workspace / channel / short_id

    def _get_checkpoint(self, short_dir: Path) -> str:
        ckpt_file = short_dir / "checkpoint.json"
        if ckpt_file.exists():
            try:
                return json.loads(ckpt_file.read_text()).get("stage", JobState.PENDING)
            except Exception:
                pass
        return JobState.PENDING

    def _set_checkpoint(self, short_dir: Path, stage: str, stage_retries: dict = None, error_details: dict = None):
        short_dir.mkdir(parents=True, exist_ok=True)
        ckpt_file = short_dir / "checkpoint.json"
        
        current_data = {}
        if ckpt_file.exists():
            try:
                current_data = json.loads(ckpt_file.read_text())
            except Exception:
                pass
                
        retries = stage_retries if stage_retries is not None else current_data.get("stage_retries", {})
            
        data = {
            "short_id": short_dir.name,
            "stage": stage,
            "stage_retries": retries,
            "completed": stage == JobState.COMPLETED,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if error_details:
            data["error_details"] = error_details
        elif "error_details" in current_data:
            data["error_details"] = current_data["error_details"]
            
        ckpt_file.write_text(json.dumps(data))

    def run(self, channels: list[str] = None):
        channels = channels or CHANNEL_NAMES
        log.info(f"Starting Production Streaming Factory — month: {self.month}")
        self.monitor.start()

        # Discover pending jobs
        for channel in channels:
            dirs = self.ds.rclone_ls(self.month, channel)
            short_ids = set()
            completed_on_drive = set()
            for line in dirs:
                parts = line.strip().split()
                if len(parts) >= 2:
                    path_parts = parts[-1].split('/')
                    if len(path_parts) > 1 and ("short" in path_parts[0] or "day" in path_parts[0]):
                        short_ids.add(path_parts[0])
                        if path_parts[-1] == "final_short.mp4":
                            completed_on_drive.add(path_parts[0])
            
            for sid in sorted(short_ids):
                if sid in completed_on_drive:
                    log.info(f"[{channel}] Skipping {sid} — final_short.mp4 already on Drive")
                    continue
                    
                short_dir = self._get_short_dir(channel, sid)
                stage = self._get_checkpoint(short_dir)
                if stage not in (JobState.COMPLETED, JobState.FAILED):
                    job = {"channel": channel, "short_id": sid, "start_time": time.time(), "stage": stage}
                    self.pending_jobs.append(job)

        log.info(f"Found {len(self.pending_jobs)} jobs to process.")
        
        if not self.pending_jobs:
            log.info("No pending jobs. Shutting down.")
            self._shutdown_flow()
            return

        # Start Workers (1 Video Worker)
        threads = []
        threads.append(threading.Thread(target=self._download_worker, name="w-download"))
        threads.append(threading.Thread(target=self._image_worker, name="w-image"))
        threads.append(threading.Thread(target=self._video_worker, name="w-video-0"))
        threads.append(threading.Thread(target=self._assembly_worker, name="w-assembly"))
        threads.append(threading.Thread(target=self._upload_worker, name="w-upload"))
        threads.append(threading.Thread(target=self._heartbeat_watchdog, name="w-heartbeat"))

        for t in threads:
            t.daemon = True
            t.start()

        # Push jobs into the pipeline
        for job in self.pending_jobs:
            self.processing_jobs.add(f"{job['channel']}/{job['short_id']}")
            stage = job["stage"]
            
            if stage == JobState.ASSEMBLY_DONE:
                self.upload_q.put(job)
            elif stage == JobState.VIDEOS_DONE:
                self.assembly_q.put(job)
            elif stage == JobState.IMAGES_DONE:
                self.video_q.put(job)
            elif stage == JobState.DOWNLOADED:
                self.image_q.put(job)
            else:
                self.download_q.put(job)

        # Wait for all queues to empty
        def all_done():
            return (
                self.download_q.empty() and self.image_q.empty() and 
                self.video_q.empty() and self.assembly_q.empty() and 
                self.upload_q.empty() and not self.processing_jobs
            )

        while not all_done():
            time.sleep(10)
            
        log.info("All jobs processed.")
        self._shutdown_flow()

    def _mark_failed(self, job: dict, stage: str, error: str):
        job_str = f"{job['channel']}/{job['short_id']}"
        short_dir = self._get_short_dir(job['channel'], job['short_id'])
        
        ckpt_file = short_dir / "checkpoint.json"
        current_data = {}
        if ckpt_file.exists():
            try:
                current_data = json.loads(ckpt_file.read_text())
            except Exception:
                pass
                
        stage_retries = current_data.get("stage_retries", {})
        current_retries = stage_retries.get(stage, 0) + 1
        stage_retries[stage] = current_retries
        
        if current_retries >= 3:
            log.error(f"DLQ EXILE: {job_str} failed {stage} {current_retries} times. Exiling to failed_shorts/")
            error_details = {
                "failed_stage": stage,
                "error": str(error),
                "timestamp": datetime.utcnow().isoformat()
            }
            self._set_checkpoint(short_dir, JobState.FAILED, stage_retries, error_details)
            
            failed_dir = self.workspace.parent / "failed_shorts" / self.month / job['channel'] / job['short_id']
            failed_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(short_dir), str(failed_dir))
            
            if job_str in self.processing_jobs:
                self.processing_jobs.remove(job_str)
                
            fail_msg = f"{datetime.utcnow().isoformat()} | {job['short_id']} | EXILED ({stage}) | {error}\n"
        else:
            log.warning(f"RE-QUEUE: {job_str} failed {stage} (retry {current_retries}/3). Pushing back into pipeline.")
            self._set_checkpoint(short_dir, self._get_checkpoint(short_dir), stage_retries)
            
            if job_str in self.processing_jobs:
                self.processing_jobs.remove(job_str)
                
            self._requeue_job(job, short_dir)
            fail_msg = f"{datetime.utcnow().isoformat()} | {job['short_id']} | {stage} | retry:{current_retries} | {error}\n"

        fail_log = Path("/workspace/failures.log")
        with open(fail_log, "a") as f:
            f.write(fail_msg)

    def _requeue_job(self, job: dict, short_dir: Path):
        stage = self._get_checkpoint(short_dir)
        job["stage"] = stage
        self.processing_jobs.add(f"{job['channel']}/{job['short_id']}")
        
        if stage == JobState.ASSEMBLY_DONE:
            self.upload_q.put(job)
        elif stage == JobState.VIDEOS_DONE:
            self.assembly_q.put(job)
        elif stage == JobState.IMAGES_DONE:
            self.video_q.put(job)
        elif stage == JobState.DOWNLOADED:
            self.image_q.put(job)
        else:
            self.download_q.put(job)

    def _update_heartbeat(self, worker_name: str):
        self.heartbeats[worker_name] = time.time()

    def _heartbeat_watchdog(self):
        """Monitors all workers to ensure they haven't stalled for > 30 mins."""
        while True:
            time.sleep(60)
            now = time.time()
            for worker, last_beat in self.heartbeats.items():
                if now - last_beat > 1800: # 30 minutes
                    log.error(f"HEARTBEAT STALL: {worker} hasn't made progress in 30 minutes! Alerting and restarting process.")
                    with open("/workspace/failures.log", "a") as f:
                        f.write(f"{datetime.utcnow().isoformat()} | SYSTEM | HEARTBEAT | 0 | {worker} stalled for >30m\n")
                    subprocess.run(["sudo", "systemctl", "restart", "factory_runner"])  # Example recovery action
                    sys.exit(1)

    # --- Workers ---
    
    def _download_worker(self):
        worker_name = "download_worker"
        self._update_heartbeat(worker_name)
        while True:
            job = self.download_q.get()
            self._update_heartbeat(worker_name)
            channel, short_id = job["channel"], job["short_id"]
            short_dir = self._get_short_dir(channel, short_id)
            try:
                ok = self.ds.download_job(self.month, channel, short_id, short_dir)
                if ok:
                    self._set_checkpoint(short_dir, JobState.DOWNLOADED)
                    self.image_q.put(job)
                else:
                    self._mark_failed(job, "download", "rclone copy failed")
            except Exception as e:
                log.error(f"Download error {short_id}: {e}")
                self._mark_failed(job, "download", str(e))
            finally:
                self._update_heartbeat(worker_name)
                self.download_q.task_done()

    def _image_worker(self):
        worker_name = "image_worker"
        self._update_heartbeat(worker_name)
        while True:
            job = self.image_q.get()
            self._update_heartbeat(worker_name)
            channel, short_id = job["channel"], job["short_id"]
            short_dir = self._get_short_dir(channel, short_id)
            try:
                t0 = time.time()
                script = self._read_text(short_dir / "script.txt")
                idea = self._read_json(short_dir / "idea.json")
                
                audio_path = short_dir / "audio.mp3"
                duration = self._get_audio_duration(audio_path)
                import math
                target_dur = TARGET_SCENE_DURATION.get(channel, 5.0)
                num_scenes = min(MAX_SCENES, max(8, math.ceil(duration / target_dur)))
                
                scenes_dir = short_dir / "scenes"
                self.ig.generate_scenes(channel, script, scenes_dir, num_scenes=num_scenes, idea=idea)
                self.ig.generate_thumbnail(channel, short_dir, script=script, idea=idea)
                self.total_images += (num_scenes + 1)
                
                self.monitor.record_timing("image_gen", time.time() - t0)
                self._set_checkpoint(short_dir, JobState.IMAGES_DONE)
                self.video_q.put(job)
            except Exception as e:
                log.error(f"Image error {short_id}: {e}")
                self._mark_failed(job, "image_gen", str(e))
            finally:
                self._update_heartbeat(worker_name)
                self.image_q.task_done()

    def _video_worker(self):
        worker_name = "video_worker"
        self._update_heartbeat(worker_name)
        while True:
            job = self.video_q.get()
            self._update_heartbeat(worker_name)
            channel, short_id = job["channel"], job["short_id"]
            short_dir = self._get_short_dir(channel, short_id)
            try:
                t0 = time.time()
                audio_path = short_dir / "audio.mp3"
                duration = self._get_audio_duration(audio_path)
                import math
                target_dur = TARGET_SCENE_DURATION.get(channel, 5.0)
                num_scenes = min(MAX_SCENES, max(8, math.ceil(duration / target_dur)))
                
                scenes_dir = short_dir / "scenes"
                clips_dir = short_dir / "clips"
                self.vg.animate_scenes(channel, scenes_dir, clips_dir, num_scenes=num_scenes, audio_duration_sec=duration)
                self.total_clips += num_scenes
                
                for clip in sorted(clips_dir.glob("clip_*.mp4")):
                    target = short_dir / clip.name
                    if not target.exists():
                        target.write_bytes(clip.read_bytes())
                        
                self.monitor.record_timing("video_gen", time.time() - t0)
                self._set_checkpoint(short_dir, JobState.VIDEOS_DONE)
                self.assembly_q.put(job)
            except Exception as e:
                log.error(f"Video error {short_id}: {e}")
                self._mark_failed(job, "video_gen", str(e))
            finally:
                self._update_heartbeat(worker_name)
                self.video_q.task_done()

    def _assembly_worker(self):
        worker_name = "assembly_worker"
        self._update_heartbeat(worker_name)
        while True:
            job = self.assembly_q.get()
            self._update_heartbeat(worker_name)
            channel, short_id = job["channel"], job["short_id"]
            short_dir = self._get_short_dir(channel, short_id)
            try:
                t0 = time.time()
                script = self._read_text(short_dir / "script.txt")
                seo = self._read_json(short_dir / "seo.json")
                
                raw_thumb = short_dir / "thumbnail_raw.png"
                title = seo.get("title_clickbait", "") if seo else ""
                if raw_thumb.exists() and title:
                    final_thumb = short_dir / "thumbnail.png"
                    self.tg.generate(channel, raw_thumb, title, final_thumb)
                    
                ok = self.va.assemble(short_dir, script=script, seo=seo)
                if ok:
                    self.monitor.record_timing("assembly", time.time() - t0)
                    self._set_checkpoint(short_dir, JobState.ASSEMBLY_DONE)
                    self.upload_q.put(job)
                else:
                    self._mark_failed(job, "assembly", "ffmpeg failed")
            except Exception as e:
                log.error(f"Assembly error {short_id}: {e}")
                self._mark_failed(job, "assembly", str(e))
            finally:
                self._update_heartbeat(worker_name)
                self.assembly_q.task_done()

    def _upload_worker(self):
        worker_name = "upload_worker"
        self._update_heartbeat(worker_name)
        while True:
            job = self.upload_q.get()
            self._update_heartbeat(worker_name)
            channel, short_id = job["channel"], job["short_id"]
            short_dir = self._get_short_dir(channel, short_id)
            job_str = f"{channel}/{short_id}"
            try:
                t0 = time.time()
                # Create generation log
                log_data = {"short_id": short_id, "completed_at": datetime.utcnow().isoformat(), "processing_time": time.time() - job["start_time"]}
                (short_dir / "generation_log.json").write_text(json.dumps(log_data))
                
                ok = self.ds.upload_final(self.month, channel, short_id, short_dir)
                if ok:
                    self.monitor.record_timing("upload", time.time() - t0)
                    self.monitor.record_timing("total_short", time.time() - job["start_time"])
                    
                    self._set_checkpoint(short_dir, JobState.COMPLETED)
                    
                    # Clean up local files, but KEEP checkpoint.json
                    for file_path in short_dir.iterdir():
                        if file_path.name != "checkpoint.json":
                            if file_path.is_dir():
                                shutil.rmtree(file_path, ignore_errors=True)
                            else:
                                file_path.unlink(missing_ok=True)
                    log.info(f"[{channel}] Cleaned up local files for {short_id} (kept checkpoint)")
                    
                    if job_str in self.processing_jobs:
                        self.processing_jobs.remove(job_str)
                else:
                    self._mark_failed(job, "upload", "rclone upload failed")
            except Exception as e:
                log.error(f"Upload error {short_id}: {e}")
                self._mark_failed(job, "upload", str(e))
            finally:
                self._update_heartbeat(worker_name)
                self.upload_q.task_done()

    # --- Shutdown & Utils ---
    def _shutdown_flow(self):
        self.monitor.stop()
        report_path = Path("/workspace/benchmark_report.json")
        completed_shorts = len(self.state["completed"]) if hasattr(self, "state") and "completed" in self.state else len([p for p in self.workspace.glob("*/*/checkpoint.json") if self._get_checkpoint(p.parent) == JobState.COMPLETED])
        self.monitor.generate_report(completed_shorts, self.total_images, self.total_clips, report_path)
        
        log.info("Uploading final benchmark report...")
        subprocess.run(["rclone", "copy", str(report_path), f"{RCLONE_REMOTE}:youtube_factory/month_{self.month}/"])
        
        # Sync logs
        log_file = Path("/workspace/logs/factory.log")
        if log_file.exists():
            self.ds.sync_logs(self.month, log_file)
            
        log.info("Initiating auto-shutdown.")
        time.sleep(10)
        subprocess.run(["sudo", "shutdown", "-h", "now"])

    @staticmethod
    def _get_audio_duration(audio_path: Path) -> float:
        if not audio_path.exists():
            return 45.0
        try:
            import subprocess
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 str(audio_path)],
                capture_output=True, text=True, timeout=10
            )
            return float(res.stdout.strip())
        except Exception:
            return 45.0

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Streaming Production Factory Runner")
    parser.add_argument("--month", required=True)
    parser.add_argument("--channels", nargs="+")
    args = parser.parse_args()
    
    runner = FactoryRunner(args.month)
    runner.run(channels=args.channels)
