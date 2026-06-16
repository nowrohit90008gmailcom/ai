#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_vps1.sh — Initial setup for Hetzner CX22 VPS (the Brain / always-on)
#
# Run as root on a fresh Ubuntu 22.04 server:
#   curl -sSL https://raw.githubusercontent.com/you/factory/main/scripts/setup_vps1.sh | bash
# Or upload and run:
#   chmod +x setup_vps1.sh && ./setup_vps1.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_DIR="/app"
DOMAIN="${DOMAIN:-yourdomain.com}"    # Set this before running
VENV_DIR="$APP_DIR/venv"

echo "🚀 ShortForge — VPS 1 Setup"
echo "=============================="

# ─── 1. System updates ────────────────────────────────────────────────────────
echo "📦 Updating system packages..."
apt-get update -y
apt-get upgrade -y
apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    ffmpeg \
    nginx \
    certbot python3-certbot-nginx \
    git \
    curl wget \
    htop \
    cron \
    build-essential \
    libssl-dev \
    ufw

# ─── 2. Firewall ──────────────────────────────────────────────────────────────
echo "🔒 Configuring firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ─── 3. Create app directory ──────────────────────────────────────────────────
echo "📁 Creating app directory..."
mkdir -p $APP_DIR
cd $APP_DIR

# ─── 4. Python venv ───────────────────────────────────────────────────────────
echo "🐍 Creating Python virtual environment..."
python3.11 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

# ─── 5. Install dependencies (done by install_deps.sh) ────────────────────────
echo "📚 Installing Python dependencies..."
pip install --upgrade pip
pip install -r $APP_DIR/requirements.txt

# ─── 6. Install Playwright browsers ──────────────────────────────────────────
echo "🌐 Installing Playwright Chromium..."
playwright install chromium
playwright install-deps

# ─── 7. Nginx config ──────────────────────────────────────────────────────────
echo "🌐 Configuring Nginx..."
cat > /etc/nginx/sites-available/youtube-factory << 'NGINX_EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/youtube-factory /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# ─── 8. systemd service for FastAPI ───────────────────────────────────────────
echo "⚙️  Creating systemd service..."
cat > /etc/systemd/system/youtube-factory.service << 'SERVICE_EOF'
[Unit]
Description=YouTube Content Factory Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/app
ExecStart=/app/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
Environment=PYTHONPATH=/app
EnvironmentFile=/app/.env

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable youtube-factory
systemctl start youtube-factory

# ─── 9. SSL with Let's Encrypt ────────────────────────────────────────────────
echo "🔐 Installing SSL certificate..."
certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || \
    echo "⚠️  SSL setup skipped (set DOMAIN variable first)"

# ─── 10. Install rclone ───────────────────────────────────────────────────────
echo "☁️  Installing rclone..."
curl https://rclone.org/install.sh | bash

echo ""
echo "✅ VPS 1 Setup Complete!"
echo "========================"
echo "Next steps:"
echo "  1. Upload your code to $APP_DIR"
echo "  2. Create $APP_DIR/.env with your API keys"
echo "  3. Run: rclone config  (to set up Google Drive)"
echo "  4. Run: python cron_setup.py  (to install cron jobs)"
echo "  5. Run: python modules/auth_manager.py  (to authenticate YouTube)"
echo ""
echo "Dashboard: http://$DOMAIN"
