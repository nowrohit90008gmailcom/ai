"""
config.py — Central configuration for the YouTube Content Factory.

All API keys, channel configs, paths, schedules, and constants live here.
Fill in the values marked with YOUR_* before running the system.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Load .env if present ─────────────────────────────────────────────────────
load_dotenv()

# ─── Base Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
MUSIC_DIR  = STATIC_DIR / "music"     # Drop royalty-free .mp3 tracks here

# Google Drive mount point (set by rclone)
GDRIVE_MOUNT = Path(os.getenv("GDRIVE_MOUNT", "/mnt/gdrive"))
GDRIVE_BASE = GDRIVE_MOUNT / "youtube_factory"

# ─── API Keys ────────────────────────────────────────────────────────────────
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "YOUR_CEREBRAS_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "YOUR_DEEPGRAM_KEY")
VAST_API_KEY     = os.getenv("VAST_API_KEY", "YOUR_VAST_KEY")
VAST_INSTANCE_ID = os.getenv("VAST_INSTANCE_ID", "YOUR_VAST_INSTANCE_ID")

# ─── Notification Config ──────────────────────────────────────────────────────
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS", "your_email@gmail.com")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "YOUR_APP_PASSWORD")   # App password, not login
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", "your_email@gmail.com")  # Where to send alerts
NTFY_TOPIC     = os.getenv("NTFY_TOPIC", "youtube_factory")         # ntfy.sh topic

# ─── Dashboard Auth ───────────────────────────────────────────────────────────
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "YOUR_SECURE_PASSWORD")
JWT_SECRET_KEY     = os.getenv("JWT_SECRET_KEY", "YOUR_RANDOM_JWT_SECRET_32_CHARS_MIN")
JWT_ALGORITHM      = "HS256"
JWT_EXPIRE_HOURS   = 24

# ─── Cerebras Models ──────────────────────────────────────────────────────────
# Cerebras GPT OSS 120B — runs on CS-3 wafer chip @ ~2000 tokens/sec
CEREBRAS_MODEL      = os.getenv("CEREBRAS_MODEL",      "gpt-oss-120b")
CEREBRAS_MODEL_FAST = os.getenv("CEREBRAS_MODEL_FAST", "llama3.3-70b")

# Temperature tuning per task type
CEREBRAS_TEMP_CREATIVE   = 0.88   # ideas, hooks, scripts  — higher = more variety
CEREBRAS_TEMP_STRUCTURED = 0.30   # SEO JSON, image prompts — lower = cleaner format

# Token budgets per task
CEREBRAS_MAX_TOKENS_SCRIPT  = 1000   # ~600-800 word narration script
CEREBRAS_MAX_TOKENS_SEO     = 600    # title + tags + description JSON
CEREBRAS_MAX_TOKENS_PROMPTS = 1400   # 8 image prompts at ~100 words each
CEREBRAS_MAX_TOKENS_IDEA    = 400    # idea JSON (title + hook + outline)

# ─── Channel Definitions ─────────────────────────────────────────────────────
CHANNELS = {
    "horror_crime": {
        "name": "Horror Crime Stories",
        "google_account": os.getenv("HORROR_GOOGLE_ACCOUNT", "horrorcrimestories@gmail.com"),
        "youtube_category_id": "22",   # Entertainment
        "is_kids": False,
        "post_times_est": ["21:00", "23:00"],  # 9 PM, 11 PM
        "post_times_utc": ["02:00", "04:00"],  # UTC equivalent
        "deepgram_voice": "aura-orpheus-en",
        "pitch_multiplier": None,      # No pitch shift
        "tempo": None,
        "motion_bucket_id": 40,        # Slow/creepy motion
        "clip_fps": 8,
        "clip_frames": 48,             # 6 seconds (8fps × 48 = 6s)
        "audience": "US adults aged 18-35",
        "tone": "Suspenseful, conversational, podcast-like",
        "color_theme": "#dc2626",      # Dashboard accent color
    },
    "manners_fun": {
        "name": "Learning Manners with Fun",
        "google_account": os.getenv("MANNERS_GOOGLE_ACCOUNT", "mannerslearning@gmail.com"),
        "youtube_category_id": "26",   # Howto & Style
        "is_kids": True,
        "post_times_est": ["07:00", "15:30"],  # 7 AM, 3:30 PM
        "post_times_utc": ["12:00", "20:30"],
        "deepgram_voice": "aura-luna-en",
        "pitch_multiplier": 1.30,      # +30% → sweet girl voice
        "tempo": 0.85,
        "motion_bucket_id": 100,       # Moderate motion
        "clip_fps": 8,
        "clip_frames": 40,             # 5 seconds (8fps × 40 = 5s)
        "audience": "US children aged 5-10 and parents",
        "tone": "Warm, friendly, educational, encouraging",
        "color_theme": "#16a34a",      # Dashboard accent color
    },
    "cartoon_stories": {
        "name": "Cartoon Character Stories",
        "google_account": os.getenv("CARTOON_GOOGLE_ACCOUNT", "cartoonkidstories@gmail.com"),
        "youtube_category_id": "1",    # Film & Animation
        "is_kids": True,
        "post_times_est": ["15:00", "19:00"],  # 3 PM, 7 PM
        "post_times_utc": ["20:00", "00:00"],
        "deepgram_voice": "aura-stella-en",
        "pitch_multiplier": 1.25,      # +25% → energetic kid voice
        "tempo": 0.90,
        "motion_bucket_id": 127,       # High/dynamic motion
        "clip_fps": 8,
        "clip_frames": 40,             # 5 seconds (8fps × 40 = 5s)
        "audience": "US children aged 5-10",
        "tone": "Fast-paced, fun, expressive, energetic",
        "color_theme": "#7c3aed",      # Dashboard accent color
    },
}

CHANNEL_NAMES = list(CHANNELS.keys())

# ─── Scraping Sources Per Channel ─────────────────────────────────────────────
SCRAPE_SOURCES = {
    "horror_crime": [
        "https://www.reddit.com/r/truecrime/top.json?t=week",
        "https://www.reddit.com/r/UnresolvedMysteries/top.json?t=week",
        "https://crimeonline.com/category/crime/",
        "https://www.oxygen.com/true-crime-buzz",
    ],
    "manners_fun": [
        "https://www.motherly.com/parenting/",
        "https://www.scarymommy.com/parenting/",
        "https://www.pbs.org/parents/",
        "https://www.commonsensemedia.org/",
    ],
    "cartoon_stories": [
        "https://www.gutenberg.org/browse/scores/top",
        "https://www.aesopfables.com/",
        "https://americanliterature.com/childrens-stories",
    ],
}

# ─── Video / Audio Specs ──────────────────────────────────────────────────────
VIDEO_WIDTH       = 1080
VIDEO_HEIGHT      = 1920
VIDEO_FPS         = 8
AUDIO_SAMPLE_RATE = 44100
MAX_SCENES        = 16         # Hard cap to prevent GPU explosion
TARGET_SCENE_DURATION = {
    "horror_crime": 6.0,
    "manners_fun": 4.5,
    "cartoon_stories": 4.5
}

# ─── Caption / Subtitle Settings ─────────────────────────────────────────────
CAPTION_FONT_SIZE   = 52            # px, burned into 1080×1920 video
CAPTION_FONT_COLOR  = "white"
CAPTION_OUTLINE     = 3             # outline thickness in px
CAPTION_Y_POSITION  = "(h-th)/1.15" # Near bottom of frame
HOOK_TEXT_DURATION  = 3.0           # seconds the hook text is shown
MUSIC_VOLUME        = 0.12          # 12% of full volume (keeps narration audible)
SHORTS_PER_CHANNEL_PER_MONTH = 60
TOTAL_SHORTS_PER_MONTH = 180

# ─── ComfyUI Settings (VPS 2) ─────────────────────────────────────────────────
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")

# ─── Image Generation Model (ComfyUI) ──────────────────────────────────────
# FLUX.1-schnell: 4 steps, ~20s/image on RTX 3090, top-tier quality.
# Files needed in ComfyUI/models/:
#   unet/flux1-schnell.safetensors    (download from HuggingFace black-forest-labs)
#   clip/t5xxl_fp8_e4m3fn.safetensors (T5 encoder)
#   clip/clip_l.safetensors            (CLIP-L encoder)
#   vae/ae.safetensors                 (FLUX VAE)
FLUX_UNET       = os.getenv("FLUX_UNET",  "flux1-schnell.safetensors")
FLUX_CLIP_T5    = os.getenv("FLUX_T5",    "t5xxl_fp8_e4m3fn.safetensors")
FLUX_CLIP_L     = os.getenv("FLUX_CLIP",  "clip_l.safetensors")
FLUX_VAE        = os.getenv("FLUX_VAE",   "ae.safetensors")
FLUX_GUIDANCE   = 3.5    # FluxGuidance value (3.5 = cinematic; 1.0 = creative)

# ─── Speed / Parallelism Settings ────────────────────────────────────────────
IMAGE_SAMPLER_STEPS  = 4             # FLUX.1-schnell: 4 steps is all you need
IMAGE_SAMPLER_NAME   = "euler"        # FLUX native sampler
IMAGE_SAMPLER_CFG    = 1.0           # FLUX doesn't use CFG in the traditional sense

# ─── Video Clip Model Selection ──────────────────────────────────────────────
# LTX-Video: 20-30s per clip — highly efficient cinematic and animated quality.
# LTX-Video model files needed in ComfyUI/models/checkpoints/:
#   ltx-video-2b-v0.9.1.safetensors   (HuggingFace: Lightricks/LTX-Video)

# LTX-Video model settings
LTX_MODEL      = os.getenv("LTX_MODEL", "ltx-video-2b-v0.9.1.safetensors")
LTX_NUM_FRAMES = 97     # Must be 8n+1: 97=12s@8fps, 81=10s@8fps, 65=8s@8fps
LTX_FPS        = 8      # Output FPS
LTX_STEPS      = 25     # 25 steps is fast on RTX 3090 (~20-30s total)
LTX_CFG        = 3.0    # Guidance scale for LTX-Video
LTX_RESOLUTION = (768, 1360)   # (width, height) — scaled to 1080x1920 by ffmpeg

# Submit all N ComfyUI jobs at once instead of sequential submit-wait-submit.
# ComfyUI queues internally; GPU processes them without idle gaps between jobs.
COMFYUI_BATCH_SUBMIT = True          # submit all 8 jobs before polling any
COMFYUI_POLL_WORKERS = 8             # concurrent polling threads

# ─── Parallel GPU Instances (optional — one per channel) ─────────────────────
# Set COMFYUI_URL_HORROR / _MANNERS / _CARTOON to point to 3 separate Vast.ai
# instances.  If only one GPU, all three default to COMFYUI_URL.
COMFYUI_URL_HORROR  = os.getenv("COMFYUI_URL_HORROR",  COMFYUI_URL)
COMFYUI_URL_MANNERS = os.getenv("COMFYUI_URL_MANNERS", COMFYUI_URL)
COMFYUI_URL_CARTOON = os.getenv("COMFYUI_URL_CARTOON", COMFYUI_URL)

COMFYUI_URLS = {
    "horror_crime":    COMFYUI_URL_HORROR,
    "manners_fun":     COMFYUI_URL_MANNERS,
    "cartoon_stories": COMFYUI_URL_CARTOON,
}

# Max parallel channels (1 = sequential, 3 = each channel on own GPU)
FACTORY_PARALLEL_CHANNELS = int(os.getenv("PARALLEL_CHANNELS", "1"))

# ─── Google Drive / rclone ────────────────────────────────────────────────────
RCLONE_REMOTE = "gdrive"   # Name configured in rclone config

# ─── Meta Graph API ───────────────────────────────────────────────────────────
META_API_VERSION = "v18.0"
META_CREDENTIALS = {
    "horror_crime": {
        "page_id":       os.getenv("HORROR_FB_PAGE_ID", ""),
        "ig_account_id": os.getenv("HORROR_IG_ACCOUNT_ID", ""),
        "access_token":  os.getenv("HORROR_META_TOKEN", ""),
    },
    "manners_fun": {
        "page_id":       os.getenv("MANNERS_FB_PAGE_ID", ""),
        "ig_account_id": os.getenv("MANNERS_IG_ACCOUNT_ID", ""),
        "access_token":  os.getenv("MANNERS_META_TOKEN", ""),
    },
    "cartoon_stories": {
        "page_id":       os.getenv("CARTOON_FB_PAGE_ID", ""),
        "ig_account_id": os.getenv("CARTOON_IG_ACCOUNT_ID", ""),
        "access_token":  os.getenv("CARTOON_META_TOKEN", ""),
    },
}

# ─── Deepgram Cost Tracking ───────────────────────────────────────────────────
DEEPGRAM_COST_PER_1K_CHARS = 0.0150   # $0.015 per 1000 characters

# ─── Hook Rotation Formats ────────────────────────────────────────────────────
HOOK_FORMATS = [
    "shocking_stat",
    "location_drop",
    "question_hook",
    "cliffhanger",
    "relatable_moment",
]

# ─── Retry Config ─────────────────────────────────────────────────────────────
POST_MAX_RETRIES  = 3
POST_RETRY_DELAYS = [300, 1800, 3600]   # 5min, 30min, 1hr in seconds
API_RATE_LIMIT_SLEEP = 2               # Seconds between API calls

# ─── Posting Platform Flags ───────────────────────────────────────────────────
POST_TO_YOUTUBE   = True
POST_TO_FACEBOOK  = True
POST_TO_INSTAGRAM = True

# ─── YouTube API Units Budget ─────────────────────────────────────────────────
# Each upload = ~1,600 units; 6 posts/day = 9,600 units; limit = 10,000/project
YOUTUBE_UNITS_PER_UPLOAD = 1600
YOUTUBE_DAILY_UNIT_LIMIT = 10000

# ─── Dashboard / Server ───────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
DOMAIN = os.getenv("DOMAIN", "localhost")   # Your VPS domain or IP

# ─── Rate Limiting (brute-force protection) ───────────────────────────────────
MAX_FAILED_LOGINS  = 5
LOGIN_LOCKOUT_SECS = 900  # 15 minutes
