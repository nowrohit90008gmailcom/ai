"""
skills/pacing_editor.py — Rewrites scripts for maximum retention.

WHAT IT DOES
────────────
After the main script is written, this skill applies three
evidence-based retention techniques:

1. OPEN LOOP INJECTION — Inserts an unanswered question right before
   the 50% mark. This exploits the "Zeigarnik effect": people feel
   psychologically compelled to finish content with open questions.
   Example: "But here's what nobody is talking about..."

2. PATTERN INTERRUPT — Injects a one-sentence "pattern break" around
   the 30% mark to re-engage viewers whose attention may be drifting.
   Example: "Wait. There's something you need to know."

3. PAUSE OPTIMISATION — Ensures every sentence that ends with "..."
   or "—" is on its own line so the voice generator produces better
   natural pauses (the ffmpeg tempo processing respects line breaks
   in the Deepgram TTS output).

The editor outputs the improved script text directly.
It falls back to the original script if anything goes wrong.
"""

import re
from config import CEREBRAS_MODEL
from modules.cerebras_client import CerebrasWrapper
from modules.logger import get_logger

log = get_logger("pacing_editor")

PACING_PROMPT = """\
You are an expert YouTube Shorts editor specialising in viewer retention.

CHANNEL TYPE: {channel}
TARGET AUDIENCE: {audience}

ORIGINAL SCRIPT:
\"\"\"{script}\"\"\"

Apply these THREE retention techniques to rewrite the script:

1. OPEN LOOP: Around the 50% mark, add ONE sentence that creates an \
irresistible open loop (unanswered question or shocking tease). \
Examples: "But nobody knew what was coming next...", \
"And that's when things got really strange..."

2. PATTERN INTERRUPT: Around the 30% mark, add ONE very short sentence \
that snaps the viewer back to attention. \
Examples: "Wait.", "Here's the thing.", "Listen carefully."

3. PAUSE MARKS: Every sentence that would benefit from a dramatic pause \
should end with "..." or "—". Add these where they're missing but natural.

4. Keep the CTA (last sentence) EXACTLY as-is.
5. Do NOT add more than 15% extra words — keep it tight.
6. Return ONLY the improved script text. No labels, no explanation, no markdown.
"""

CHANNEL_AUDIENCES = {
    "horror_crime":    "US adults aged 18-35, true crime podcast fans",
    "manners_fun":     "US children aged 5-10 and their parents",
    "cartoon_stories": "US children aged 5-10",
}


class PacingEditor:
    """
    Post-processes a generated script to maximise viewer retention
    using open loops, pattern interrupts and pause optimisation.
    """

    def __init__(self):
        self.client = CerebrasWrapper()

    def improve(self, channel: str, script: str) -> str:
        """
        Takes a raw script and returns a retention-optimised version.
        Always returns something — worst case, the original script.
        """
        if not script or len(script.split()) < 50:
            return script  # too short to edit

        try:
            improved = self._call_cerebras(channel, script)
            if not improved or len(improved.split()) < 30:
                log.warning(f"[{channel}] PacingEditor returned empty — keeping original")
                return script

            # Safety: strip any labels the model might have added
            improved = re.sub(
                r"\[HOOK\]|\[STORY\]|\[PUNCHLINE\]|\[CTA\]|\[LESSON\]|\[MORAL\]",
                "", improved
            ).strip()

            orig_words = len(script.split())
            new_words  = len(improved.split())
            log.info(
                f"[{channel}] PacingEditor: {orig_words} → {new_words} words "
                f"({new_words - orig_words:+d})"
            )
            return improved

        except Exception as e:
            log.warning(f"[{channel}] PacingEditor failed ({e}) — keeping original script")
            return script

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _call_cerebras(self, channel: str, script: str) -> str:
        audience = CHANNEL_AUDIENCES.get(channel, "general audience")
        prompt   = PACING_PROMPT.format(
            channel  = channel,
            audience = audience,
            script   = script,
        )
        return self.client.generate_completion(
            model      = CEREBRAS_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 2000,
            temperature= 1.0,
            retries    = 3,
        )
