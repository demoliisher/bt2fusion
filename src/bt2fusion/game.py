"""Reading and writing the game's channel state.

Three independent sources describe the current channel:

1. the registry (``...\\Wooduan\\SSJJ2\\COMMON``) -- authoritative, written by
   the launcher itself and used by it to recover a damaged ``platform.xml``;
2. the config files in the install directory;
3. ``myeasylog.log``, which records ``platform_config_.channel_id_:N``.

:func:`detect` consults them in that order. Reading never writes; use
:func:`ensure_configs` or :func:`rewrite` to change anything on disk.
"""

from __future__ import annotations

import os
import string

from . import config, fsutil, shortcuts
from .channels import CHANNELS, DEFAULT_CHANNEL, LAUNCHER, Channel
from .errors import BT2FusionError, InstallNotFoundError
from .profiles import INI_FILENAME, XML_FILENAME

__all__ = [
    'CAFE_SUBPATHS',
    'CONVENTIONAL_SUBPATHS',
    'INI_NAME',
    'LOG_NAME',
    'OFFICIAL_SUBPATHS',
    'XML_NAME',
    'DetectedChannel',
    'detect',
    'detect_from_config',
    'detect_from_log',
    'detect_from_registry',
    'ensure_configs',
    'find_all',
    'installer_ini',
    'is_install_dir',
    'launch',
    'locate',
    'read_registry_channel',
    'reset_location_cache',
    'rewrite',
]

XML_NAME = XML_FILENAME
INI_NAME = INI_FILENAME
LOG_NAME = 'myeasylog.log'

#: Game root used by internet-cafe diskless images.
#:
#: 网维大师 (顺网) and 云更新 both publish games under a shared ``网络游戏``
#: directory, so a cafe machine normally has the game at
#: ``<drive>:\网络游戏\生死狙击2``. Cafes are this tool's primary target: the
#: client there ships with the cafe's own channel, and a player has to replace
#: the config to log in with their own account. That path is therefore tried
#: first, ahead of any remembered or officially-installed location.
CAFE_GAME_ROOT = '网络游戏'
#: Windows path lookups are case-insensitive, so one casing of the ASCII name
#: covers the others; only genuinely different names are listed.
CAFE_SUBPATHS = (
    os.path.join(CAFE_GAME_ROOT, '生死狙击2'),
    os.path.join(CAFE_GAME_ROOT, 'SSJJ2'),
)

#: Layout written by the official Wooduan installer.
OFFICIAL_SUBPATHS = (
    os.path.join('Wooduan', 'SSJJ2-WD'),
)

#: Every conventional sub-path, most likely first.
CONVENTIONAL_SUBPATHS = CAFE_SUBPATHS + OFFICIAL_SUBPATHS

#: Registry key holding the authoritative channel, in the 32-bit view.
REGISTRY_KEY = r'SOFTWARE\WOW6432Node\Wooduan\SSJJ2\COMMON'
REGISTRY_KEY_64 = r'SOFTWARE\Wooduan\SSJJ2\COMMON'

_location: str | None = None
_location_resolved: bool = False


class DetectedChannel:
    """What channel the game is currently set to use.

    Two independent records can disagree:

    * ``config_channel`` -- what the config files in the install directory
      say. This is what switching actually rewrites.
    * ``registry_channel`` -- what the launcher last recorded in the registry.
      The launcher uses it to restore a damaged ``platform.xml``.

    ``channel`` is the best single answer, preferring the config files, and
    :attr:`consistent` reports whether the two agree. They normally diverge
    right after a switch, until the game is next launched and re-registers.
    """

    __slots__ = ('config_channel', 'registry_channel', 'source')

    def __init__(self, config_channel=None, registry_channel=None,
                 source: str = 'none'):
        self.config_channel = config_channel
        self.registry_channel = registry_channel
        self.source = source

    @property
    def channel(self) -> Channel | None:
        """Best single answer, preferring the on-disk config."""
        return self.config_channel or self.registry_channel

    @property
    def consistent(self) -> bool:
        """True when both records agree (or only one is known)."""
        if self.config_channel is None or self.registry_channel is None:
            return True
        return self.config_channel.key == self.registry_channel.key

    def __bool__(self) -> bool:
        return self.channel is not None

    def __repr__(self) -> str:
        name = self.channel.key if self.channel else None
        return (f'<DetectedChannel {name} via {self.source}'
                f'{" (registry disagrees)" if not self.consistent else ""}>')


