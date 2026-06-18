#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_factory.sh — One-command setup for VPS 2 (Vast.ai GPU server)
#
# This script is designed to run automatically when a Vast.ai instance boots.
# Set it as the "On-Start Script" in the Vast.ai instance configuration.
#
# Usage:
#   curl -sSL https://YOUR_URL/setup_factory.sh | bash
# Or:
#   ./scripts/setup_factory.sh --month 2026_06
# ─────────────────────────────────────────────────────────────────────────────
set -e

MONTH="${1:-$(date +%Y_%m)}"
WORKSPACE="/workspace"
FACTORY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMFYUI_DIR="$WORKSPACE/ComfyUI"
MODELS_DIR="$COMFYUI_DIR/models"

echo "🏭 YouTube Content Factory — VPS 2 (GPU) Setup"
echo "================================================"
echo "Month: $MONTH"
echo "CUDA: $(nvcc --version 2>/dev/null | head -1 || echo 'checking...')"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true

# ─── 1. System packages ───────────────────────────────────────────────────────
echo "📦 Installing system packages..."
apt-get update -y -q
apt-get install -y -q \
    ffmpeg \
    git \
    curl wget \
    python3-pip \
    fuse \
    systemd

# ─── 2. Python packages ──────────────────────────────────────────────────────
echo "📚 Installing Python packages..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install \
    requests \
    loguru \
    python-dotenv \
    aiofiles

# ─── 3. ComfyUI & Custom Nodes ────────────────────────────────────────────────
echo "🎨 Setting up ComfyUI..."
if [ ! -d "$COMFYUI_DIR" ]; then
    git clone --depth=1 https://github.com/comfyanonymous/ComfyUI $COMFYUI_DIR
fi
cd $COMFYUI_DIR
pip install -r requirements.txt

echo "🧩 Installing Custom Nodes..."
cd $COMFYUI_DIR/custom_nodes
if [ ! -d "ComfyUI-VideoHelperSuite" ]; then
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    pip install -r ComfyUI-VideoHelperSuite/requirements.txt
fi

# ─── 4. Create model directories ─────────────────────────────────────────────
echo "📂 Creating model directories..."
mkdir -p $MODELS_DIR/checkpoints
mkdir -p $MODELS_DIR/vae
mkdir -p $MODELS_DIR/clip
mkdir -p $MODELS_DIR/unet
mkdir -p $MODELS_DIR/diffusion_models
mkdir -p $WORKSPACE/output
mkdir -p $WORKSPACE/logs

# ─── 5. Download Models (FLUX Schnell & LTX-Video) ────────────────────────────
echo "⬇️  Downloading Models..."

download_model() {
    local url=$1
    local path=$2
    echo "Downloading $(basename $path)..."
    # -c enables resuming partial downloads. If fully downloaded, it skips automatically.
    wget -c -q --show-progress -O "$path.tmp" "$url" && mv "$path.tmp" "$path" || echo "⚠️  Download failed for $path"
}

download_model "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors" "$MODELS_DIR/unet/flux1-schnell.safetensors"
download_model "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors" "$MODELS_DIR/vae/ae.safetensors"
download_model "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" "$MODELS_DIR/clip/t5xxl_fp8_e4m3fn.safetensors"
download_model "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" "$MODELS_DIR/clip/clip_l.safetensors"
download_model "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.1.safetensors" "$MODELS_DIR/diffusion_models/ltx-video-2b-v0.9.1.safetensors"
download_model "https://huggingface.co/Kijai/LTX-Video-comfy/resolve/main/ltx-video-vae.safetensors" "$MODELS_DIR/vae/ltx-video-vae.safetensors"

# ─── 6. Install rclone ────────────────────────────────────────────────────────
echo "☁️  Installing rclone..."
curl -s https://rclone.org/install.sh | bash

# ─── 7. Copy rclone config from environment or Drive credentials ──────────────
echo "☁️  Setting up rclone config..."
if [ ! -z "$RCLONE_CONFIG_B64" ]; then
    mkdir -p ~/.config/rclone
    echo "$RCLONE_CONFIG_B64" | base64 -d > ~/.config/rclone/rclone.conf
    echo "✅ rclone config loaded from environment"
fi

mkdir -p /mnt/gdrive
rclone mount gdrive: /mnt/gdrive --daemon --vfs-cache-mode writes || \
    echo "⚠️  Google Drive mount failed — check rclone config"

# ─── 8. Background Services & Logging ───────────────────────────────────────────
echo "⚙️  Starting ComfyUI in the background..."

# Setup logrotate
cat <<EOF > /etc/logrotate.d/youtube_factory
/workspace/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}
EOF

cd $COMFYUI_DIR
nohup python3 main.py --listen 0.0.0.0 --port 8188 --output-directory $WORKSPACE/output > /workspace/logs/comfyui.log 2>&1 &

echo "⏳ Waiting for ComfyUI to start (can take several minutes)..."
timeout 180 bash -c 'until curl -s http://localhost:8188/system_stats > /dev/null; do sleep 5; echo "Waiting..."; done' || true

if curl -s http://localhost:8188/system_stats > /dev/null; then
    echo "✅ ComfyUI API is responding on port 8188."
    
    # Validate Workflows
    OBJECTS=$(curl -s http://localhost:8188/object_info)
    if echo "$OBJECTS" | grep -qi "LTX"; then
        echo "✅ LTX workflow nodes detected."
    else
        echo "❌ ERROR: LTX native nodes missing from ComfyUI. Aborting setup!"
        exit 1
    fi
    
    if echo "$OBJECTS" | grep -qi "Flux"; then
        echo "✅ FLUX workflow nodes detected."
    else
        echo "❌ ERROR: FLUX native nodes missing from ComfyUI. Aborting setup!"
        exit 1
    fi
else
    echo "❌ ERROR: ComfyUI failed to start! Check /workspace/logs/comfyui.log. Aborting setup!"
    exit 1
fi

# ─── 9. Start Pipeline ────────────────────────────────────────────────────────
echo "🚀 Validation passed! Starting factory pipeline & watchdog..."
cd $FACTORY_DIR
nohup python3 -m modules.comfyui_watchdog > /workspace/logs/watchdog.log 2>&1 &
nohup python3 -m modules.factory_runner --month $MONTH > /workspace/logs/factory_runner.log 2>&1 &

echo ""
echo "✅ Setup complete!"
echo "  ComfyUI: http://localhost:8188"
echo "  Runner Status: ps aux | grep python"
echo "  Logs:    tail -f /workspace/logs/*.log"
echo "  Output:  $WORKSPACE/output/"
