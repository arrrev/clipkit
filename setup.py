from setuptools import setup

APP = ['main.py']

OPTIONS = {
    'argv_emulation': False,
    'semi_standalone': False,
    'site_packages': True,
    'iconfile': 'ClipKit.icns',
    'plist': {
        'CFBundleName': 'ClipKit',
        'CFBundleDisplayName': 'ClipKit',
        'CFBundleIdentifier': 'com.clipkit.app',
        'CFBundleVersion': '1.0.6',
        'CFBundleShortVersionString': '1.0.6',
        'LSUIElement': True,          # no Dock icon
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': 'ClipKit needs access to monitor clipboard.',
    },
    'packages': [
        'rumps', 'objc', 'Foundation', 'AppKit', 'Quartz',
        'pynput', 'sqlparse', 'PIL',
        'clipboard_monitor', 'history_window',
        'transform_window', 'settings_window', 'transform',
        'settings', 'startup',
    ],
    'includes': ['objc', 'Foundation', 'AppKit', 'sqlparse'],
}

setup(
    app=APP,
    name='ClipKit',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