def is_install_dir(path) -> bool:
    """True when ``path`` looks like a BT2 install directory."""
    if not path:
        return False
    return os.path.isfile(os.path.join(path, LAUNCHER.name))


# --- reading helpers --------------------------------------------------------

def _read(path: str, name: str):
    """Read a file from the install dir; ``None`` when missing/unreadable."""
    try:
        with open(os.path.join(path, name), 'rb') as handle:
            return handle.read()
    except OSError:
        return None


def _write(path: str, name: str, data: bytes) -> None:
    with open(os.path.join(path, name), 'wb') as handle:
        handle.write(data)


def _read_configs(path: str):
    return _read(path, XML_NAME), _read(path, INI_NAME)


# --- registry ---------------------------------------------------------------

def read_registry_channel():
    """Read the channel the launcher recorded in the registry.

    Returns ``(platform, channel_id)`` or ``(None, None)``. The 32-bit view is
    tried first because the launcher is a 32-bit binary.
    """
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None, None

    for key_path in (REGISTRY_KEY, REGISTRY_KEY_64):
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    platform, _ = _query(key, 'Platform')
                    channel_id, _ = _query(key, 'Channel')
            except OSError:
                continue
            if channel_id is not None or platform:
                return platform, channel_id
    return None, None


def _query(key, name):
    import winreg
    try:
        return winreg.QueryValueEx(key, name)
    except OSError:
        return None, None


def detect_from_registry():
    """Channel from the registry, or ``None``."""
    platform, channel_id = read_registry_channel()
    if channel_id is not None:
        candidates = CHANNELS.get_from_id(int(channel_id))
        if len(candidates) == 1:
            return candidates[0]
        if platform:
            found = CHANNELS.get_from_platform(platform)
            if found is not None:
                return found
        if candidates:
            return candidates[0]
    if platform:
        return CHANNELS.get_from_platform(platform)
    return None


# --- config files -----------------------------------------------------------

def detect_from_config(path=None):
    """Channel implied by the config files, or ``None``.

    ``platform.xml`` takes priority over ``platform_exm.ini``.
    """
    path = path or locate()
    if not path:
        return None

    xml, ini = _read_configs(path)
    if xml is None and ini is None:
        return None

    if xml is not None:
        for channel in CHANNELS:
            if channel.xml == xml:
                return channel
    if ini is not None:
        for channel in CHANNELS:
            if channel.ini == ini:
                return channel
    return None


# --- log --------------------------------------------------------------------

def detect_from_log(path=None):
    """Channel recorded in ``myeasylog.log``, or ``None``."""
    import re

    path = path or locate()
    if not path:
        return None

    raw = _read(path, LOG_NAME)
    if not raw:
        return None

    ids = re.findall(r'channel_id_\s*:\s*(\d+)',
                     raw.decode('utf-8', errors='replace'))
    if not ids:
        return None

    try:
        last_id = int(ids[-1])
    except ValueError:
        return None

    possible = CHANNELS.get_from_id(last_id)
    if not possible:
        # An id with no registered channel (3, 5, 7, ...). Previously this
        # raised IndexError; report "unknown" instead.
        return None
    if len(possible) == 1:
        return possible[0]

    # Several channels share this id (official/beta both report 1). The log
    # cannot separate them, so compare the actual config blobs.
    xml, ini = _read_configs(path)
    for channel in possible:
        if channel.matches(xml, ini):
            return channel
    return possible[0]


# --- combined ---------------------------------------------------------------

