# ClipKit

A macOS clipboard manager with text transforms, global hotkeys, and clipboard history.

## Features

- **Clipboard history** — browse and re-paste recent clipboard items
- **Text transforms** — CSV, JSON, SQL, case, sort, deduplicate, and more
- **Global hotkeys** — ⌘⌥V (history) and ⌘⌥T (transform) work anywhere
- **Quick Transform** — right-click any history item to transform inline
- **Per-transform hotkeys** — set custom hotkeys for any transform in Settings
- **Auto-start at login** — optional LaunchAgent support
- **Menu bar only** — no Dock icon, always available from ✂

## Install via Homebrew

```bash
brew tap arrrev/clipkit
brew install --cask clipkit
```

## Manual Install

Download the latest release from [Releases](https://github.com/arrrev/clipkit/releases) and follow the included Setup Instructions.

## Requirements

- macOS 13 (Ventura) or later
- Apple Silicon or Intel Mac

## After Installing

Grant Accessibility permission for hotkeys to work:

**System Settings → Privacy & Security → Accessibility → ClipKit → ON**

Then quit and relaunch ClipKit.

## Built With

- Python 3.13 + PyObjC
- rumps (menu bar framework)
- py2app (app bundler)
