import json
import os
from dataclasses import dataclass, asdict, field

SETTINGS_DIR = os.path.expanduser('~/.clipkit')
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')


@dataclass
class Settings:
    buffer_size_mb: int = 50
    max_items: int = 200
    start_at_login: bool = False
    hotkey_open: str = 'cmd+shift+v'
    hotkey_transform: str = 'cmd+shift+t'
    hidden_transforms: list = field(default_factory=list)   # transform names to hide
    transform_order: list = field(default_factory=list)     # transform names in user order
    transform_hotkeys: dict = field(default_factory=dict)  # transform name → hotkey string e.g. "cmd+alt+1"

    def save(self):
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**valid)
        except Exception:
            return cls()


_instance: Settings | None = None


def get() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings.load()
    return _instance


def save():
    if _instance:
        _instance.save()
