"""
modules/voice_generator.py — Deepgram TTS + ffmpeg pitch shift for all 3 channels.

Voices:
  horror_crime    → aura-orpheus-en (deep male, no transform)
  manners_fun     → aura-luna-en    (female, +30% pitch → sweet girl)
  cartoon_stories → aura-stella-en  (female, +25% pitch → energetic kid)
"""

import subprocess
import os
from pathlib import Path

import requests

from config import DEEPGRAM_API_KEY, CHANNELS, AUDIO_SAMPLE_RATE
from modules.logger import get_logger

log = get_logger("voice_generator")

DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"


class VoiceGenerator:
    """Generates voiceover audio files using Deepgram TTS + ffmpeg pitch transform."""

    def generate_voice(self, text: str, channel: str, output_path: str) -> bool:
        """
        Full pipeline: Deepgram TTS → optional ffmpeg pitch shift → output MP3.
        Returns True on success.
        """
        cfg = CHANNELS[channel]
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        raw_path = output.with_name(output.stem + "_raw.mp3")

        # Guard: Deepgram returns 400 if text is empty
        if not text or not text.strip():
            log.error(f"[{channel}] Empty script text — skipping voice generation")
            return False

        # Step 1 — Deepgram TTS
        success = self._deepgram_tts(text, cfg["deepgram_voice"], str(raw_path))
        if not success:
            return False

        # Step 2 — Optional pitch/tempo transform
        pitch = cfg.get("pitch_multiplier")
        tempo = cfg.get("tempo")

        if pitch and tempo:
            # Full transform: pitch shift + tempo adjust (manners_fun, cartoon_stories)
            success = self._pitch_shift(
                str(raw_path), output_path,
                pitch=pitch,
                tempo=tempo,
            )
        elif tempo:
            # Tempo only: just slow down without pitch change (horror_crime)
            success = self._tempo_only(str(raw_path), output_path, tempo=tempo)
        else:
            # No transform — copy straight through
            import shutil
            shutil.copy(str(raw_path), output_path)
            success = True

        # Cleanup raw file
        if raw_path.exists():
            raw_path.unlink()

        if success:
            log.info(f"[{channel}] Voice ready: {output_path}")
        return success

    def _deepgram_tts(self, text: str, voice: str, output_path: str) -> bool:
        """Call Deepgram TTS API and save raw MP3."""
        try:
            response = requests.post(
                DEEPGRAM_TTS_URL,
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "application/json",
                },
                params={
                    "model": voice,
                    "encoding": "mp3",
                },
                json={
                    "text": text,
                },
                timeout=60,
            )
            response.raise_for_status()
            Path(output_path).write_bytes(response.content)
            log.info(f"Deepgram TTS complete: {len(response.content) // 1024}KB")
            return True
        except Exception as e:
            log.error(f"Deepgram TTS failed: {e}")
            return False

    @staticmethod
    def _pitch_shift(input_path: str, output_path: str, pitch: float, tempo: float) -> bool:
        """
        Apply pitch shift using ffmpeg asetrate + aresample + atempo filter chain.
        pitch=1.30 → +30% pitch  |  tempo=0.85 → 15% slower (preserves length after pitch)
        """
        rate = int(AUDIO_SAMPLE_RATE * pitch)
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", input_path,
                    "-af", f"asetrate={rate},aresample={AUDIO_SAMPLE_RATE},atempo={tempo}",
                    output_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                log.error(f"ffmpeg pitch shift failed: {result.stderr[-300:]}")
                return False
            return True
        except Exception as e:
            log.error(f"ffmpeg pitch shift exception: {e}")
            return False

    @staticmethod
    def _tempo_only(input_path: str, output_path: str, tempo: float) -> bool:
        """
        Slow down audio using ffmpeg atempo without any pitch change.
        tempo=0.78 → 22% slower (natural pacing for horror/crime narration).
        Note: atempo range is [0.5, 2.0]. Values below 0.5 require chained filters.
        """
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", input_path,
                    "-af", f"atempo={tempo}",
                    output_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                log.error(f"ffmpeg tempo-only failed: {result.stderr[-300:]}")
                return False
            return True
        except Exception as e:
            log.error(f"ffmpeg tempo-only exception: {e}")
            return False

    def estimate_duration_seconds(self, text: str) -> float:
        """Estimate audio duration from word count (avg ~2.5 words/sec for narration)."""
        words = len(text.split())
        return words / 2.5

    def estimate_cost_usd(self, text: str) -> float:
        """Estimate Deepgram cost based on character count."""
        from config import DEEPGRAM_COST_PER_1K_CHARS
        chars = len(text)
        return (chars / 1000) * DEEPGRAM_COST_PER_1K_CHARS
