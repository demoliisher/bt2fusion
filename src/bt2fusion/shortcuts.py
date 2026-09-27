"""Discover the game through Windows shortcuts.

Cafes and installers create desktop / Start Menu shortcuts pointing at the
launcher. Those shortcuts are a good signal, but the shortcut *name* is not:
the game ships as both ``生死狙击2`` and the English ``Battle Teams 2``, so
matching filenames misses perfectly valid shortcuts. Shortcuts are therefore
matched by their **target**, which is name-agnostic.

Parsing is dependency-free. A ``.lnk`` stores its target as plain text in one
of several structures (LinkInfo, RelativePath, WorkingDir, ...), so every
plausible string is extracted and each candidate is validated against the real
filesystem before being trusted -- junk from adjacent binary fields fails that
check and is discarded.
"""

from __future__ import annotations

import os
import re

from .channels import LAUNCHER

__all__ = [
    'SHORTCUT_SUBDIRS',
    'find_install_from_shortcuts',
    'iter_shortcuts',
    'shortcut_dirs',
]

#: Start Menu / desktop locations, per user and machine-wide.
SHORTCUT_SUBDIRS = (
    ('APPDATA', r'Microsoft\Windows\Start Menu\Programs'),
    ('PROGRAMDATA', r'Microsoft\Windows\Start Menu\Programs'),
    ('USERPROFILE', 'Desktop'),
    ('PUBLIC', 'Desktop'),
)

#: Printable ASCII runs, used to find paths stored as plain single-byte text.
_ASCII_RUN = re.compile(rb'[\x20-\x7e]{4,}')

#: A Windows absolute path begins with a drive letter. The prefix is also
#: required to be free of control characters, which is what rejects the
#: binary noise produced by decoding a whole ``.lnk`` as text. Backslashes and
#: forward slashes are separators and therefore allowed.
_ABSOLUTE = re.compile(r'^[A-Za-z]:[\\/]')
_PATHLIKE = re.compile(r'^[A-Za-z]:[\\/][^:*?"<>|\x00-\x1f]*$')

#: How deep to recurse when looking for shortcuts.
_MAX_DEPTH = 3


def _env(name: str) -> str | None:
    return os.environ.get(name) or None


def shortcut_dirs() -> list[str]:
    """Existing directories that may hold shortcuts, de-duplicated."""
    found: list[str] = []
    for var, subpath in SHORTCUT_SUBDIRS:
        base = _env(var)
        if not base:
            continue
        path = os.path.join(base, subpath)
        if os.path.isdir(path) and path not in found:
            found.append(path)
    return found


def iter_shortcuts(dirs=None):
    """Yield every ``.lnk`` under the shortcut directories.

    Recursion is bounded, since Start Menu trees can nest deeply.
    """
    for base in (dirs if dirs is not None else shortcut_dirs()):
        base_depth = base.rstrip('\\/').count(os.sep)
        for root, subdirs, files in os.walk(base, onerror=lambda _e: None):
            if root.count(os.sep) - base_depth >= _MAX_DEPTH:
                subdirs[:] = []
            for name in files:
                if name.lower().endswith('.lnk'):
                    yield os.path.join(root, name)


def _strings(raw: bytes) -> list[str]:
    """Text views of a shortcut's bytes, in the encodings ``.lnk`` uses.

    Three views are produced because paths are stored differently depending
    on whether they are ASCII and on which field they live in:

    * printable ASCII runs (covers plain-ASCII paths in any structure);
    * the whole blob decoded as UTF-16LE, which is how non-ASCII paths such
      as ``E:\\网络游戏\\生死狙击2`` are stored -- a byte-oriented scan cannot
      find those, because a CJK code unit has a non-zero high byte;
    * the whole blob decoded as ANSI/GBK, for older shortcuts.

    The decoded views contain binary noise around the real strings, which is
    harmless: candidates are validated against the filesystem afterwards.
    """
    views = [m.group().decode('latin-1') for m in _ASCII_RUN.finditer(raw)]
    for encoding in ('utf-16le', 'gbk'):
        try:
            views.append(raw.decode(encoding, errors='ignore'))
        except (UnicodeDecodeError, LookupError):  # pragma: no cover
            continue
    return views


def _candidates(text: str, target_name: str) -> list[str]:
    """Install directories implied by one string.

    Looks for ``target_name`` and takes the directory prefix. The prefix is
    re-anchored at a drive letter so that any junk from an adjacent binary
    field ahead of the path is dropped, and the result must look like a
    clean path -- a candidate containing control characters is noise from
    decoding a binary structure as text.
    """
    results: list[str] = []
    lowered = text.lower()
    needle = target_name.lower()

    start = 0
    while True:
        index = lowered.find(needle, start)
        if index < 0:
            break
        start = index + len(needle)

        prefix = text[:index]
        match = re.search(r'[A-Za-z]:[\\/][^:*?"<>|\x00-\x1f]*$', prefix)
        if match is None:
            continue
        candidate = match.group().rstrip('\\/')
        if candidate and _PATHLIKE.match(candidate):
            results.append(os.path.normpath(candidate))
    return results


def paths_from_shortcut(path: str) -> list[str]:
    """Candidate install directories embedded in one ``.lnk`` file.

    Candidates are not validated here; see :func:`find_install_from_shortcuts`.
    """
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError:
        return []

    results: list[str] = []
    for text in _strings(raw):
        for candidate in _candidates(text, LAUNCHER.name):
            if _ABSOLUTE.match(candidate) and candidate not in results:
                results.append(candidate)
    return results


def find_install_from_shortcuts(dirs=None) -> str | None:
    """Install directory named by any shortcut, or ``None``.

    Every candidate is checked against the filesystem, so a shortcut whose
    target no longer exists is ignored rather than trusted.
    """
    from .game import is_install_dir

    for shortcut in iter_shortcuts(dirs):
        for candidate in paths_from_shortcut(shortcut):
            if is_install_dir(candidate):
                return candidate
    return None


def find_all_installs_from_shortcuts(dirs=None) -> list[str]:
    """Every distinct install directory named by a shortcut."""
    from .game import is_install_dir

    found: list[str] = []
    for shortcut in iter_shortcuts(dirs):
        for candidate in paths_from_shortcut(shortcut):
            if is_install_dir(candidate) and candidate not in found:
                found.append(candidate)
    return found
