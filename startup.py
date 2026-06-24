"""Manage LaunchAgent for start-at-login."""
import os
import subprocess

LABEL = 'com.clipkit.agent'
PLIST = os.path.expanduser(f'~/Library/LaunchAgents/{LABEL}.plist')
APP_BINARY = '/Applications/ClipKit.app/Contents/MacOS/ClipKit'

_PLIST_TEMPLATE = '''\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{binary}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>ProcessType</key><string>Interactive</string>
  <key>StartInterval</key><integer>0</integer>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
'''


def is_enabled() -> bool:
    return os.path.exists(PLIST)


def enable():
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    log = os.path.expanduser('~/.clipkit/clipkit.log')
    content = _PLIST_TEMPLATE.format(label=LABEL, binary=APP_BINARY, log=log)
    with open(PLIST, 'w') as f:
        f.write(content)
    subprocess.run(['launchctl', 'unload', PLIST], capture_output=True)
    subprocess.run(['launchctl', 'load', PLIST], capture_output=True)


def disable():
    if os.path.exists(PLIST):
        subprocess.run(['launchctl', 'unload', PLIST], capture_output=True)
        os.remove(PLIST)


def toggle() -> bool:
    if is_enabled():
        disable()
        return False
    else:
        enable()
        return True
