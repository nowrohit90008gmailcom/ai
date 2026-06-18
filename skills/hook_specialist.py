"""
skills/hook_specialist.py — Generates 3 competing hooks, scores them and
returns the single best one for the given channel and story.

HOW IT WORKS
────────────
1. Receives the story summary + channel.
2. Asks Cerebras to generate exactly 3 different hooks (different hook types).
3. Asks Cerebras to score each hook 1-10 on scroll-stop potential.
4. Returns the top-scoring hook text.

This replaces the old single-shot approach where the script generator
just used whatever hook the model happened to produce first.
The winning hook is then injected into the main script prompt so the
full script is written AROUND the best possible opening line.
"""

import json
import re
from config import CEREBRAS_MODEL, CEREBRAS_MAX_TOKENS_IDEA
from modules.cerebras_client import CerebrasWrapper
from modules.logger import get_logger

log = get_logger("hook_specialist")

# ─── Hook Generation Prompt ───────────────────────────────────────────────────

HOOK_GEN_PROMPT = {
    "horror_crime": """\
You are the world's best true crime YouTube Shorts hook writer.
Your only job: craft 3 completely DIFFERENT hook sentences for this story.
Each hook must stop a scrolling viewer dead in their tracks in under 2 seconds.

Story: {story_text}
Angle: {angle}

Write exactly 3 hooks. Each must use a DIFFERENT hook type from:
- LOCATION_DROP: Start with a creepy American town/address
- SHOCKING_STAT: Open with a disturbing number or fact
- CLIFFHANGER: Start mid-action, sentence cut off with "..."
- QUESTION_HOOK: Direct question to viewer
- IDENTITY_REVEAL: "Nobody knew that [person]..."

Return ONLY a valid JSON array of exactly 3 strings. No explanation:
["hook 1 here", "hook 2 here", "hook 3 here"]""",

    "manners_fun": """\
You are the world's best kids' YouTube Shorts hook writer.
Your only job: craft 3 completely DIFFERENT hook sentences for this topic.
Each hook must make a US child aged 5-10 instantly curious or laugh.

Topic: {story_text}
Lesson: {angle}

Write exactly 3 hooks. Each must use a DIFFERENT hook type:
- FUNNY_QUESTION: A silly relatable question kids love
- RELATABLE_MOMENT: "Has this ever happened to you...?"
- SURPRISE_FACT: Something surprising about everyday life
- CHALLENGE_HOOK: "Can you do THIS better than your friends?"
- STORY_START: Jump straight into a fun mini-situation

Return ONLY a valid JSON array of exactly 3 strings. No explanation:
["hook 1 here", "hook 2 here", "hook 3 here"]""",

    "cartoon_stories": """\
You are the world's best kids' cartoon YouTube Shorts hook writer.
Your only job: craft 3 completely DIFFERENT hook sentences for this story.
Each hook must make a US child aged 5-10 instantly excited.

Character: {angle}
Story: {story_text}

Write exactly 3 hooks. Each must use a DIFFERENT hook type:
- ACTION_OPEN: Start mid-action: "Zoom! {character} was flying when..."
- MYSTERY_OPEN: "Nobody knew what was hiding inside the..."
- FUNNY_PROBLEM: Start with a hilarious problem
- EXCLAMATION: "OH NO! {character} just..."
- QUESTION: Ask the viewer a fun question about the character

Return ONLY a valid JSON array of exactly 3 strings. No explanation:
["hook 1 here", "hook 2 here", "hook 3 here"]""",
}

# ─── Hook Scoring Prompt ──────────────────────────────────────────────────────

HOOK_SCORE_PROMPT = """\
You are a YouTube Shorts retention expert.
Score each hook below from 1-10 for its ability to STOP a scrolling viewer.

Scoring criteria:
- 9-10: Irresistible, creates instant dread/curiosity/excitement, viewer MUST keep watching
- 7-8: Strong hook, most viewers stop
- 5-6: Decent but generic, some viewers scroll past
- 1-4: Weak, most viewers scroll past

Channel type: {channel}
Hooks to score:
1. {hook1}
2. {hook2}
3. {hook3}

Return ONLY a valid JSON object:
{{"scores": [score1, score2, score3], "best_index": 0_or_1_or_2, "reason": "one sentence why"}}"""


class HookSpecialist:
    """
    Generates 3 competing hooks, scores them, and returns the best one.
    Falls back to the original hook_preview from the idea if anything fails.
    """

    def __init__(self):
        self.client = CerebrasWrapper()

    def get_best_hook(self, channel: str, idea: dict) -> str:
        """
        Main entry point. Returns the single best hook string.
        Always returns something — worst case the original hook_preview.
        """
        story = idea.get("raw_story", {})
        story_text = f"{story.get('title', '')}. {story.get('summary', '')}"
        angle = idea.get("angle", idea.get("lesson", idea.get("character_name", "")))
        fallback = idea.get("hook_preview", story.get("title", ""))

        try:
            hooks = self._generate_hooks(channel, story_text, angle)
            if not hooks or len(hooks) < 2:
                log.warning(f"[{channel}] Hook generation returned <2 hooks — using fallback")
                return fallback

            best = self._score_and_pick(channel, hooks)
            log.info(f"[{channel}] 🎣 Best hook selected: {best[:80]}...")
            return best

        except Exception as e:
            log.warning(f"[{channel}] HookSpecialist failed ({e}) — using fallback hook")
            return fallback

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _generate_hooks(self, channel: str, story_text: str, angle: str) -> list[str]:
        """Ask Cerebras to generate 3 hooks and parse the JSON array."""
        prompt = HOOK_GEN_PROMPT[channel].format(
            story_text=story_text[:600],
            angle=angle[:200],
            character=angle[:80],   # for cartoon_stories template
        )
        raw = self.client.generate_completion(
            model=CEREBRAS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=1.0,
            retries=3,
        )
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        hooks = json.loads(match.group())
        return [h.strip() for h in hooks if isinstance(h, str) and h.strip()]

    def _score_and_pick(self, channel: str, hooks: list[str]) -> str:
        """Score all hooks and return the best one."""
        # Pad to 3 if fewer were returned
        while len(hooks) < 3:
            hooks.append(hooks[-1])

        prompt = HOOK_SCORE_PROMPT.format(
            channel=channel,
            hook1=hooks[0],
            hook2=hooks[1],
            hook3=hooks[2],
        )
        raw = self.client.generate_completion(
            model=CEREBRAS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=1.0,
            retries=3,
        )
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return hooks[0]  # default to first if scoring fails
        result = json.loads(match.group())
        best_idx = int(result.get("best_index", 0))
        best_idx = max(0, min(best_idx, len(hooks) - 1))
        reason = result.get("reason", "")
        log.info(f"Hook scores: {result.get('scores', [])} — picked #{best_idx} ({reason})")
        return hooks[best_idx]
