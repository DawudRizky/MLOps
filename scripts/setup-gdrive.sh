#!/bin/bash
#
# Setup Google Drive with rclone
# This will guide you through authenticating with Google Drive
#

set -e

echo "=========================================="
echo "Google Drive Setup with rclone"
echo "=========================================="
echo ""
echo "Follow these steps:"
echo ""
echo "1. When prompted, choose: n (for new remote)"
echo "2. Name: gdrive"
echo "3. Storage: choose '18' for Google Drive"
echo "4. client_id: press Enter (leave blank)"
echo "5. client_secret: press Enter (leave blank)"
echo "6. scope: choose '1' for full access"
echo "7. root_folder_id: press Enter (leave blank)"
echo "8. service_account_file: press Enter (leave blank)"
echo "9. Edit advanced config: n (No)"
echo "10. Use auto config: n (No - because we're on a headless server)"
echo ""
echo "11. IMPORTANT: You'll get a URL like:"
echo "    https://accounts.google.com/o/oauth2/auth?..."
echo ""
echo "    Copy that URL and open it in your LOCAL browser"
echo "    Login with your Google account"
echo "    Grant permissions"
echo "    Copy the verification code from the browser"
echo "    Paste it back in the terminal"
echo ""
echo "12. Configure as team drive: n (No)"
echo "13. Confirm: y (Yes)"
echo "14. Quit: q (Quit)"
echo ""
echo "Press Enter to continue..."
read

rclone config