def detect(path=None) -> DetectedChannel:
    """Determine the currently configured channel.

    Read-only: never modifies anything.

    Sources are consulted in this order:

    1. the config files -- authoritative, because they are what the game
       actually reads at startup and what :func:`rewrite` changes;
    2. the login log ``myeasylog.log``;
    3. the registry -- advisory only. See the note below.

    The registry is deliberately the *last* resort rather than a trusted
    source. It is machine-global state: on a shared or reimaged machine it can
    survive from a previous install, user or channel, and the game reads it
    only to repair a damaged ``platform.xml``. It is also unavailable in
    practice when reasoning about someone else's machine. It is therefore
    reported for information but never allowed to override the config files.
    """
    path = path or locate()

    config_channel = None
    source = 'none'
    if path:
        config_channel = detect_from_config(path)
        if config_channel is not None:
            source = 'config'
        else:
            config_channel = detect_from_log(path)
            if config_channel is not None:
                source = 'log'

    # Advisory: recorded for display, never trusted over the config files.
    registry_channel = detect_from_registry()

    if config_channel is not None:
        if registry_channel is not None and \
                registry_channel.key != config_channel.key:
            source += '+registry-mismatch'
        return DetectedChannel(config_channel, registry_channel, source)

    if registry_channel is not None:
        return DetectedChannel(None, registry_channel, 'registry-only')

    return DetectedChannel(None, None, 'none')


# --- locating ---------------------------------------------------------------

def locate(refresh: bool = False):
    """Find the BT2 install directory, or ``None``.

    Ordered for the primary use case -- a player at an internet cafe, on a
    machine they have never used before, where nothing is remembered:

    1. a shortcut pointing at the launcher (covers manually created and
       installer-created shortcuts, whatever the game is named);
    2. the cafe layout ``<drive>:\\网络游戏\\生死狙击2``, across every drive;
    3. other conventional layouts;
    4. the directory remembered from a previous run;
    5. a full filesystem scan (slow -- last resort).

    A remembered directory ranks below the cafe paths deliberately: on a
    shared or diskless machine a stale path is common, while the cafe layout
    is stable and cheap to test.

    Returns ``None`` when the game cannot be found. The result is cached;
    pass ``refresh=True`` to search again.
    """
    global _location, _location_resolved

    if _location_resolved and not refresh:
        return _location

    found = shortcuts.find_install_from_shortcuts()

    if found is None:
        found = _first_install_dir(_cafe_candidates())

    if found is None:
        found = _first_install_dir(_conventional_candidates())

    if found is None:
        remembered = config.get_install_dir()
        if remembered and is_install_dir(remembered):
            found = remembered

    # Last resort: scan every drive. This is slow, so the result is
    # remembered to avoid repeating it on the next run.
    if found is None:
        found = fsutil.find_file(LAUNCHER.name)

    _location, _location_resolved = found, True
    return found


def _first_install_dir(candidates):
    """Return the first candidate that looks like an install directory."""
    for candidate in candidates:
        if is_install_dir(candidate):
            return candidate
    return None


def _drive_roots():
    """Drive roots, largest first, falling back to a probe of A:-Z:.

    ``fsutil.get_disk_used`` reports used space, which lets the busiest drive
    -- normally where games live -- be checked first.
    """
    try:
        used = fsutil.get_disk_used()
    except OSError:
        used = {}
    if used:
        return sorted(used, key=used.get, reverse=True)

    return [f'{letter}:\\' for letter in string.ascii_uppercase
            if os.path.exists(f'{letter}:\\')]


def _cafe_candidates():
    """``<drive>:\\网络游戏\\生死狙击2`` on every drive."""
    for root in _drive_roots():
        for subpath in CAFE_SUBPATHS:
            yield os.path.join(root, subpath)


def _conventional_candidates():
    """Other known layouts, on every drive."""
    for root in _drive_roots():
        for subpath in OFFICIAL_SUBPATHS:
            yield os.path.join(root, subpath)


