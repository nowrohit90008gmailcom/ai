#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# install_deps.sh — Install all Python dependencies for the YouTube Factory
#
# Run in the project directory:
#   chmod +x scripts/install_deps.sh && ./scripts/install_deps.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PYTHON="${PYTHON:-python3.11}"
VENV_DIR="${VENV_DIR:-./venv}"

echo "📦 YouTube Content Factory — Dependency Installer"
echo "=================================================="

# ─── 1. Create virtual environment if needed ─────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creating virtual environment..."
    $PYTHON -m venv $VENV_DIR
fi

# ─── 2. Activate ─────────────────────────────────────────────────────────────
source $VENV_DIR/bin/activate
echo "✅ Using Python: $(python --version)"

# ─── 3. Upgrade pip ──────────────────────────────────────────────────────────
pip install --upgrade pip setuptools wheel

# ─── 4. Install Python packages ──────────────────────────────────────────────
echo "📚 Installing Python packages from requirements.txt..."
pip install -r requirements.txt

# ─── 5. Install Playwright browsers ──────────────────────────────────────────
echo "🌐 Installing Playwright Chromium browser..."
playwright install chromium
playwright install-deps chromium

# ─── 6. Check ffmpeg ─────────────────────────────────────────────────────────
echo "🎬 Checking ffmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "⚠️  ffmpeg not found. Install with:"
    echo "     Ubuntu: sudo apt install ffmpeg"
    echo "     macOS:  brew install ffmpeg"
fi

# ─── 7. Check rclone ─────────────────────────────────────────────────────────
echo "☁️  Checking rclone..."
if command -v rclone &> /dev/null; then
    echo "✅ rclone: $(rclone version | head -1)"
else
    echo "⚠️  rclone not found. Install with:"
    echo "     curl https://rclone.org/install.sh | sudo bash"
fi

# ─── 8. Create .env template if not present ──────────────────────────────────
if [ ! -f ".env" ]; then
    echo "📝 Creating .env template..."
    cat > .env << 'ENV_EOF'
# YouTube Content Factory — Environment Variables
# Fill in all values before running the system.

# ─── API Keys ─────────────────────────────────────────────────────────────────
CEREBRAS_API_KEY=your_cerebras_api_key_here
DEEPGRAM_API_KEY=your_deepgram_api_key_here
VAST_API_KEY=your_vast_api_key_here
VAST_INSTANCE_ID=your_vast_instance_id_here

# ─── Dashboard Auth ───────────────────────────────────────────────────────────
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_password
JWT_SECRET_KEY=generate_a_random_32_char_string_here

# ─── Notifications ────────────────────────────────────────────────────────────
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_PASSWORD=your_gmail_app_password
NOTIFY_EMAIL=your_email@gmail.com
NTFY_TOPIC=youtube_factory_YOUR_NAME

# ─── Google Drive ────────────────────────────────────────────────────────────
GDRIVE_MOUNT=/mnt/gdrive

# ─── Channel Google Accounts ─────────────────────────────────────────────────
HORROR_GOOGLE_ACCOUNT=horrorcrimestories@gmail.com
MANNERS_GOOGLE_ACCOUNT=mannerslearning@gmail.com
CARTOON_GOOGLE_ACCOUNT=cartoonkidstories@gmail.com

# ─── Meta API ────────────────────────────────────────────────────────────────
HORROR_FB_PAGE_ID=
HORROR_IG_ACCOUNT_ID=
HORROR_META_TOKEN=

MANNERS_FB_PAGE_ID=
MANNERS_IG_ACCOUNT_ID=
MANNERS_META_TOKEN=

CARTOON_FB_PAGE_ID=
CARTOON_IG_ACCOUNT_ID=
CARTOON_META_TOKEN=

# ─── Server ───────────────────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
DEBUG=false
DOMAIN=your_vps_domain_or_ip
ENV_EOF
    echo "✅ .env template created — fill in your values!"
fi

echo ""
echo "✅ All dependencies installed!"
echo "=============================="
echo ""
echo "Next steps:"
echo "  1. Fill in .env with your API keys"
echo "  2. Run setup scripts: ./scripts/setup_rclone.sh"
echo "  3. Start dashboard: uvicorn main:app --host 0.0.0.0 --port 8000"
echo "  4. Install cron jobs: python cron_setup.py"
