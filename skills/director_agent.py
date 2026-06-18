"""
skills/director_agent.py — AI "Cinematographer" that upgrades image prompts.

WHAT IT DOES
────────────
Instead of asking Cerebras for 8 generic scene prompts, the Director Agent:

1. Reads the full script and plans a proper STORYBOARD — assigning each of
   the 8 scenes a specific SHOT TYPE and LIGHTING SETUP.
2. Maintains CHARACTER CONTINUITY — if scene 1 establishes "a man in a red
   jacket," every subsequent prompt with that character will say the same.
3. Injects those cinematography details into the existing prompts, making
   the AI images far more varied and professional.

SHOT TYPES USED
───────────────
- EXTREME_CLOSE_UP  : Object/face detail, high tension
- CLOSE_UP          : Emotional reaction, intimacy
- MEDIUM_SHOT       : Standard narrative shot
- WIDE_SHOT         : Establishing environment
- AERIAL            : Drone-style overview, location reveal
- LOW_ANGLE         : Villain/power shot, intimidating
- HIGH_ANGLE        : Victim/vulnerability shot
- POV               : First-person immersion
"""

import json
import re
from config import CEREBRAS_MODEL
from modules.cerebras_client import CerebrasWrapper
from modules.logger import get_logger

log = get_logger("director_agent")

# ─── Storyboard Planning Prompt ───────────────────────────────────────────────

STORYBOARD_PROMPT = """\
You are an expert film director planning a YouTube Shorts storyboard.

CHANNEL: {channel}
VISUAL STYLE: {style}

SCRIPT:
\"\"\"{script}\"\"\"

Plan exactly {n} shots for this script. For each shot assign:
1. shot_type: one of [EXTREME_CLOSE_UP, CLOSE_UP, MEDIUM_SHOT, WIDE_SHOT, AERIAL, LOW_ANGLE, HIGH_ANGLE, POV]
2. lighting: a specific lighting description (e.g. "harsh cold blue moonlight", "warm afternoon sunlight", "red and blue police light strobes")
3. subject: what the camera focuses on
4. mood_modifier: 2-3 cinematic adjectives (e.g. "ominous, desolate, tense")

Rules:
- NO two consecutive shots should have the same shot_type
- Vary between tight (close) and wide shots to create rhythm
- Lighting must MATCH the emotional beat of that moment in the script
- For character shots, always describe: age, clothing, hair colour consistently

Return ONLY a valid JSON array of {n} objects:
[
  {{"shot_type": "WIDE_SHOT", "lighting": "...", "subject": "...", "mood_modifier": "..."}},
  ...
]"""

# ─── Shot-type → ComfyUI Modifiers ───────────────────────────────────────────

SHOT_MODIFIERS = {
    "EXTREME_CLOSE_UP": "extreme close-up macro shot, tight framing, shallow depth of field",
    "CLOSE_UP":         "close-up shot, face or object fills frame, bokeh background",
    "MEDIUM_SHOT":      "medium shot, waist-up framing, standard cinematic composition",
    "WIDE_SHOT":        "wide establishing shot, full environment visible, epic scale",
    "AERIAL":           "aerial drone shot, bird's eye view, sweeping perspective",
    "LOW_ANGLE":        "low angle shot, camera looking up, imposing and powerful",
    "HIGH_ANGLE":       "high angle shot, camera looking down, vulnerable perspective",
    "POV":              "first-person POV shot, immersive handheld camera feel",
}

# ─── Channel-specific style bases ────────────────────────────────────────────

CHANNEL_STYLES = {
    "horror_crime": (
        "dark cinematic horror-documentary photography, desaturated colours, "
        "film grain, harsh shadows, realistic"
    ),
    "manners_fun": (
        "bright cheerful Pixar-quality 3D cartoon illustration, soft pastel "
        "volumetric lighting, child-friendly, warm colours"
    ),
    "cartoon_stories": (
        "bold colourful Cartoon Network / comic book style animation, "
        "high contrast, dynamic lines, energetic"
    ),
}


class DirectorAgent:
    """
    Plans a cinematography-aware storyboard and upgrades raw image prompts
    with shot-type, lighting and continuity information.
    """

    def __init__(self):
        self.client = CerebrasWrapper()

    def upgrade_prompts(self, channel: str, script: str,
                        raw_prompts: list[str]) -> list[str]:
        """
        Takes the existing raw_prompts (from Cerebras or fallback templates)
        and enhances each one with director-level cinematography data.

        Returns upgraded prompts of the same length.
        Always returns something — worst case, the original raw_prompts.
        """
        if not raw_prompts:
            return raw_prompts

        n = len(raw_prompts)
        try:
            storyboard = self._plan_storyboard(channel, script, n)
            if not storyboard or len(storyboard) != n:
                log.warning(f"[{channel}] Storyboard length mismatch — using raw prompts")
                return raw_prompts

            upgraded = []
            for i, (raw, shot) in enumerate(zip(raw_prompts, storyboard)):
                enhanced = self._enhance_prompt(raw, shot, channel)
                log.info(
                    f"[{channel}] Scene {i+1}: "
                    f"{shot.get('shot_type','?')} | {shot.get('lighting','')[:50]}"
                )
                upgraded.append(enhanced)

            log.info(f"[{channel}] DirectorAgent upgraded {n} prompts ✅")
            return upgraded

        except Exception as e:
            log.warning(f"[{channel}] DirectorAgent failed ({e}) — using raw prompts")
            return raw_prompts

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _plan_storyboard(self, channel: str, script: str, n: int) -> list[dict]:
        """Ask Cerebras to plan n shots with specific cinematography."""
        style = CHANNEL_STYLES.get(channel, "cinematic professional photography")
        prompt = STORYBOARD_PROMPT.format(
            channel=channel,
            style=style,
            script=script[:800],
            n=n,
        )
        raw = self.client.generate_completion(
            model=CEREBRAS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=1.0,
            retries=3,
        )
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        return json.loads(match.group())

    def _enhance_prompt(self, raw_prompt: str, shot: dict, channel: str) -> str:
        """Inject shot_type, lighting and mood into a raw prompt string."""
        shot_type    = shot.get("shot_type", "MEDIUM_SHOT")
        lighting     = shot.get("lighting", "natural cinematic lighting")
        mood         = shot.get("mood_modifier", "cinematic, professional")
        subject      = shot.get("subject", "")
        shot_mod     = SHOT_MODIFIERS.get(shot_type, "medium shot")
        style_base   = CHANNEL_STYLES.get(channel, "cinematic photography")

        # Build the enhanced prompt:
        # [Original description] + [Shot modifier] + [Lighting] + [Mood] + [Style base]
        parts = [
            raw_prompt.rstrip(".,"),
            shot_mod,
            f"lighting: {lighting}",
            mood,
            style_base,
            "masterpiece, 4K, vertical 9:16 smartphone composition",
        ]
        return ", ".join(p.strip() for p in parts if p.strip())
