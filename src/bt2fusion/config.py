"""Persistent user settings (the remembered install directory).

The game records its *channel* in the registry but not its install directory,
and there is no uninstall entry or shortcut to query. So the only reliable way
to avoid a full-disk scan is to remember the directory the user picked.
"""

from __future__ import annotations

import contextlib
import json
import os

__all__ = [
    'clear',
    'config_dir',
    'config_path',
    'get_install_dir',
    'load',
    'save',
    'set_install_dir',
]

_APP_NAME = 'bt2fusion'
_FILENAME = 'config.json'


def config_dir() -> str:
    """Directory holding this app's settings."""
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, _APP_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), _FILENAME)


def load() -> dict:
    """Read the settings file; returns ``{}`` when absent or unreadable."""
    try:
        with open(config_path(), encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    """Write the settings file, creating the directory as needed."""
    os.makedirs(config_dir(), exist_ok=True)
    tmp = config_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, config_path())


def get_install_dir() -> str | None:
    value = load().get('install_dir')
    return value if isinstance(value, str) and value else None


def set_install_dir(path: str) -> None:
    data = load()
    data['install_dir'] = path
    save(data)


def clear() -> None:
    with contextlib.suppress(OSError):
        os.remove(config_path())
