"""
modules/auth_manager.py — OAuth token management for 3 YouTube accounts + Meta.

Each channel has its own Google Cloud project and OAuth credentials.
Tokens are stored as pickle files in config/credentials/<channel>/token.pickle
and auto-refresh when expired.
"""

import os
import pickle
from pathlib import Path

from config import CREDENTIALS_DIR, CHANNELS
from modules.logger import get_logger

log = get_logger("auth_manager")

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class AuthManager:
    """Manages OAuth tokens for all 3 YouTube channels."""

    def get_youtube_service(self, channel: str):
        """
        Returns an authenticated YouTube API service for the given channel.
        Uses stored token if valid; triggers OAuth flow if needed.
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_path = CREDENTIALS_DIR / channel / "token.pickle"
        secrets_path = CREDENTIALS_DIR / channel / "client_secrets.json"
        creds = None

        # Load existing token
        if token_path.exists():
            with open(token_path, "rb") as f:
                creds = pickle.load(f)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(token_path, creds)
                log.info(f"[{channel}] Token refreshed")
            except Exception as e:
                log.error(f"[{channel}] Token refresh failed: {e}")
                creds = None

        # Full OAuth flow (requires browser — run once locally)
        if not creds or not creds.valid:
            if not secrets_path.exists():
                raise FileNotFoundError(
                    f"Missing client_secrets.json for {channel}. "
                    f"Download from Google Cloud Console → {secrets_path}"
                )
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets_path), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0)
            self._save_token(token_path, creds)
            log.info(f"[{channel}] New token saved")

        return build("youtube", "v3", credentials=creds)

    def is_connected(self, channel: str) -> bool:
        """Check if a valid token exists for this channel."""
        token_path = CREDENTIALS_DIR / channel / "token.pickle"
        if not token_path.exists():
            return False
        try:
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
            return creds and (creds.valid or creds.refresh_token)
        except Exception:
            return False

    def revoke_token(self, channel: str):
        """Delete stored token for a channel."""
        token_path = CREDENTIALS_DIR / channel / "token.pickle"
        if token_path.exists():
            token_path.unlink()
            log.info(f"[{channel}] Token revoked")

    @staticmethod
    def _save_token(path: Path, creds):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(creds, f)
