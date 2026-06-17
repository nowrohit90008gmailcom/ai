"""
modules/script_generator.py — Full YouTube Shorts script generation using Cerebras.

Generates 80–130 word scripts in the [HOOK][STORY][PUNCHLINE][CTA] format,
tailored per channel style and voice.
"""

import time
from config import (
    CEREBRAS_MODEL,
    CEREBRAS_TEMP_CREATIVE, CEREBRAS_MAX_TOKENS_SCRIPT,
    CHANNELS, API_RATE_LIMIT_SLEEP,
)
from modules.cerebras_client import CerebrasWrapper
from modules.logger import get_logger

log = get_logger("script_generator")

SCRIPT_PROMPTS = {
    "horror_crime": """Write a YouTube Shorts horror crime script for a US adult audience aged 18-35.

Story data: {story_text}
Angle: {angle}
Hook type: {hook_type}

Requirements:
- Total length: 140-260 words (target around 180 words for a 60-second short)
- Format: [HOOK] [STORY] [PUNCHLINE] [CTA]
- Hook: First sentence must create instant dread or curiosity using: {hook_preview}
- Reference real American locations, FBI/local PD, US legal terms where applicable
- Tone: Suspenseful, conversational, like a true crime podcast
- Pacing: Short punchy sentences. Dramatic pauses implied with "..."
- End with a shocking revelation or unanswered question
- CTA: "Follow for more true crime stories"

Return ONLY the script text. No labels, no explanation, no markdown.""",

    "manners_fun": """Write a YouTube Shorts educational script for US children aged 5-10 and their parents.

Topic: {story_text}
Lesson: {angle}
Hook: {hook_preview}

Requirements:
- Total length: 140-260 words (target around 180 words for a 60-second short)
- Format: [HOOK] [STORY] [PUNCHLINE] [CTA]
- Hook: Fun question or relatable situation
- Use simple vocabulary (grade 1-3 reading level)
- Include ONE fun rhyme or repetition kids can remember
- Align with US kindergarten social skills standards
- Tone: Warm, friendly, encouraging — NEVER scolding
- End with the lesson clearly stated in one simple sentence
- CTA: "Follow to learn more fun manners!"

Return ONLY the script text. No labels, no explanation, no markdown.""",

    "cartoon_stories": """Write a YouTube Shorts cartoon story script for US children aged 5-10.

Character: {angle}
Story: {story_text}
Hook: {hook_preview}

Requirements:
- Total length: 140-260 words (target around 180 words for a 60-second short)
- Format: [HOOK] [STORY] [PUNCHLINE] [CTA]
- Hook: Exciting action or funny situation in first sentence
- Use American humor, relatable school/home settings
- Include action words: Zoom! Bam! Whoosh! Pop! at dramatic moments
- Always end with a clear moral lesson (one sentence)
- Tone: Maximum fun, silly, expressive
- CTA: "Follow for more cartoon stories!"

Return ONLY the script text. No labels, no explanation, no markdown.""",
}


class ScriptGenerator:
    """Generates per-channel scripts using Cerebras."""

    def __init__(self):
        self.client = CerebrasWrapper()

    def generate(self, channel: str, idea: dict) -> str:
        """Generate a script from a structured idea."""
        story = idea.get("raw_story", {})
        story_text = f"{story.get('title', '')}. {story.get('summary', '')}"

        prompt = SCRIPT_PROMPTS[channel].format(
            story_text=story_text[:800],
            angle=idea.get("angle", idea.get("lesson", idea.get("character_name", ""))),
            hook_type=idea.get("hook_type", "cliffhanger"),
            hook_preview=idea.get("hook_preview", ""),
        )

        script = self._call_cerebras(prompt)  # uses CEREBRAS_MAX_TOKENS_SCRIPT from config
        log.debug(f"[{channel}] Raw script response: {repr(script[:200])}")
        word_count = len(script.split())
        log.info(f"[{channel}] Script generated ({word_count} words): {script[:60]}...")
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
            retries=5
        )
