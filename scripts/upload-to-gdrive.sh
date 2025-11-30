#!/bin/bash
#
# Quick Upload MLflow Artifacts to Google Drive
# Usage: ./upload-to-gdrive.sh
#

set -e

echo "=========================================="
echo "Upload MLflow Artifacts to Google Drive"
echo "=========================================="
echo ""

# Check if rclone is configured
if ! rclone listremotes | grep -q "gdrive:"; then
    echo "⚠️  Google Drive not configured yet!"
    echo ""
    echo "Please run: rclone config"
    echo ""
    echo "Quick setup instructions:"
    echo "1. Type: n (new remote)"
    echo "2. Name: gdrive"
    echo "3. Storage: 18 (Google Drive)"
    echo "4. Leave client_id blank (press Enter)"
    echo "5. Leave client_secret blank (press Enter)"
    echo "6. Scope: 1 (Full access)"
    echo "7. Leave root_folder_id blank"
    echo "8. Leave service_account_file blank"
    echo "9. Advanced config: n"
    echo "10. Auto config: n (important!)"
    echo "11. Copy the URL to your browser, login, get code"
    echo "12. Paste the code back"
    echo "13. Team drive: n"
    echo "14. Confirm: y"
    echo "15. Quit: q"
    echo ""
    exit 1
fi

# Check if backup file exists
BACKUP_FILE="/root/mlflow_latest_5runs_*.tar.gz"
LATEST_BACKUP=$(ls -t $BACKUP_FILE 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup file found!"
    echo "Run the backup script first: ./scripts/quick-backup-to-gdrive.sh"
    exit 1
fi

FILE_SIZE=$(du -h "$LATEST_BACKUP" | cut -f1)
echo "📦 Found backup: $(basename $LATEST_BACKUP)"
echo "📊 Size: $FILE_SIZE"
echo ""

# Create MLOps folder on Google Drive if not exists
echo "📁 Creating MLOps folder on Google Drive..."
rclone mkdir gdrive:MLOps-Backup 2>/dev/null || true

# Upload to Google Drive
echo "☁️  Uploading to Google Drive..."
echo "This may take 5-15 minutes depending on your connection..."
echo ""

rclone copy "$LATEST_BACKUP" gdrive:MLOps-Backup/ --progress --stats 10s

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Upload successful!"
    echo ""
    echo "📍 File location: Google Drive > MLOps-Backup > $(basename $LATEST_BACKUP)"
    echo ""
    echo "To access:"
    echo "1. Open https://drive.google.com"
    echo "2. Look for 'MLOps-Backup' folder"
    echo "3. File: $(basename $LATEST_BACKUP)"
    echo ""
    
    # Get shareable link
    echo "🔗 Getting shareable link..."
    rclone link gdrive:MLOps-Backup/$(basename $LATEST_BACKUP) || echo "⚠️  Could not generate link automatically. Open Google Drive to share manually."
else
    echo "❌ Upload failed!"
    exit 1
fi
