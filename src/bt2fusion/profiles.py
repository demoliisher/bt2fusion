"""Access to the bundled channel profile data.

Channel profiles live as ordinary files under ``bt2fusion/data/profiles/``
rather than as a generated Python literal. That keeps ~50 KB of binary data
out of the source tree, makes the files diffable and replaceable, and removes
any need for a code-generation step.
"""

from __future__ import annotations

from functools import cache
from importlib import resources

from .errors import ProfileError

__all__ = [
    'INI_FILENAME',
    'XML_FILENAME',
    'available_profiles',
    'load_profile',
]

XML_FILENAME = 'platform.xml'
INI_FILENAME = 'platform_exm.ini'
FILENAMES = (XML_FILENAME, INI_FILENAME)

_ROOT = 'data/profiles'


def _profile_dir(name: str):
    """Traversable for one channel's profile directory."""
    return resources.files('bt2fusion').joinpath(_ROOT).joinpath(name)


def available_profiles() -> list[str]:
    """Names of every bundled profile directory, sorted."""
    root = resources.files('bt2fusion').joinpath(_ROOT)
    try:
        return sorted(
            entry.name for entry in root.iterdir() if entry.is_dir())
    except (FileNotFoundError, NotADirectoryError):
        return []


@cache
def load_profile(name: str) -> tuple[bytes, bytes]:
    """Return ``(platform.xml, platform_exm.ini)`` bytes for ``name``.

    Results are cached; the files only change when the package is updated.
    """
    directory = _profile_dir(name)
    blobs = []
    for filename in FILENAMES:
        target = directory.joinpath(filename)
        try:
            blobs.append(target.read_bytes())
        except (FileNotFoundError, NotADirectoryError, OSError) as exc:
            raise ProfileError(
                f'profile {name!r} is missing {filename} ({exc})') from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise ProfileError(
                f'could not read {filename} for profile {name!r}: {exc}'
            ) from exc
    return blobs[0], blobs[1]
