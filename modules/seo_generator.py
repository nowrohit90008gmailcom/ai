"""
modules/seo_generator.py — YouTube SEO metadata generation using Cerebras.

Generates 3 title variants, a 150-200 word description, 20 tags,
and 5 hashtags per video — all US-audience optimized.
"""

import json
import time
from config import (
    CEREBRAS_MODEL,
    CEREBRAS_TEMP_STRUCTURED, CEREBRAS_MAX_TOKENS_SEO,
    CHANNELS, API_RATE_LIMIT_SLEEP,
)
from modules.cerebras_client import CerebrasWrapper
from modules.logger import get_logger

log = get_logger("seo_generator")

SEO_PROMPT = """Generate YouTube SEO metadata for this Shorts video.

Channel: {channel_name}
Target audience: {audience}
Script:
{script}

Return ONLY a valid JSON object with these exact fields:
{{
  "title_clickbait": "...",
  "title_clear": "...",
  "title_question": "...",
  "description": "...",
  "tags": ["tag1", "tag2", "tag3"],
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"]
}}

Rules:
- All 3 titles: max 60 characters, no clickbait emojis in title_clear
- title_clickbait: shocking, curiosity-driven
- title_clear: descriptive, keyword-rich
- title_question: ends with a question mark
- description: 150-200 words, SEO optimized, US-focused, include keywords naturally
- tags: exactly 20 tags, mix of broad and specific US-trending terms
- hashtags: exactly 5, include #Shorts and channel-specific tags

Return ONLY the JSON object. No markdown, no explanation."""


class SEOGenerator:
    """Generates YouTube SEO packages using Cerebras."""

    def __init__(self):
        self.client = CerebrasWrapper()

    def generate(self, channel: str, script: str) -> dict:
        """Generate full SEO package for a script."""
        ch_cfg = CHANNELS[channel]
        prompt = SEO_PROMPT.format(
            channel_name=ch_cfg["name"],
            audience=ch_cfg["audience"],
            script=script[:600],
        )
        raw = self._call_cerebras(prompt)
        log.debug(f"[{channel}] Raw SEO response: {raw[:300]}")
        try:
            import re
            # Strip markdown code blocks and extract JSON object
            cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise ValueError("No JSON object found in SEO response")
            seo = json.loads(match.group())
            # Enforce tag/hashtag counts
            seo["tags"] = (seo.get("tags", []) + [""] * 20)[:20]
            seo["hashtags"] = (seo.get("hashtags", []) + ["#Shorts"])[:5]
            if "#Shorts" not in seo["hashtags"]:
                seo["hashtags"][4] = "#Shorts"
            log.info(f"[{channel}] SEO: {seo.get('title_clickbait', '')[:50]}")
            return seo
        except Exception as e:
            log.error(f"[{channel}] SEO parse error: {e} | raw: {raw[:200]}")
            return self._fallback_seo(channel)

    def generate_batch(self, channel: str, scripts: list[str]) -> list[dict]:
        results = []
        for i, script in enumerate(scripts):
            seo = self.generate(channel, script)
            results.append(seo)
            log.info(f"[{channel}] SEO packages: {i + 1}/{len(scripts)}")
            time.sleep(API_RATE_LIMIT_SLEEP)
        return results

    def _call_cerebras(self, prompt: str) -> str:
        try:
            return self.client.generate_completion(
                model=CEREBRAS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=CEREBRAS_MAX_TOKENS_SEO,
                temperature=CEREBRAS_TEMP_STRUCTURED,
                retries=5
            )
        except Exception:
            return json.dumps(self._fallback_seo("horror_crime"))

    @staticmethod
    def _fallback_seo(channel: str) -> dict:
        return {
            "title_clickbait": "You Won't Believe What Happened Next",
            "title_clear": "True Crime Story from the United States",
            "title_question": "What Really Happened That Night?",
            "description": "A compelling story you need to hear. Follow for more amazing content.",
            "tags": [
                "true crime", "shorts", "youtube shorts", "horror", "crime story",
                "usa", "american crime", "mystery", "cold case", "unsolved",
                "criminal", "detective", "fbi", "police", "crime scene",
                "thriller", "scary", "real crime", "documentary", "viral"
            ],
            "hashtags": ["#Shorts", "#TrueCrime", "#Horror", "#Crime", "#Mystery"],
        }
