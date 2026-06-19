"""
modules/video_generator.py — Animate scene images into clips via ComfyUI + LTX-Video.

Single-GPU optimized:
  - Upload ALL images to ComfyUI simultaneously
  - Submit ALL animation jobs to the queue at once
  - ComfyUI processes them sequentially on the GPU with zero idle gaps
  - Python polls all concurrently so download starts the instant each finishes
"""

import time
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from config import (
    COMFYUI_URL, COMFYUI_URLS, CHANNELS,
    COMFYUI_POLL_WORKERS,
    LTX_MODEL, LTX_NUM_FRAMES, LTX_FPS,
    LTX_STEPS, LTX_CFG, LTX_RESOLUTION,
)
from modules.logger import get_logger

log = get_logger("video_generator")


class VideoGenerator:
    """Animates scene images into video clips via ComfyUI + LTX-Video."""

    def __init__(self, channel: str = None, comfyui_url: str = None):
        if comfyui_url:
            self.url = comfyui_url.rstrip("/")
        elif channel and channel in COMFYUI_URLS:
            self.url = COMFYUI_URLS[channel].rstrip("/")
        else:
            self.url = COMFYUI_URL.rstrip("/")

    def animate_scenes(self, channel: str, scenes_dir: Path,
                        clips_dir: Path, num_scenes: int = 8, audio_duration_sec: float = None) -> list[Path]:
        """
        Upload + queue ALL scene images at once, poll concurrently.
        GPU never idles between clip submissions.
        Returns list of clip paths.
        """
        scenes_dir = Path(scenes_dir)
        clips_dir  = Path(clips_dir)
        clips_dir.mkdir(parents=True, exist_ok=True)

        cfg = CHANNELS[channel]
        base_fps = LTX_FPS

        # Calculate exact frames needed per scene
        if audio_duration_sec and audio_duration_sec > 0:
            target_fps = base_fps
            sec_per_scene = audio_duration_sec / num_scenes
            target_frames = math.ceil(sec_per_scene * target_fps)
            
            # LTX requires 8n+1 frames
            n = math.ceil((target_frames - 1) / 8)
            calc_frames = max(9, 8 * n + 1)
        else:
            calc_frames = LTX_NUM_FRAMES

        settings = {
            "motion_bucket_id": cfg["motion_bucket_id"],
            "fps":              base_fps,
            "num_frames":       calc_frames,
        }

        # Build list of (scene_path, clip_path) pairs
        jobs = []
        for i in range(1, num_scenes + 1):
            scene_path = scenes_dir / f"scene_{i:02d}.png"
            clip_path  = clips_dir  / f"clip_{i:02d}.mp4"
            if scene_path.exists():
                jobs.append((scene_path, clip_path))
            else:
                log.warning(f"[{channel}] Missing scene: {scene_path.name} — skipping")

        if not jobs:
            log.error(f"[{channel}] No scene images found in {scenes_dir}")
            return []

        log.info(
            f"[{channel}] Batch animating {len(jobs)} clips — "
            f"{settings['num_frames']}fr@{settings['fps']}fps = "
            f"{settings['num_frames']//settings['fps']}s each"
        )

        return self._batch_animate(jobs, settings, channel)

    # ─── Batch Submit + Concurrent Poll ───────────────────────────────────────

    def _batch_animate(self, jobs: list[tuple], settings: dict,
                        channel: str) -> list[Path]:
        """
        Step 1: Upload all images + submit all workflows to ComfyUI queue.
        Step 2: Poll all jobs concurrently with ThreadPoolExecutor.
        """
        prompt_ids = {}   # prompt_id → clip_output_path

        # ── Step 1: Upload + queue all at once ─────────────────────────────────
        for scene_path, clip_path in jobs:
            try:
                uploaded_name = self._upload_image(scene_path)
                if not uploaded_name:
                    continue
                workflow = self._build_ltx_workflow(uploaded_name, settings)
                
                r = requests.post(f"{self.url}/prompt",
                                   json={"prompt": workflow}, timeout=15)
                r.raise_for_status()
                pid = r.json()["prompt_id"]
                prompt_ids[pid] = clip_path
                log.info(f"[{channel}] Queued {scene_path.name} → {clip_path.name} (id={pid[:8]})")
            except Exception as e:
                log.error(f"[{channel}] Submit failed for {scene_path.name}: {e}")

        if not prompt_ids:
            return [p for _, p in jobs]

        log.info(f"[{channel}] {len(prompt_ids)} clip jobs in GPU queue — polling...")

        # ── Step 2: Poll all concurrently ──────────────────────────────────────
        def poll_clip(pid_path: tuple) -> Path:
            pid, out_path = pid_path
            for _ in range(1200):   # max 20 min per clip
                time.sleep(2)
                try:
                    history = requests.get(
                        f"{self.url}/history/{pid}", timeout=10
                    ).json()
                    if pid in history:
                        outputs = history[pid].get("outputs", {})
                        for node_out in outputs.values():
                            for key in ("videos", "gifs", "images"):
                                if key in node_out:
                                    info = node_out[key][0]
                                    vid_bytes = requests.get(
                                        f"{self.url}/view",
                                        params={
                                            "filename": info["filename"],
                                            "subfolder": info.get("subfolder", ""),
                                            "type":     info.get("type", "output"),
                                        },
                                        timeout=120,
                                    ).content
                                    out_path.write_bytes(vid_bytes)
                                    log.info(f"[{channel}] Clip done: {out_path.name}")
                                    return out_path
                except Exception:
                    pass
            log.warning(f"[{channel}] Clip timeout: {out_path.name}")
            return out_path

        workers = min(COMFYUI_POLL_WORKERS, len(prompt_ids))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(poll_clip, item): item
                for item in prompt_ids.items()
            }
            results = [fut.result() for fut in as_completed(futures)]

        return sorted(results)

    # ─── Image Upload ─────────────────────────────────────────────────────────

    def _upload_image(self, image_path: Path) -> str | None:
        """Upload scene image to ComfyUI /upload/image. Returns server filename."""
        try:
            with open(image_path, "rb") as fh:
                r = requests.post(
                    f"{self.url}/upload/image",
                    files={"image": (image_path.name, fh, "image/png")},
                    timeout=30,
                )
            r.raise_for_status()
            return r.json().get("name", image_path.name)
        except Exception as e:
            log.error(f"Image upload failed for {image_path.name}: {e}")
            return None


    @staticmethod
    def _build_ltx_workflow(image_filename: str, settings: dict) -> dict:
        """
        ComfyUI workflow for LTX-Video.
        Uses a custom LTXImageToVideo wrapper node or similar compatible parameters.
        """
        width, height = LTX_RESOLUTION
        return {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": image_filename},
            },
            "2": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": LTX_MODEL,
                    "weight_dtype": "fp8_e4m3fn"
                }
            },
            "3": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "t5xxl_fp8_e4m3fn.safetensors",
                    "type": "ltxv"
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "",
                    "clip": ["3", 0]
                }
            },
            "5": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "ltx-video-vae.safetensors"
                }
            },
            "6": {
                "class_type": "LTXVImgToVideo",
                "inputs": {
                    "positive": ["4", 0],
                    "negative": ["4", 0],
                    "vae": ["5", 0],
                    "image": ["1", 0],
                    "width": width,
                    "height": height,
                    "length": settings["num_frames"],
                    "batch_size": 1,
                    "strength": 1.0
                }
            },
            "7": {
                "class_type": "LTXVScheduler",
                "inputs": {
                    "steps": LTX_STEPS,
                    "max_shift": 1.5,
                    "base_shift": 1.5,
                    "stretch": True,
                    "terminal": 0.0,
                    "model": ["2", 0]
                }
            },
            "8": {
                "class_type": "SamplerCustom",
                "inputs": {
                    "model": ["2", 0],
                    "add_noise": True,
                    "noise_seed": int(uuid.uuid4().int % 2**32),
                    "cfg": LTX_CFG,
                    "positive": ["6", 0],
                    "negative": ["6", 1],
                    "sampler": ["99", 0],
                    "sigmas": ["7", 0],
                    "latent_image": ["6", 2]
                }
            },
            "99": {
                "class_type": "KSamplerSelect",
                "inputs": {
                    "sampler_name": "euler"
                }
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["8", 0],
                    "vae": ["5", 0]
                }
            },
            "10": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["9", 0],
                    "frame_rate": settings["fps"],
                    "loop_count": 0,
                    "filename_prefix": "clip_ltx",
                    "format": "video/h264-mp4",
                    "pix_fmt": "yuv420p",
                    "crf": 19,
                    "save_metadata": False,
                    "pingpong": False,
                    "save_output": True
                }
            }
        }
