import time
import json
from config import CEREBRAS_API_KEYS
from modules.logger import get_logger

log = get_logger("cerebras_client")

class CerebrasWrapper:
    """
    A wrapper around the Cerebras client that handles:
      1. Multiple API keys with round-robin rotation
      2. Exponential backoff and retry logic (up to 5 retries)
    """
    
    def __init__(self):
        self.keys = CEREBRAS_API_KEYS
        self.current_key_idx = 0
        self.clients = []
        
        try:
            from cerebras.cloud.sdk import Cerebras
            for key in self.keys:
                if "YOUR_" not in key:
                    self.clients.append(Cerebras(api_key=key))
        except ImportError:
            log.warning("cerebras-cloud-sdk not installed — using mock mode")
            self.clients = []
            
    def _rotate_key(self):
        """Rotates to the next available API key."""
        if not self.clients:
            return
        old_idx = self.current_key_idx
        self.current_key_idx = (self.current_key_idx + 1) % len(self.clients)
        log.info(f"Rotating Cerebras API key (index {old_idx} -> {self.current_key_idx})")

    def generate_completion(self, model: str, messages: list, max_tokens: int, temperature: float, retries: int = 5) -> str:
        """
        Executes a chat completion request with built-in retries and key rotation.
        """
        if not self.clients:
            log.warning("No Cerebras clients available. Returning mock response.")
            return '{"angle":"Mock angle","hook_type":"cliffhanger","hook_preview":"This is a mock idea"}'
            
        last_exception = None
        
        for attempt in range(1, retries + 1):
            client = self.clients[self.current_key_idx]
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                last_exception = e
                err_msg = str(e).lower()
                log.warning(f"Cerebras API error on attempt {attempt}/{retries}: {e}")
                
                # If we have multiple keys and it's a rate limit or auth error, rotate immediately
                if len(self.clients) > 1 and ("429" in err_msg or "rate limit" in err_msg or "auth" in err_msg or "401" in err_msg):
                    self._rotate_key()
                
                if attempt < retries:
                    sleep_time = 2 ** attempt  # 2, 4, 8, 16 seconds
                    log.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    log.error("Exhausted all retries for Cerebras API.")
                    
        raise last_exception
