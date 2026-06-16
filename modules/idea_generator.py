"""
modules/idea_generator.py — Turn scraped stories into refined video ideas using Cerebras.

Takes raw scraped story data and generates a structured video concept
with the best angle, hook type, and key elements to highlight.
"""

import time
from config import (
    CEREBRAS_API_KEY, CEREBRAS_MODEL,
    CEREBRAS_TEMP_STRUCTURED, CEREBRAS_MAX_TOKENS_IDEA,
    CHANNELS, API_RATE_LIMIT_SLEEP,
)
from modules.logger import get_logger

log = get_logger("idea_generator")

IDEA_PROMPTS = {
    "horror_crime": """You are a viral true crime content strategist for YouTube Shorts.

Given this raw story data, extract the BEST angle for a 60-second Short aimed at US adults 18-35.

Story: {story_text}

Return a JSON object with:
{{
  "angle": "The most shocking/intriguing angle to take",
  "hook_type": "shocking_stat|location_drop|question_hook|cliffhanger|relatable_moment",
  "hook_preview": "First 1-2 sentences that would stop someone scrolling",
  "key_facts": ["fact1", "fact2", "fact3"],
  "emotional_core": "What emotion drives this story (dread/curiosity/outrage)",
  "us_location": "City, State if applicable",
  "year": "Year of incident if applicable"
}}

Return ONLY the JSON, no explanation.""",

    "manners_fun": """You are a kids educational content strategist for YouTube Shorts.

Given this parenting/education topic, find the BEST angle for a fun 60-second Short for US kids 5-10.

Topic: {story_text}

Return a JSON object with:
{{
  "lesson": "The specific manner or social skill to teach",
  "scenario": "Relatable US school/home situation to illustrate it",
  "hook_type": "question_hook|relatable_moment|shocking_stat",
  "hook_preview": "Fun question or situation that opens the video",
  "age_group": "5-7|8-10|5-10",
  "fun_element": "A rhyme, game, or repetition kids can remember",
  "positive_message": "The uplifting takeaway"
}}

Return ONLY the JSON, no explanation.""",

    "cartoon_stories": """You are a kids cartoon content strategist for YouTube Shorts.

Given this story/fable, adapt it for a fun 60-second animated Short for US kids 5-10.

Story: {story_text}

Return a JSON object with:
{{
  "character_name": "A fun cartoon character name (not copyrighted)",
  "character_type": "animal|kid|robot|creature",
  "problem": "The challenge or conflict",
  "solution": "How the character solves it (creatively)",
  "moral": "The lesson in one simple sentence",
  "hook_type": "question_hook|cliffhanger|relatable_moment",
  "hook_preview": "Exciting opening that would excite kids",
  "action_words": ["Zoom!", "Bam!", "Whoosh!"]
}}

Return ONLY the JSON, no explanation.""",
}


class IdeaGenerator:
    """Uses Cerebras to refine scraped stories into structured video ideas."""

    def __init__(self):
        try:
            from cerebras.cloud.sdk import Cerebras
            self.client = Cerebras(api_key=CEREBRAS_API_KEY)
        except ImportError:
            log.warning("cerebras-cloud-sdk not installed — using mock mode")
            self.client = None

    def generate(self, channel: str, story: dict) -> dict:
        """Generate a refined video idea from a scraped story."""
        story_text = f"{story.get('title', '')}. {story.get('summary', '')}"
        prompt = IDEA_PROMPTS[channel].format(story_text=story_text)

        response_text = self._call_cerebras(prompt)
        try:
            import json
            idea = json.loads(response_text)
            idea["raw_story"] = story
            idea["channel"] = channel
            log.info(f"[{channel}] Idea: {idea.get('hook_preview', '')[:60]}")
            return idea
        except Exception as e:
            log.error(f"[{channel}] Failed to parse idea JSON: {e}")
            return {"error": str(e), "raw_story": story, "channel": channel}

    def generate_batch(self, channel: str, stories: list[dict]) -> list[dict]:
        """Generate ideas for a list of stories."""
        ideas = []
        for i, story in enumerate(stories):
            idea = self.generate(channel, story)
            ideas.append(idea)
            log.info(f"[{channel}] Ideas: {i + 1}/{len(stories)}")
            time.sleep(API_RATE_LIMIT_SLEEP)
        return ideas

    def _call_cerebras(self, prompt: str, max_tokens: int = None) -> str:
        if self.client is None:
            return '{"angle":"Mock angle","hook_type":"cliffhanger","hook_preview":"This is a mock idea"}'
        response = self.client.chat.completions.create(
            model=CEREBRAS_MODEL,                           # cbsgpt-120b
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or CEREBRAS_MAX_TOKENS_IDEA,
            temperature=CEREBRAS_TEMP_STRUCTURED,           # 0.30 — clean JSON output
        )
        return response.choices[0].message.content.strip()
