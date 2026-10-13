#!/bin/bash
APP_NAME="ClipKit.app"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/dist/mac-arm64/$APP_NAME"
DEST="/Applications/$APP_NAME"

# Build if app not already built
if [ ! -d "$SRC" ]; then
    echo "Building ClipKit first…"
    cd "$SCRIPT_DIR"
    npm run build
fi

echo "Installing ClipKit..."
rm -rf "$DEST"
cp -r "$SRC" "$DEST"

echo "Removing security restrictions..."
osascript -e "do shell script \"xattr -rd com.apple.quarantine '$DEST' 2>/dev/null; true\" with administrator privileges"

echo "Launching ClipKit..."
open "$DEST"

echo ""
echo "✅ ClipKit installed! Look for ✂ in your menu bar."
echo "   You can close this window."
sleep 3
