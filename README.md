# ClipKit (Electron)

macOS menu-bar clipboard manager — Electron rewrite of the original Python/PyObjC app.

## Features
- Menu-bar app (✂ scissors icon), no Dock icon (`LSUIElement`).
- Clipboard monitor: watches the macOS pasteboard change count and reads only on change (Universal Clipboard-safe), stores history in `~/.clipkit/history.json`.
- History window (⌘⌥V): search, filter tabs (All/Text/JSON/SQL/CSV), type badges, copy/transform/pin/delete.
- Transform window (⌘⌥T): paste-from-clipboard, type-filtered transform dropdown, apply (auto-copies), ⇅ swap, output badge + stats.
- Settings window: General (launch at login, max items, max buffer MB), Transforms (reorder + enable/disable + per-transform hotkey), Hotkeys (record Open History / Transform Text shortcuts).
- 22 text transforms (see `src/transforms.js`).

## Setup
```bash
npm install
npm start
```

## Build a DMG
```bash
npm run build
```

## Tray icon
`main.js` renders a built-in scissors SVG as the menu-bar icon, so no asset is required.
To bake a static PNG instead, run once:
```bash
npx electron assets/make_tray.js
```
This writes `assets/trayTemplate.png`, which `main.js` prefers when present.

## Data files
- `~/.clipkit/settings.json` — settings
- `~/.clipkit/history.json` — clipboard history (`[{ text, pinnedAt, createdAt }]`)

## Hotkeys
Defaults: Open History `⌘⌥V`, Transform Text `⌘⌥T`. Per-transform hotkeys apply a transform
directly to the current clipboard contents.

## Releases & Homebrew
Prebuilt releases are on the [Releases page](https://github.com/arrrev/clipkit/releases).
Install or update with Homebrew:
```bash
brew install --cask arrrev/clipkit/clipkit
brew upgrade --cask clipkit
```

## Python version
The original Python/PyObjC app (1.x) lives on the [`python`](https://github.com/arrrev/clipkit/tree/python) branch, tagged `python-1.0.9`.
