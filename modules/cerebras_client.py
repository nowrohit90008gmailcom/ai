"""
modules/cerebras_client.py — Centralized Cerebras API wrapper with:
  1. Multiple API key round-robin rotation
  2. Exponential backoff retry logic (up to 5 retries)
  3. Reasoning model support (gpt-oss-120b / zai-glm-4.7)
     — These models return a 'reasoning_content' field which we strip
       from the final output, keeping only the clean user-facing response.
"""

import time
from config import CEREBRAS_API_KEYS, CEREBRAS_MODEL
from modules.logger import get_logger

log = get_logger("cerebras_client")

# Reasoning models (gpt-oss-120b / zai-glm-4.7) require temperature=1.0.
# Setting temperature < 1.0 causes them to silently return empty content.
# We detect them by name and always override temperature to 1.0.
REASONING_MODELS = {"gpt-oss-120b", "zai-glm-4.7"}
MIN_REASONING_TEMP = 1.0  # Do not go below this for reasoning models


class CerebrasWrapper:
    """
    A wrapper around the Cerebras client that handles:
      1. Multiple API keys with round-robin rotation
      2. Exponential backoff and retry logic (up to 5 retries)
      3. Reasoning model response extraction (strips chain-of-thought)

    --- HOW TO USE MULTIPLE API KEYS ---
    In your .env file, separate keys with commas:
        CEREBRAS_API_KEY=key1,key2,key3

    The wrapper will automatically distribute requests across all keys,
    and rotate to the next key immediately on rate-limit (429) errors.
    """

    def __init__(self):
        self.keys = CEREBRAS_API_KEYS
        self.current_key_idx = 0
        self.clients = []

        try:
            from cerebras.cloud.sdk import Cerebras
            for key in self.keys:
                stripped = key.strip()
                if stripped and "YOUR_" not in stripped:
                    self.clients.append(Cerebras(api_key=stripped))
            if self.clients:
                log.info(f"CerebrasWrapper: {len(self.clients)} API key(s) loaded.")
            else:
                log.warning("CerebrasWrapper: No valid API keys found — running in mock mode.")
        except ImportError:
            log.warning("cerebras-cloud-sdk not installed — using mock mode")
            self.clients = []

    def _rotate_key(self):
        """Round-robins to the next available API key."""
        if len(self.clients) < 2:
            return
        old_idx = self.current_key_idx
        self.current_key_idx = (self.current_key_idx + 1) % len(self.clients)
        log.info(f"Rotating Cerebras API key: key#{old_idx} → key#{self.current_key_idx}")

    @staticmethod
    def _extract_content(response) -> str:
        """
        Safely extracts the final user-facing text from the response.

        For reasoning models (gpt-oss-120b / zai-glm-4.7):
          - The model does internal chain-of-thought thinking
          - The final answer is in message.content
          - BUT some Cerebras SDK versions return it in reasoning_content
            and leave content empty — so we fall back to reasoning_content
            if content is empty.
        """
        msg = response.choices[0].message
        content = (msg.content or "").strip()

        # Fallback: reasoning models sometimes put output in reasoning_content
        if not content:
            reasoning = getattr(msg, "reasoning_content", None) or ""
            content = reasoning.strip()
            if content:
                log.debug("Used reasoning_content fallback (content was empty)")

        return content

    def generate_completion(
        self,
        model: str,
        messages: list,
        max_tokens: int,
        temperature: float,
        retries: int = 5,
    ) -> str:
        """
        Executes a chat completion request with:
          - Built-in retry loop (default 5 attempts)
          - Automatic key rotation on rate-limit / auth errors
          - Exponential backoff: 2, 4, 8, 16 seconds between retries
          - Reasoning model response extraction

        Returns the text content string.
        Raises the last exception if all retries fail.
        """
        if not self.clients:
            log.warning("No Cerebras clients available — returning mock response.")
            return '{"angle":"Mock angle","hook_type":"cliffhanger","hook_preview":"This is a mock idea"}'

        last_exception = None
        is_reasoning = model in REASONING_MODELS

        # Reasoning models REQUIRE temperature >= 1.0.
        # Values below 1.0 cause them to silently return empty content.
        if is_reasoning and temperature < MIN_REASONING_TEMP:
            log.debug(
                f"[{model}] Reasoning model detected — clamping temperature "
                f"{temperature} → {MIN_REASONING_TEMP}"
            )
            temperature = MIN_REASONING_TEMP

        for attempt in range(1, retries + 1):
            client = self.clients[self.current_key_idx]
            try:
                kwargs = dict(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                response = client.chat.completions.create(**kwargs)
                content = self._extract_content(response)

                if is_reasoning:
                    log.debug(f"[{model}] Reasoning model — extracted final answer ({len(content)} chars)")

                return content

            except Exception as e:
                last_exception = e
                err_str = str(e).lower()
                log.warning(f"Cerebras API error on attempt {attempt}/{retries}: {e}")

                # Rotate key immediately on rate-limit or auth errors
                if "429" in err_str or "rate limit" in err_str or "401" in err_str or "auth" in err_str:
                    self._rotate_key()

                if attempt < retries:
                    sleep_time = 2 ** attempt  # 2, 4, 8, 16 seconds
                    log.info(f"Retrying in {sleep_time}s (attempt {attempt}/{retries})...")
                    time.sleep(sleep_time)
                else:
                    log.error(f"Exhausted all {retries} retries for Cerebras API. Last error: {e}")

        if last_exception:
            raise last_exception
        return ""
