"""
modules/video_assembler.py — Full ffmpeg assembly pipeline.

Fixes applied vs original:
  ✅ FIX 1: Video loops to match full audio length (-stream_loop -1 + -shortest)
  ✅ FIX 2: Captions burned in from SRT via subtitles filter (Deepgram STT accurate)
  ✅ FIX 3: Background music mixed at 12% volume (royalty-free from static/music/)
  ✅ FIX 4: Hook text overlay on first 3 seconds
  ✅ FIX 5: Scales to 1080×1920 with padding
  ✅ FIX 6: H.264 + AAC, -movflags +faststart for streaming

Final duration = audio narration length (30–50 seconds).
"""

import os
import random
import subprocess
from pathlib import Path

from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    MUSIC_DIR, MUSIC_VOLUME, HOOK_TEXT_DURATION,
    CAPTION_FONT_SIZE, CAPTION_OUTLINE,
)
from modules.caption_generator import CaptionGenerator
from modules.sfx_generator import SFXGenerator
from modules.logger import get_logger

log = get_logger("video_assembler")


class VideoAssembler:
    """Assembles clips + audio → final short, with captions, music, and hook text."""

    def assemble(self, short_dir: Path, script: str = "", seo: dict = None) -> bool:
        """
        Full pipeline for one short.
        short_dir must contain: clip_01.mp4 … clip_08.mp4, audio.mp3
        Writes: final_short.mp4, captions.srt
        Returns True on success.
        """
        short_dir   = Path(short_dir)
        audio_path  = short_dir / "audio.mp3"
        output_path = short_dir / "final_short.mp4"
        clips_txt   = short_dir / "_clips.txt"
        raw_video   = short_dir / "_raw_video.mp4"
        srt_path    = short_dir / "captions.srt"

        clip_paths  = sorted(short_dir.glob("clip_*.mp4"))

        if not clip_paths:
            log.error(f"No clips found in {short_dir}")
            return False
        if not audio_path.exists():
            log.error(f"Audio not found: {audio_path}")
            return False

        try:
            # ── Step 1: Concatenate clips ─────────────────────────────────────
            clips_txt.write_text(
                "\n".join(f"file '{c.name}'" for c in clip_paths),
                encoding="utf-8",
            )
            r1 = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", "_clips.txt", "-c", "copy", "_raw_video.mp4"],
                capture_output=True, text=True, timeout=300,
                cwd=str(short_dir),
            )
            if r1.returncode != 0:
                log.error(f"Clip concat failed:\n{r1.stderr[-600:]}")
                return False
            log.info(f"Clips concatenated: {len(clip_paths)} × clips → _raw_video.mp4")

            # ── Step 2: Generate captions SRT ────────────────────────────────
            cap_gen = CaptionGenerator()
            cap_gen.generate_srt(script, str(audio_path), str(srt_path))

            # ── Step 3: Build and run final ffmpeg assembly command ───────────
            hook_text  = (seo or {}).get("title_clickbait", "") if seo else ""
            
            channel = short_dir.parent.name
            music_path = self._pick_music(channel)
            
            # ── Step 2.5: Generate SFX Track ─────────────────────────────────
            sfx_path = short_dir / "sfx_track.mp3"
            sfx_gen = SFXGenerator()
            sfx_gen.generate_sfx_track(srt_path, clip_paths, audio_path, sfx_path)

            success = self._run_assembly(
                short_dir   = short_dir,
                audio_path  = audio_path,
                raw_video   = raw_video,
                srt_path    = srt_path,
                output_path = output_path,
                hook_text   = hook_text,
                music_path  = music_path,
                sfx_path    = sfx_path,
            )

            if success:
                size_mb = output_path.stat().st_size / (1024 * 1024)
                log.info(f"✅ Assembly complete: {output_path.name} ({size_mb:.1f} MB)")

            return success

        except Exception as e:
            log.error(f"Assembly error in {short_dir.name}: {e}")
            return False

        finally:
            for tmp in [clips_txt, raw_video, short_dir / "sfx_track.mp3"]:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    def assemble_batch(self, channel_dir: Path, scripts: list[str] = None,
                        seos: list[dict] = None) -> dict:
        """Assemble all shorts in a channel directory."""
        results = {"success": 0, "failed": 0}
        short_dirs = sorted(
            d for d in channel_dir.iterdir()
            if d.is_dir() and ("short_" in d.name or "day_" in d.name)
        )
        for i, short_dir in enumerate(short_dirs):
            # FIX BUG 7: guard against index out of range if lists are shorter than dirs
            script = scripts[i] if scripts and i < len(scripts) else ""
            seo    = seos[i]    if seos    and i < len(seos)    else {}
            ok = self.assemble(short_dir, script=script, seo=seo)
            results["success" if ok else "failed"] += 1

        log.info(
            f"Batch assembly: {results['success']} succeeded, "
            f"{results['failed']} failed"
        )
        return results

    # ─── Core ffmpeg Command ──────────────────────────────────────────────────
    def _run_assembly(
        self,
        short_dir: Path,
        audio_path: Path,
        raw_video: Path,
        srt_path: Path,
        output_path: Path,
        hook_text: str = "",
        music_path: Path = None,
        sfx_path: Path = None,
    ) -> bool:
        """
        Build and execute the ffmpeg filter_complex command.

        Inputs:
          [0] video  — raw concatenated clips (streamed with -stream_loop -1)
          [1] audio  — narration (defines final length via -shortest)
          [2] music  — optional background music (if present)
          [3] sfx    — optional SFX track (if present)
        """
        # Scale + pad filter (letterbox to 1080×1920)
        scale_filter = (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1"
        )

        # Subtitles filter — use just filename since we set cwd=short_dir
        # This avoids Windows drive-letter colon escaping issues
        sub_style = (
            f"FontName=Arial,"
            f"FontSize={CAPTION_FONT_SIZE},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"Outline={CAPTION_OUTLINE},"
            f"Shadow=2,"
            f"Bold=1,"
            f"Alignment=2,"
            f"MarginV=100"
        )
        sub_filter = f"subtitles=captions.srt:force_style='{sub_style}'"

        # Hook text drawtext filter
        hook_filter = ""
        if hook_text:
            safe_hook = (
                hook_text[:55]
                .replace("'", "")
                .replace(":", "")
                .replace("\\", "")
                .replace("[", "")
                .replace("]", "")
                .replace(",", "")
            )
            hook_filter = (
                f",drawtext="
                f"text='{safe_hook}':"
                f"fontsize=46:"
                f"fontcolor=white@0.95:"
                f"x=(w-tw)/2:"
                f"y=h-th-220:"
                f"enable='between(t\\,0\\,{HOOK_TEXT_DURATION})':"
                f"box=1:"
                f"boxcolor=black@0.55:"
                f"boxborderw=16"
            )

        # Combined video filter chain
        video_filter = f"{scale_filter},{sub_filter}{hook_filter}"

        # ── Build inputs list ─────────────────────────────────────────────────
        inputs = [
            "-stream_loop", "-1", "-i", "_raw_video.mp4",
            "-i", str(audio_path),
        ]
        
        audio_streams = ["[1:a]volume=1.0[narr]"]
        amix_inputs = ["[narr]"]
        
        if music_path and music_path.exists():
            inputs.extend(["-i", str(music_path)])
            idx = (len(inputs) // 2) - 1
            audio_streams.append(f"[{idx}:a]volume={MUSIC_VOLUME}[music]")
            amix_inputs.append("[music]")
            
        if sfx_path and sfx_path.exists():
            inputs.extend(["-i", str(sfx_path)])
            idx = (len(inputs) // 2) - 1
            audio_streams.append(f"[{idx}:a]volume=1.0[sfx]")
            amix_inputs.append("[sfx]")

        # ── Build filter_complex ──────────────────────────────────────────────
        filter_complex = f"[0:v]{video_filter}[vout];"
        
        if len(amix_inputs) > 1:
            # Mix multiple audio tracks together
            filter_complex += ";".join(audio_streams) + ";"
            amix_str = "".join(amix_inputs)
            filter_complex += f"{amix_str}amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=2[aout]"
            map_args = ["-map", "[vout]", "-map", "[aout]"]
        else:
            # No extra audio — simple passthrough
            map_args = ["-map", "[vout]", "-map", "1:a"]
            # remove trailing semicolon from filter_complex
            filter_complex = filter_complex.rstrip(";")

        # ── Final command ──────────────────────────────────────────────────────
        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + ["-filter_complex", filter_complex]
            + map_args
            + [
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-r", str(VIDEO_FPS),
                "-shortest",
                "-movflags", "+faststart",
                "final_short.mp4",  # relative — cwd = short_dir
            ]
        )

        log.info(f"Running ffmpeg assembly (music={'yes' if music_path else 'no'})...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            cwd=str(short_dir),  # ← key: cwd = short_dir so relative paths work
        )

        if result.returncode != 0:
            log.error(f"ffmpeg failed:\n{result.stderr[-800:]}")
            return False

        return True

    # ─── Music Picker ─────────────────────────────────────────────────────────
    @staticmethod
    def _pick_music(channel: str = None) -> Path | None:
        """
        Pick a random .mp3 from static/music/{channel}/ if provided,
        else from static/music/.
        Returns None if directory is empty (no music → silent bg).
        Place royalty-free tracks in static/music/ — YouTube Audio Library recommended.
        """
        try:
            target_dir = MUSIC_DIR
            if channel:
                channel_dir = MUSIC_DIR / channel
                if channel_dir.exists():
                    target_dir = channel_dir
                else:
                    # Fallback to root music dir if channel dir doesn't exist
                    pass
            
            tracks = list(target_dir.glob("*.mp3"))
            if tracks:
                return random.choice(tracks)
        except Exception as e:
            log.warning(f"Error picking music: {e}")
        return None
