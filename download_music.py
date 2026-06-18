import subprocess
import sys
from pathlib import Path

# Resolve path relative to this script so it works on both local and VPS
BASE_DIR = Path(__file__).parent
MUSIC_DIR = BASE_DIR / "static" / "music"

CHANNELS = {
    "horror_crime": "ytsearch1:dark ambient no copyright music",
    "manners_fun": "ytsearch1:upbeat background music no copyright",
    "cartoon_stories": "ytsearch1:whimsical fantasy background music no copyright"
}

def download():
    # Ensure yt-dlp is installed
    try:
        import yt_dlp
    except ImportError:
        print("yt-dlp is not installed. Installing now...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
        
    for channel, query in CHANNELS.items():
        out_path = MUSIC_DIR / channel / "%(title)s.%(ext)s"
        # Ensure channel directory exists
        (MUSIC_DIR / channel).mkdir(parents=True, exist_ok=True)
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "128K",
            "-o", str(out_path),
            query
        ]
        print(f"\n🎵 Downloading track for {channel}...")
        subprocess.run(cmd)

if __name__ == "__main__":
    download()
    print("\n✅ All background music downloaded successfully to static/music!")
