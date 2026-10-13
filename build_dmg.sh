#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=== ClipKit — build & package ==="

# ── 1. Build app bundle ────────────────────────────────────────────────────
echo "→ Building app…"
rm -rf dist
npm run build 2>&1

APP="dist/mac-arm64/ClipKit.app"
[ -d "$APP" ] || { echo "❌ Build failed"; exit 1; }
echo "✅ App built"

# ── 2. Sign ad-hoc (lets app run without quarantine prompt) ───────────────
echo "→ Signing…"
find "$APP/Contents/Frameworks" -name "*.dylib" -o -name "*.so" 2>/dev/null | \
  while read f; do codesign --force --sign - "$f" 2>/dev/null || true; done
codesign --force --sign - "$APP/Contents/MacOS/ClipKit" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || true
xattr -cr "$APP"
echo "✅ Signed"

# ── 3. Create DMG ─────────────────────────────────────────────────────────
echo "→ Creating DMG…"
DMG_NAME="ClipKit.dmg"
DMG_STAGING="/tmp/ClipKit_dmg_staging"
rm -rf "$DMG_STAGING" "$DMG_NAME"
mkdir -p "$DMG_STAGING"

cp -r "$APP" "$DMG_STAGING/"
xattr -cr "$DMG_STAGING/ClipKit.app" 2>/dev/null || true
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create \
  -volname "ClipKit" \
  -srcfolder "$DMG_STAGING" \
  -ov -format UDRW \
  -fs HFS+ \
  /tmp/ClipKit_rw.dmg

MOUNT=$(hdiutil attach /tmp/ClipKit_rw.dmg -readwrite -noverify -noautoopen | \
  grep -E '^/dev/' | tail -1 | awk '{print $NF}')

osascript <<APPLESCRIPT
tell application "Finder"
  tell disk "ClipKit"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {200, 120, 750, 420}
    set opts to icon view options of container window
    set icon size of opts to 100
    set arrangement of opts to not arranged
    set position of item "ClipKit.app" of container window to {160, 150}
    set position of item "Applications" of container window to {390, 150}
    close
    open
    update without registering applications
    delay 2
    close
  end tell
end tell
APPLESCRIPT

sleep 1
hdiutil detach "$MOUNT" -quiet || true

hdiutil convert /tmp/ClipKit_rw.dmg \
  -format UDZO -imagekey zlib-level=9 \
  -o "$DMG_NAME"

rm -f /tmp/ClipKit_rw.dmg
rm -rf "$DMG_STAGING"

echo ""
echo "✅ Done: $(pwd)/$DMG_NAME  ($(du -h "$DMG_NAME" | cut -f1))"
echo ""
echo "Share ClipKit.dmg — recipients open it, drag ClipKit → Applications, done."
