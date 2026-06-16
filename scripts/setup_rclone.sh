#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_rclone.sh — Configure rclone Google Drive mount on VPS 1
#
# Run this ONCE after rclone is installed.
# Requires a browser for the OAuth step (run locally or via SSH tunnel).
# ─────────────────────────────────────────────────────────────────────────────
set -e

MOUNT_POINT="/mnt/gdrive"
RCLONE_REMOTE="gdrive"
GDRIVE_DIR="youtube_factory"

echo "☁️  Setting up Google Drive via rclone"
echo "======================================="

# ─── 1. Create mount point ────────────────────────────────────────────────────
echo "📁 Creating mount point at $MOUNT_POINT..."
mkdir -p $MOUNT_POINT

# ─── 2. Run rclone config (interactive) ──────────────────────────────────────
echo ""
echo "Starting rclone config..."
echo "Select: n (new remote) → name it 'gdrive' → type 17 (Google Drive) → follow OAuth"
echo ""
rclone config

# ─── 3. Test the connection ───────────────────────────────────────────────────
echo ""
echo "🧪 Testing Google Drive connection..."
rclone ls $RCLONE_REMOTE: --max-depth 1 && echo "✅ Connection works!" || {
    echo "❌ Connection failed. Re-run 'rclone config'"
    exit 1
}

# ─── 4. Create factory directory on Drive ─────────────────────────────────────
echo "📂 Creating $GDRIVE_DIR on Google Drive..."
rclone mkdir "$RCLONE_REMOTE:$GDRIVE_DIR" || true

# ─── 5. Create systemd service for auto-mount ────────────────────────────────
echo "⚙️  Creating rclone mount systemd service..."
cat > /etc/systemd/system/rclone-gdrive.service << 'SERVICE_EOF'
[Unit]
Description=rclone Google Drive Mount
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/rclone mount gdrive: /mnt/gdrive \
    --vfs-cache-mode writes \
    --vfs-write-back 5s \
    --allow-non-empty \
    --allow-other \
    --buffer-size 256M \
    --dir-cache-time 48h \
    --poll-interval 15s \
    --log-level INFO \
    --log-file /var/log/rclone.log
ExecStop=/bin/fusermount -u /mnt/gdrive
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
SERVICE_EOF

# ─── 6. Enable and start ──────────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable rclone-gdrive
systemctl start rclone-gdrive

echo ""
echo "✅ Waiting for mount..."
sleep 5

if mountpoint -q $MOUNT_POINT; then
    echo "✅ Google Drive mounted at $MOUNT_POINT"
    echo "   Path: $MOUNT_POINT/$GDRIVE_DIR/"
    ls $MOUNT_POINT/
else
    echo "⚠️  Mount not ready yet. Check: systemctl status rclone-gdrive"
fi

echo ""
echo "✅ rclone setup complete!"
echo "========================"
echo "  Mount point: $MOUNT_POINT"
echo "  Factory dir: $MOUNT_POINT/$GDRIVE_DIR/"
echo "  Check status: systemctl status rclone-gdrive"
echo "  View logs:    journalctl -u rclone-gdrive -f"
