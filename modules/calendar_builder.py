"""
modules/calendar_builder.py — EST posting schedule calculator.

Builds the complete posting calendar for a month, assigning each of the
60 shorts per channel to a day + time slot in EST.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from config import CHANNELS, CHANNEL_NAMES

EST = ZoneInfo("America/New_York")
UTC = timezone.utc


class CalendarBuilder:
    """Builds and queries the posting schedule for a given month."""

    def build_month_schedule(self, year: int, month: int) -> list[dict]:
        """
        Returns a flat list of all posting slots for the month.
        Each entry: {channel, day, short_num, time_est, time_utc, video_path_template}
        """
        days_in_month = self._days_in_month(year, month)
        schedule = []
        short_counters = {ch: 1 for ch in CHANNEL_NAMES}

        for day in range(1, days_in_month + 1):
            for ch, cfg in sorted(CHANNELS.items(),
                                   key=lambda x: x[1]["post_times_est"][0]):
                for time_est_str in cfg["post_times_est"]:
                    h, m = map(int, time_est_str.split(":"))
                    dt_est = datetime(year, month, day, h, m, 0, tzinfo=EST)
                    dt_utc = dt_est.astimezone(UTC)
                    short_num = short_counters[ch]
                    short_counters[ch] += 1

                    schedule.append({
                        "channel": ch,
                        "channel_name": cfg["name"],
                        "day": day,
                        "short_num": short_num,
                        "time_est": time_est_str,
                        "time_utc": dt_utc.strftime("%H:%M"),
                        "datetime_utc": dt_utc.isoformat(),
                        "cron_utc": f"{dt_utc.minute} {dt_utc.hour} * * *",
                    })

        return schedule

    def get_todays_posts(self) -> list[dict]:
        """Return today's posting schedule."""
        now = datetime.now(EST)
        schedule = self.build_month_schedule(now.year, now.month)
        return [s for s in schedule if s["day"] == now.day]

    def get_next_post(self) -> dict | None:
        """Return the next upcoming post."""
        now = datetime.now(UTC)
        schedule = self.build_month_schedule(now.year, now.month)
        future = [
            s for s in schedule
            if datetime.fromisoformat(s["datetime_utc"]) > now
        ]
        return future[0] if future else None

    def video_path(self, month: str, channel: str, day: int, short_num: int) -> str:
        """
        Returns the Google Drive path for a specific video.
        short_num here = short index within the day (1 or 2), not global.
        """
        from config import GDRIVE_BASE
        return str(
            GDRIVE_BASE /
            f"month_{month}" /
            channel /
            f"day_{day:02d}_short_{short_num:02d}" /
            "final_short.mp4"
        )

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        if month == 12:
            return (date(year + 1, 1, 1) - date(year, 12, 1)).days
        return (date(year, month + 1, 1) - date(year, month, 1)).days
