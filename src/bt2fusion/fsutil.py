"""Windows filesystem helpers: enumerating drives and locating files."""

from __future__ import annotations

import ctypes
import os
import string

__all__ = ['find_file', 'get_disk_used']


def get_disk_used() -> dict[str, float]:
    """Map each ready drive root to its used space in GiB.

    Drives that are present but not ready (empty optical drives, disconnected
    card readers) are skipped rather than raising.
    """
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()

    used: dict[str, float] = {}
    for index, letter in enumerate(string.ascii_uppercase):
        if not (bitmask >> index) & 1:
            continue

        drive = f'{letter}:\\'
        try:
            free = ctypes.c_ulonglong(0)
            total = ctypes.c_ulonglong(0)
            ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(drive),
                None,
                ctypes.pointer(total),
                ctypes.pointer(free),
            )
        except OSError:
            continue

        if not ok:
            continue

        used[drive] = (total.value - free.value) / (1024 ** 3)

    return used


def find_file(filename: str, min_used_gb: float = 40.0):
    """Search every drive for ``filename`` and return its directory.

    This walks the entire filesystem, so it is slow and should only be used
    as a last resort. Drives holding less than ``min_used_gb`` are skipped as
    an optimisation, since the game needs far more space than that.

    Returns ``None`` when the file is not found.
    """
    # Reversed so the system disk, typically enumerated first, is scanned last.
    for root, used in reversed(get_disk_used().items()):
        if used < min_used_gb:
            continue
        for directory, _subdirs, files in os.walk(root, onerror=lambda _e: None):
            if filename in files:
                return directory

    return None
