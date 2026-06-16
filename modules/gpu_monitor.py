"""
modules/gpu_monitor.py — Track GPU utilization and generate benchmark reports.
"""

import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from modules.logger import get_logger

log = get_logger("gpu_monitor")


class GpuMonitor:
    def __init__(self):
        self.running = False
        self.stats = {
            "vram_usage_mb": [],
            "utilization_pct": [],
        }
        self.timings = {
            "image_gen": [],
            "video_gen": [],
            "assembly": [],
            "upload": [],
            "total_short": []
        }
        self.start_time = None
        self._thread = None

    def start(self):
        self.running = True
        self.start_time = time.time()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="gpu-monitor")
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)

    def record_timing(self, stage: str, duration_sec: float):
        if stage in self.timings:
            self.timings[stage].append(duration_sec)

    def _monitor_loop(self):
        while self.running:
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(',')
                    if len(parts) == 2:
                        self.stats["vram_usage_mb"].append(int(parts[0].strip()))
                        self.stats["utilization_pct"].append(int(parts[1].strip()))
            except Exception as e:
                log.debug(f"nvidia-smi failed: {e}")
            
            # Poll every 5 seconds
            time.sleep(5)

    def _avg(self, lst: list) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    def generate_report(self, total_shorts: int, total_images: int, total_clips: int, output_path: Path, month: str = ""):
        """Generate benchmark_report.json"""
        total_time_hours = (time.time() - self.start_time) / 3600 if self.start_time else 0
        total_time_mins = total_time_hours * 60
        avg_short_time = self._avg(self.timings["total_short"])
        
        # Estimate monthly runtime based on target of 180 shorts
        estimated_monthly_hours = (avg_short_time * 180) / 3600 if avg_short_time > 0 else 0
        
        # FIX BUG 4: include month subfolder so the path matches where factory_runner writes failed shorts
        failed_count = 0
        failed_stages = {}
        if month:
            failed_dir = Path(f"/workspace/output/failed_shorts/{month}")
        else:
            failed_dir = Path("/workspace/output/failed_shorts")
        if failed_dir.exists():
            for ckpt in failed_dir.rglob("checkpoint.json"):
                failed_count += 1
                try:
                    data = json.loads(ckpt.read_text())
                    err = data.get("error_details", {})
                    stage = err.get("failed_stage", "unknown")
                    failed_stages[stage] = failed_stages.get(stage, 0) + 1
                except Exception:
                    pass

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "total_shorts_processed": total_shorts,
            "failed_jobs_count": failed_count,
            "failed_stages_breakdown": failed_stages,
            "total_gpu_hours_this_run": round(total_time_hours, 2),
            "estimated_monthly_runtime_hours": round(estimated_monthly_hours, 2),
            "throughput": {
                "images_per_minute": round(total_images / total_time_mins, 2) if total_time_mins > 0 else 0,
                "clips_per_minute": round(total_clips / total_time_mins, 2) if total_time_mins > 0 else 0,
                "shorts_per_hour": round(total_shorts / total_time_hours, 2) if total_time_hours > 0 else 0
            },
            "hardware": {
                "avg_vram_used_mb": round(self._avg(self.stats["vram_usage_mb"]), 2),
                "avg_gpu_utilization_pct": round(self._avg(self.stats["utilization_pct"]), 2),
                "max_vram_used_mb": max(self.stats["vram_usage_mb"]) if self.stats["vram_usage_mb"] else 0
            },
            "averages_seconds": {
                "image_generation": round(self._avg(self.timings["image_gen"]), 2),
                "clip_generation": round(self._avg(self.timings["video_gen"]), 2),
                "assembly": round(self._avg(self.timings["assembly"]), 2),
                "upload": round(self._avg(self.timings["upload"]), 2),
                "total_per_short": round(avg_short_time, 2)
            }
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2))
        log.info(f"Benchmark report generated: {output_path}")
        return report
