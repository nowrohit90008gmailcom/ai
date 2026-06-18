"""
modules/script_generator.py — Full YouTube Shorts script generation using Cerebras.

Generates 140-260 word scripts in the narrative format,
tailored per channel style and voice.

SKILLS PIPELINE (runs before / after main generation):
  1. HookSpecialist  — generates 3 competing hooks, picks the best one
  2. ScriptGenerator — writes the full script around the winning hook
  3. PacingEditor    — injects open loops + pattern interrupts for retention
"""

import re
import time
from config import (
    CEREBRAS_MODEL,
    CEREBRAS_TEMP_CREATIVE, CEREBRAS_MAX_TOKENS_SCRIPT,
    CHANNELS, API_RATE_LIMIT_SLEEP,
)
from modules.cerebras_client import CerebrasWrapper
from modules.logger import get_logger
from skills.hook_specialist import HookSpecialist
from skills.pacing_editor import PacingEditor

log = get_logger("script_generator")

SCRIPT_PROMPTS = {
    "horror_crime": """Write a YouTube Shorts horror crime script for a US adult audience aged 18-35.

Story data: {story_text}
Angle: {angle}
Hook type: {hook_type}

Requirements:
- Total length: 140-260 words (target around 180 words for a 60-second short)
- Hook: Open with EXACTLY this sentence: {hook_preview}
- Reference real American locations, FBI/local PD, US legal terms where applicable
- Tone: Suspenseful, conversational, like a true crime podcast
- Pacing: CRITICAL - You MUST use frequent ellipses (...) and em-dashes (—) to force natural speaking pauses.
- Write short, punchy sentences with breathing room between thoughts.
- End with a shocking revelation or unanswered question
- CTA: "Follow for more true crime stories"

Return ONLY the script text. No labels, no explanation, no markdown.""",

    "manners_fun": """Write a YouTube Shorts educational script for US children aged 5-10 and their parents.

Topic: {story_text}
Lesson: {angle}

Requirements:
- Total length: 140-260 words (target around 180 words for a 60-second short)
- Hook: Open with EXACTLY this sentence: {hook_preview}
- Use simple vocabulary (grade 1-3 reading level)
- Include ONE fun rhyme or repetition kids can remember
- Align with US kindergarten social skills standards
- Tone: Warm, friendly, encouraging — NEVER scolding
- Pacing: CRITICAL - You MUST use frequent ellipses (...) and em-dashes (—) to force natural speaking pauses.
- Write short sentences with breathing room between thoughts so kids can follow along.
- End with the lesson clearly stated in one simple sentence
- CTA: "Follow to learn more fun manners!"

Return ONLY the script text. No labels, no explanation, no markdown.""",

    "cartoon_stories": """Write a YouTube Shorts cartoon story script for US children aged 5-10.

Character: {angle}
Story: {story_text}

Requirements:
- Total length: 140-260 words (target around 180 words for a 60-second short)
- Hook: Open with EXACTLY this sentence: {hook_preview}
- Use American humor, relatable school/home settings
- Include action words: Zoom! Bam! Whoosh! Pop! at dramatic moments
- Always end with a clear moral lesson (one sentence)
- Tone: Maximum fun, silly, expressive
- Pacing: CRITICAL - You MUST use frequent ellipses (...) and em-dashes (—) to force natural speaking pauses.
- Write short sentences with breathing room between thoughts.
- CTA: "Follow for more cartoon stories!"

Return ONLY the script text. No labels, no explanation, no markdown.""",
}


class ScriptGenerator:
    """Generates per-channel scripts using Cerebras + the 3-stage Skills pipeline."""

    def __init__(self):
        self.client       = CerebrasWrapper()
        self.hook_skill   = HookSpecialist()
        self.pacing_skill = PacingEditor()

    def generate(self, channel: str, idea: dict) -> str:
        """
        Full 3-stage skills pipeline:
          Stage A — HookSpecialist generates 3 competing hooks and picks the best
          Stage B — Main script is written using the winning hook as the opener
          Stage C — PacingEditor injects open loops + pattern interrupts
        """
        story = idea.get("raw_story", {})
        story_text = f"{story.get('title', '')}. {story.get('summary', '')}"

        # ── Stage A: Hook Competition ─────────────────────────────────────────
        log.info(f"[{channel}] 🎣 Running HookSpecialist...")
        best_hook = self.hook_skill.get_best_hook(channel, idea)

        # ── Stage B: Script Generation ────────────────────────────────────────
        prompt = SCRIPT_PROMPTS[channel].format(
            story_text=story_text[:800],
            angle=idea.get("angle", idea.get("lesson", idea.get("character_name", ""))),
            hook_type=idea.get("hook_type", "cliffhanger"),
            hook_preview=best_hook,
        )
        script = self._call_cerebras(prompt)

        # Strip structural labels that the model sometimes adds
        script = re.sub(
            r"\[HOOK\]|\[STORY\]|\[PUNCHLINE\]|\[CTA\]|\[LESSON\]|\[MORAL\]",
            "", script
        ).strip()
        script = re.sub(r"\n{3,}", "\n\n", script)

        # ── Stage C: Pacing Edit ──────────────────────────────────────────────
        log.info(f"[{channel}] ✍️  Running PacingEditor...")
        script = self.pacing_skill.improve(channel, script)

        word_count = len(script.split())
        log.info(f"[{channel}] ✅ Script ready ({word_count} words): {script[:60]}...")
        return script

    def generate_batch(self, channel: str, ideas: list[dict]) -> list[str]:
        scripts = []
        for i, idea in enumerate(ideas):
            script = self.generate(channel, idea)
            scripts.append(script)
            log.info(f"[{channel}] Scripts: {i + 1}/{len(ideas)}")
            time.sleep(API_RATE_LIMIT_SLEEP)
        return scripts

    def _call_cerebras(self, prompt: str, max_tokens: int = None) -> str:
        return self.client.generate_completion(
            model=CEREBRAS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or CEREBRAS_MAX_TOKENS_SCRIPT,
            temperature=CEREBRAS_TEMP_CREATIVE,
            retries=5,
        )
