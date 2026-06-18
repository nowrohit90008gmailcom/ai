"""
modules/seo_generator.py — YouTube SEO metadata generation using Cerebras.

Generates 3 title variants, a 150-200 word description, 20 tags,
and 5 hashtags per video — all US-audience optimized.
"""

import json
import time
from config import (
    CEREBRAS_MODEL,
    CEREBRAS_MODEL_FAST,
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
- STRICTLY STICK TO THE SCRIPT: All titles and descriptions must be based ONLY on details explicitly mentioned in the provided script. Do NOT hallucinate, fabricate, or introduce any external facts, organizations (such as the "FBI", "CIA", or specific police departments), locations, numbers, or claims unless they are directly stated in the script.

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
            # Strip markdown code blocks
            cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")

            # Strategy 1: Try to find a full valid JSON object (greedy match to get outermost {})
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    seo = json.loads(match.group())
                    seo["tags"] = (seo.get("tags", []) + [""] * 20)[:20]
                    seo["hashtags"] = (seo.get("hashtags", []) + ["#Shorts"])[:5]
                    if "#Shorts" not in seo["hashtags"]:
                        seo["hashtags"][4] = "#Shorts"
                    log.info(f"[{channel}] SEO: {seo.get('title_clickbait', '')[:50]}")
                    return seo
                except json.JSONDecodeError:
                    pass  # JSON truncated — fall through to partial recovery

            # Strategy 2: Partial JSON recovery — extract individual fields with regex
            log.warning(f"[{channel}] SEO JSON truncated — running partial field recovery")
            seo = self._recover_partial_seo(cleaned, channel)
            log.info(f"[{channel}] SEO recovered: {seo.get('title_clickbait', '')[:50]}")
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
        # Reasoning models need temperature=1.0 and extra tokens for chain-of-thought
        effective_temp = max(CEREBRAS_TEMP_STRUCTURED, 1.0)
        try:
            return self.client.generate_completion(
                model=CEREBRAS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=CEREBRAS_MAX_TOKENS_SEO,
                temperature=effective_temp,
                retries=5
            )
        except Exception:
            # Secondary fallback: try the fast model
            try:
                log.warning("[seo] Primary model failed — trying fast model fallback")
                return self.client.generate_completion(
                    model=CEREBRAS_MODEL_FAST,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=CEREBRAS_MAX_TOKENS_SEO,
                    temperature=1.0,
                    retries=3
                )
            except Exception:
                return json.dumps(self._fallback_seo("fallback"))

    @staticmethod
    def _recover_partial_seo(text: str, channel: str) -> dict:
        """Extract SEO fields from truncated/partial JSON using regex per-field."""
        import re
        def extract_str(key):
            m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', text)
            return m.group(1) if m else ""
        def extract_list(key):
            m = re.search(rf'"{key}"\s*:\s*\[([^\]]*)', text, re.DOTALL)
            if not m:
                return []
            items = re.findall(r'"([^"]+)"', m.group(1))
            return items

        ch_fallback = SEOGenerator._fallback_seo(channel)
        seo = {
            "title_clickbait": extract_str("title_clickbait") or ch_fallback["title_clickbait"],
            "title_clear":     extract_str("title_clear")     or ch_fallback["title_clear"],
            "title_question":  extract_str("title_question")  or ch_fallback["title_question"],
            "description":     extract_str("description")     or ch_fallback["description"],
            "tags":            extract_list("tags")            or ch_fallback["tags"],
            "hashtags":        extract_list("hashtags")        or ch_fallback["hashtags"],
        }
        seo["tags"] = (seo["tags"] + [""] * 20)[:20]
        seo["hashtags"] = (seo["hashtags"] + ["#Shorts"])[:5]
        if "#Shorts" not in seo["hashtags"]:
            seo["hashtags"][4] = "#Shorts"
        return seo

    @staticmethod
    def _fallback_seo(channel: str) -> dict:
        ch_tags = {
            "horror_crime": ["true crime","horror","crime story","usa","american crime","mystery","cold case","unsolved","criminal","detective","fbi","police","crime scene","thriller","scary","real crime","documentary","viral","shorts","youtube shorts"],
            "manners_fun":   ["kids","parenting","manners","children","learning","toddlers","preschool","family","education","fun for kids","parenting tips","child development","kindness","sharing","school","mom","dad","babies","shorts","youtube shorts"],
            "cartoon_stories":["cartoon","kids stories","bedtime stories","fairy tales","animation","children","storytime","fable","moral story","short story","funny cartoon","adventure","animals","magic","friendship","princess","dragon","shorts","youtube shorts","family"],
        }
        ch_hashtags = {
            "horror_crime":    ["#Shorts","#TrueCrime","#Horror","#Crime","#Mystery"],
            "manners_fun":     ["#Shorts","#KidsVideo","#Parenting","#Learning","#Children"],
            "cartoon_stories": ["#Shorts","#CartoonStories","#KidsStories","#BedtimeStory","#Animation"],
        }
        default_tags = ch_tags.get(channel, ch_tags["horror_crime"])
        default_hashtags = ch_hashtags.get(channel, ch_hashtags["horror_crime"])
        return {
            "title_clickbait": "You Won't Believe What Happened Next",
            "title_clear": "Amazing Story You Need to Hear",
            "title_question": "What Really Happened?",
            "description": "A compelling story you need to hear. Follow for more amazing content every day.",
            "tags": default_tags,
            "hashtags": default_hashtags,
        }
