#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=== Building ClipKit.app ==="
rm -rf dist

npm run build 2>&1

APP="dist/mac-arm64/ClipKit.app"
if [ -d "$APP" ]; then
    echo ""
    echo "✅ Build successful: $APP"
    echo ""
    echo "To install: drag dist/mac-arm64/ClipKit.app to /Applications"
    echo "Or run now: open \"$APP\""
else
    echo "❌ Build failed — check output above"
    exit 1
fi
