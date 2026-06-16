"""
cron_setup.py — Auto-installs all posting cron jobs on VPS 1.

Run once after deployment:  python cron_setup.py

Installs 6 cron jobs (one per post slot):
  - Manners Short 1:  7:00 AM EST  = 12:00 UTC
  - Cartoon Short 1:  3:00 PM EST  = 20:00 UTC
  - Manners Short 2:  3:30 PM EST  = 20:30 UTC
  - Cartoon Short 2:  7:00 PM EST  = 00:00 UTC (next day)
  - Horror Short 1:   9:00 PM EST  = 02:00 UTC
  - Horror Short 2:  11:00 PM EST  = 04:00 UTC

NOTE: Times above are for Eastern Standard Time (EST = UTC-5).
      During Eastern Daylight Time (EDT = UTC-4), adjust by -1 hour.
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
PYTHON   = sys.executable
POST_PY  = str(BASE_DIR / "post.py")
LOG_DIR  = str(BASE_DIR / "data" / "logs")

# Format: (minute, hour_utc, channel, short_num, description)
CRON_JOBS = [
    (0,  12, "manners_fun",      1, "Manners Short 1  — 7:00 AM EST"),
    (0,  20, "cartoon_stories",  1, "Cartoon Short 1  — 3:00 PM EST"),
    (30, 20, "manners_fun",      2, "Manners Short 2  — 3:30 PM EST"),
    (0,  0,  "cartoon_stories",  2, "Cartoon Short 2  — 7:00 PM EST"),
    (0,  2,  "horror_crime",     1, "Horror Short 1   — 9:00 PM EST"),
    (0,  4,  "horror_crime",     2, "Horror Short 2   — 11:00 PM EST"),
]

# Also add a daily analytics update at 11:00 PM UTC
ANALYTICS_CRON = (0, 23, "Analytics daily update at 11 PM UTC")


def build_cron_line(minute: int, hour: int, channel: str, short_num: int, desc: str) -> str:
    log_file = f"{LOG_DIR}/cron_{channel}_s{short_num}.log"
    cmd = f"{PYTHON} {POST_PY} --channel {channel} --short {short_num}"
    return (
        f"# {desc}\n"
        f"{minute} {hour} * * * {cmd} >> {log_file} 2>&1"
    )


def install_crons():
    # Get existing crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    # Remove any existing YouTube factory lines
    lines = [l for l in existing.splitlines()
             if "post.py" not in l and "YouTube factory" not in l]

    # Add new jobs
    lines.append("\n# ── YouTube Content Factory Posting Jobs ─────────────────────────────")
    for minute, hour, channel, short_num, desc in CRON_JOBS:
        lines.append(build_cron_line(minute, hour, channel, short_num, desc))

    # Analytics cron
    lines.append(
        f"\n# {ANALYTICS_CRON[2]}\n"
        f"0 23 * * * {PYTHON} {str(BASE_DIR / 'modules' / 'performance_tracker.py')} "
        f">> {LOG_DIR}/analytics.log 2>&1"
    )

    new_crontab = "\n".join(lines) + "\n"

    # Install
    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode == 0:
        print("✅ Cron jobs installed successfully!")
        print("\nInstalled jobs:")
        for _, hour, ch, s, desc in CRON_JOBS:
            print(f"  {desc} → python post.py --channel {ch} --short {s}")
    else:
        print(f"❌ Cron install failed: {proc.stderr}")
        sys.exit(1)


def verify_crons():
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    print("Current crontab:")
    print(result.stdout)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="Show current crontab")
    args = parser.parse_args()

    if args.verify:
        verify_crons()
    else:
        install_crons()
