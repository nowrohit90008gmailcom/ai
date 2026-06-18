"""
modules/caption_generator.py — Generate SRT subtitle files for burned-in captions.

Strategy:
  1. Call Deepgram STT on the generated audio to get accurate word-level timestamps.
  2. If Deepgram STT fails (quota/network), fall back to character-count proportional
     estimation (accurate enough for short-form narration).

SRT groups words into subtitle "cards" of 4-6 words each.
The .srt file is then burned into the video by ffmpeg's subtitles filter.
"""

import json
import re
import subprocess
from pathlib import Path

import requests

from config import DEEPGRAM_API_KEY
from modules.logger import get_logger

log = get_logger("caption_generator")

DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"
WORDS_PER_CARD = 1       # words per subtitle card (word-by-word style)
MIN_CARD_DUR   = 0.1     # seconds minimum per card


class CaptionGenerator:
    """Generates SRT subtitle files from audio + script."""

    def generate_srt(self, script: str, audio_path: str, srt_path: str) -> bool:
        """
        Main entry point. Writes SRT to srt_path.
        Returns True on success.
        """
        try:
            words = self._deepgram_word_timestamps(audio_path)
            if words:
                srt = self._words_to_srt(words)
                log.info(f"Captions: {len(words)} words via Deepgram STT")
            else:
                srt = self._estimated_srt(script, audio_path)
                log.info("Captions: using character-estimate fallback")

            Path(srt_path).write_text(srt, encoding="utf-8")
            return True
        except Exception as e:
            log.error(f"Caption generation failed: {e}")
            # Write a minimal SRT so assembly doesn't fail
            Path(srt_path).write_text("1\n00:00:00,000 --> 00:00:60,000\n \n", encoding="utf-8")
            return False

    # ─── Deepgram STT ─────────────────────────────────────────────────────────
    def _deepgram_word_timestamps(self, audio_path: str) -> list[dict]:
        """
        Send audio to Deepgram pre-recorded transcription.
        Returns list of word dicts: {word, start, end}
        """
        if not DEEPGRAM_API_KEY or "YOUR_" in DEEPGRAM_API_KEY:
            return []

        try:
            with open(audio_path, "rb") as f:
                audio_data = f.read()

            response = requests.post(
                DEEPGRAM_LISTEN_URL,
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/mp3",
                },
                params={
                    "model": "nova-2",
                    "language": "en-US",
                    "punctuate": "true",
                    "words": "true",
                },
                data=audio_data,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            words = (
                data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("words", [])
            )
            return words
        except Exception as e:
            log.warning(f"Deepgram STT failed: {e}")
            return []

    # ─── Words → SRT ──────────────────────────────────────────────────────────
    def _words_to_srt(self, words: list[dict]) -> str:
        """Convert Deepgram word list into SRT format, grouping into cards."""
        if not words:
            return ""

        cards = []
        i = 0
        while i < len(words):
            chunk = words[i: i + WORDS_PER_CARD]
            start = chunk[0]["start"]
            end   = chunk[-1]["end"]
            if end - start < MIN_CARD_DUR:
                end = start + MIN_CARD_DUR
            text  = " ".join(w["word"] for w in chunk)
            cards.append((start, end, text))
            i += WORDS_PER_CARD

        return self._cards_to_srt(cards)

    # ─── Character-Count Estimate Fallback ────────────────────────────────────
    def _estimated_srt(self, script: str, audio_path: str) -> str:
        """
        Estimate per-word timestamps from total audio duration.
        Total duration obtained via ffprobe.
        """
        total_dur = self._get_audio_duration(audio_path)
        if total_dur <= 0:
            total_dur = len(script.split()) / 2.5  # fallback: 2.5 words/sec

        words = script.split()
        if not words:
            return ""

        dur_per_word = total_dur / len(words)
        cards = []
        i = 0
        while i < len(words):
            chunk = words[i: i + WORDS_PER_CARD]
            start = i * dur_per_word
            end   = start + len(chunk) * dur_per_word
            end   = max(end, start + MIN_CARD_DUR)
            text  = " ".join(chunk)
            # Clean punctuation that breaks drawtext escaping
            text  = re.sub(r"[\"\\]", "", text)
            cards.append((start, end, text))
            i += WORDS_PER_CARD

        return self._cards_to_srt(cards)

    # ─── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _cards_to_srt(cards: list[tuple]) -> str:
        """Convert list of (start, end, text) tuples to SRT string."""
        lines = []
        for idx, (start, end, text) in enumerate(cards, 1):
            lines.append(str(idx))
            lines.append(f"{_fmt_srt(start)} --> {_fmt_srt(end)}")
            lines.append(text.upper())   # upper-case captions read better on screen
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        """Get audio duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "json",
                    audio_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception:
            return 0.0


def _fmt_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    hours   = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs    = int(seconds % 60)
    millis  = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