def find_all(refresh: bool = False) -> list[str]:
    """Every install directory found, by any cheap strategy.

    Useful on a shared machine hosting more than one copy.
    """
    if refresh:
        reset_location_cache()
    seen: list[str] = []
    for candidate in (
            *shortcuts.find_all_installs_from_shortcuts(),
            *_cafe_candidates(),
            *_conventional_candidates()):
        if is_install_dir(candidate) and candidate not in seen:
            seen.append(candidate)

    remembered = config.get_install_dir()
    if remembered and is_install_dir(remembered) and remembered not in seen:
        seen.append(remembered)

    return seen


def installer_ini(path) -> dict:
    """Parse the self-describing ``installer.ini`` found in an install dir.

    Example contents::

        [Settings]
        INSTDIR=D:\\Wooduan\\SSJJ2-WD
        REGISTER_KEY=HKEY_LOCAL_MACHINE\\Software\\Wooduan\\SSJJ2-WD
        LNKNAME=生死狙击2

    The file is written by the installer in the system ANSI codepage (GBK on
    a Simplified-Chinese system), not UTF-8, so it is decoded accordingly.

    Returns a mapping of the ``[Settings]`` keys, or ``{}``.
    """
    raw = _read(path, 'installer.ini')
    if raw is None:
        return {}

    text = _decode_ansi(raw)
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('[', ';', '#')):
            continue
        key, sep, value = line.partition('=')
        if sep:
            result[key.strip().lower()] = value.strip()
    return result


def _decode_ansi(raw: bytes) -> str:
    """Decode installer text: UTF-8 when valid, else the ANSI codepage."""
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        pass
    for encoding in ('gbk', 'mbcs', 'latin-1'):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='replace')


def reset_location_cache() -> None:
    """Forget the cached install directory."""
    global _location, _location_resolved
    _location, _location_resolved = None, False


# --- writing ----------------------------------------------------------------

def _require_install(path) -> str:
    path = path or locate()
    if not path:
        raise InstallNotFoundError(
            f'{LAUNCHER.name} not found; cannot locate the install directory. '
            f'Use --path to specify it explicitly.')
    return path


def _resolve(channel) -> Channel:
    """Accept a Channel, a key, or a registry index."""
    if isinstance(channel, Channel):
        return channel
    if isinstance(channel, str):
        return CHANNELS.require(channel)
    if isinstance(channel, int) and not isinstance(channel, bool):
        try:
            return CHANNELS[channel]
        except IndexError:
            raise BT2FusionError(
                f'no channel at index {channel}') from None
    raise TypeError(
        f'expected Channel, str or int; got {type(channel).__name__}')


def ensure_configs(path=None, channel=None) -> Channel:
    """Guarantee a usable config pair, repairing it when absent.

    The only detection-adjacent function that writes. Returns the channel now
    configured.
    """
    path = _require_install(path)

    xml, ini = _read_configs(path)
    if xml is not None and ini is not None:
        found = detect_from_config(path)
        if found is not None:
            return found

    if channel is None:
        # The log is per-install and reflects real usage, so it outranks the
        # registry, which is machine-global and can be left over from a
        # previous install or user.
        channel = (detect_from_log(path)
                   or detect_from_registry()
                   or CHANNELS.require(DEFAULT_CHANNEL))
    resolved = _resolve(channel)

    _write(path, XML_NAME, resolved.xml)
    _write(path, INI_NAME, resolved.ini)
    return resolved


def rewrite(channel, path=None) -> Channel:
    """Write ``channel``'s config pair into the install directory."""
    path = _require_install(path)
    resolved = _resolve(channel)
    _write(path, XML_NAME, resolved.xml)
    _write(path, INI_NAME, resolved.ini)
    return resolved


def launch(path=None):
    """Start the game via its launcher."""
    path = _require_install(path)
    target = os.path.join(path, LAUNCHER.name)
    if not os.path.isfile(target):
        raise InstallNotFoundError(f'launcher missing: {target}')
    os.startfile(target)
