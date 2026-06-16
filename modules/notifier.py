"""
modules/notifier.py — Email (Gmail SMTP) + push (ntfy.sh) notification system.

Events that trigger notifications:
  - Bulk run started / stage complete / complete / error
  - Post failed (immediate)
  - API quota warning
  - Daily digest (11:59 PM EST)
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import requests

from config import GMAIL_ADDRESS, GMAIL_PASSWORD, NOTIFY_EMAIL, NTFY_TOPIC
from modules.logger import get_logger

log = get_logger("notifier")


class Notifier:
    """Sends push notifications and emails."""

    # ─── ntfy.sh push notifications ──────────────────────────────────────────
    def push(self, message: str, title: str = "📺 YouTube Factory",
              priority: str = "default", tags: list[str] = None):
        """
        Send a push notification via ntfy.sh.
        Subscribe at: https://ntfy.sh/{NTFY_TOPIC}
        Or use the ntfy app on your phone.
        """
        try:
            headers = {
                "Title": title,
                "Priority": priority,
            }
            if tags:
                headers["Tags"] = ",".join(tags)

            requests.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                data=message.encode("utf-8"),
                headers=headers,
                timeout=10,
            )
            log.info(f"Push sent: {message[:60]}")
        except Exception as e:
            log.warning(f"Push notification failed: {e}")

    # ─── Gmail SMTP email ─────────────────────────────────────────────────────
    def email(self, subject: str, body: str, html: bool = False):
        """Send an email via Gmail SMTP using App Password."""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"]    = GMAIL_ADDRESS
            msg["To"]      = NOTIFY_EMAIL
            msg["Subject"] = f"[YT Factory] {subject}"

            mime_type = "html" if html else "plain"
            msg.attach(MIMEText(body, mime_type))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
                server.sendmail(GMAIL_ADDRESS, NOTIFY_EMAIL, msg.as_string())

            log.info(f"Email sent: {subject}")
        except Exception as e:
            log.error(f"Email failed: {e}")

    # ─── Convenience methods ──────────────────────────────────────────────────
    def bulk_run_started(self, month: str):
        self.push(f"🚀 Bulk run started for {month}", priority="high", tags=["rocket"])
        self.email(f"Bulk Run Started — {month}", f"Bulk generation for {month} has started.")

    def bulk_run_complete(self, month: str, summary: dict):
        msg = f"✅ Bulk run complete for {month}\n\n" + "\n".join(
            f"  {ch}: {v} videos" for ch, v in summary.items()
        )
        self.push(msg, title="✅ Bulk Run Complete", priority="high", tags=["white_check_mark"])
        self.email(f"Bulk Run Complete — {month}", msg)

    def bulk_run_error(self, stage: int, error: str):
        msg = f"❌ Bulk run error at stage {stage}: {error}"
        self.push(msg, title="❌ Bulk Run Error", priority="urgent", tags=["x"])
        self.email(f"Bulk Run Error — Stage {stage}", msg)

    def stage_complete(self, stage_name: str):
        self.push(f"✅ Stage complete: {stage_name}", tags=["white_check_mark"])

    def post_failed(self, channel: str, platform: str, day: int, error: str):
        msg = f"⚠️ POST FAILED\nChannel: {channel}\nPlatform: {platform}\nDay: {day}\nError: {error}"
        self.push(msg, title="⚠️ Post Failed", priority="urgent", tags=["warning"])
        self.email(f"Post Failed — {channel} / {platform} / Day {day}", msg)

    def post_success(self, channel: str, platform: str):
        self.push(f"✅ Posted: {channel} → {platform}", tags=["tv"])

    def daily_digest(self, stats: dict):
        ts = datetime.utcnow().strftime("%Y-%m-%d")
        lines = [f"Daily Digest — {ts}", ""]
        for ch, s in stats.items():
            lines.append(f"{ch}: {s.get('posts_today', 0)} posts, {s.get('errors', 0)} errors")
        body = "\n".join(lines)
        self.email(f"Daily Digest — {ts}", body)

    def api_quota_warning(self, service: str, used: int, limit: int):
        msg = f"⚠️ API quota warning: {service} used {used}/{limit} units"
        self.push(msg, priority="high", tags=["warning"])
        self.email(f"API Quota Warning — {service}", msg)
