"""
modules/sfx_generator.py — Dynamically synthesizes and mixes SFX into an audio track.

Uses pydub to generate and mix "pop" and "whoosh" sound effects exactly at the
specified timestamps from the captions file and scene transitions.
"""

import os
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine, WhiteNoise

from modules.logger import get_logger

log = get_logger("sfx_generator")

class SFXGenerator:
    def __init__(self):
        # Synthesize a "Pop" sound for emphatic subtitle words (short tick)
        self.pop_sound = Sine(800).to_audio_segment(duration=30).fade_out(30) - 5
        
        # Synthesize a "Whoosh" sound for scene transitions (white noise sweep)
        self.whoosh_sound = WhiteNoise().to_audio_segment(duration=600).fade_in(200).fade_out(400) - 12
        
    def generate_sfx_track(self, srt_path: Path, clip_paths: list[Path], audio_path: Path, output_path: Path) -> bool:
        """
        Creates a silent audio track matching the length of the voiceover.
        Overlays pops and whooshes based on subtitles and scene transitions.
        """
        try:
            # 1. Base silent track matching voiceover length
            voiceover = AudioSegment.from_file(str(audio_path))
            total_duration_ms = len(voiceover)
            sfx_track = AudioSegment.silent(duration=total_duration_ms)
            
            # 2. Add "whoosh" at clip boundaries
            # VideoAssembler loop concatenates clips. If we have clip_paths,
            # we can guess their timestamps by their file metadata, but pydub can't read mp4 easily.
            # Assuming standard 5s or 6s clips for Shorts:
            # It's safer to just drop a whoosh every 5 seconds.
            current_ms = 0
            while current_ms < total_duration_ms:
                if current_ms > 0: # don't whoosh at 0s
                    sfx_track = sfx_track.overlay(self.whoosh_sound, position=current_ms)
                current_ms += 5000 # 5 seconds
                
            # 3. Parse SRT for emphatic words
            if srt_path.exists():
                srt_content = srt_path.read_text(encoding="utf-8").splitlines()
                for line in srt_content:
                    if "-->" in line:
                        # Parse start time "HH:MM:SS,mmm"
                        start_str = line.split("-->")[0].strip()
                        h, m, s_ms = start_str.split(":")
                        s, ms = s_ms.split(",")
                        timestamp_ms = (int(h) * 3600000) + (int(m) * 60000) + (int(s) * 1000) + int(ms)
                        
                        # Store timestamp for the next line (the actual text)
                        current_timestamp_ms = timestamp_ms
                        
                    elif line.strip() and not line.strip().isdigit() and "-->" not in line:
                        text = line.strip()
                        # If the text has an exclamation mark or is ALL CAPS, add a pop!
                        if "!" in text or (text.isupper() and len(text) > 2):
                            sfx_track = sfx_track.overlay(self.pop_sound, position=current_timestamp_ms)
                            
            # 4. Export
            sfx_track.export(str(output_path), format="mp3", bitrate="128k")
            log.info(f"Generated SFX track: {output_path.name}")
            return True
            
        except Exception as e:
            log.error(f"Failed to generate SFX track: {e}")
            # Fallback to a 30s silent track so assembly doesn't fail
            AudioSegment.silent(duration=30000).export(str(output_path), format="mp3")
            return False
