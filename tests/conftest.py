"""Shared fixtures."""

import os
import sys

import pytest

# Make ``src/`` importable without an install step.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src'))


@pytest.fixture
def fake_install(tmp_path):
    """A directory that looks like a BT2 install (has the launcher file)."""
    from bt2fusion.channels import LAUNCHER

    (tmp_path / LAUNCHER.name).write_bytes(b'MZ fake launcher')
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """Redirect settings and the location cache into a temp dir per test."""
    from bt2fusion import config, game

    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    game.reset_location_cache()
    config.clear()
    yield
    game.reset_location_cache()


@pytest.fixture(autouse=True)
def no_ambient_state(monkeypatch):
    """Hide the host machine's registry, shortcuts and whole-disk scan.

    Without this the tests would pick up whatever channel and install
    directory the machine running them happens to have -- including a real
    desktop shortcut. ``find_file`` is stubbed so no test walks the real
    filesystem.
    """
    from bt2fusion import fsutil, game, shortcuts

    monkeypatch.setattr(game, 'read_registry_channel', lambda: (None, None))
    monkeypatch.setattr(fsutil, 'find_file', lambda *a, **k: None)
    # No shortcuts by default; shortcut tests point this at a temp dir.
    monkeypatch.setattr(shortcuts, 'shortcut_dirs', lambda: [])


@pytest.fixture
def no_real_install(monkeypatch):
    """Force ``locate`` to report "not found".

    For tests that assert behaviour when the game is absent. Kept separate
    from :func:`no_ambient_state` so locator tests can drive the real
    ``locate`` against simulated drives.
    """
    from bt2fusion import game

    monkeypatch.setattr(game, 'locate', lambda *a, **k: None)


@pytest.fixture
def fake_drives(monkeypatch, tmp_path):
    """Simulate drives so ``locate`` can be exercised without touching disk.

    ``make({'D': 100, 'C': 20})`` creates one temp directory per drive and
    makes ``fsutil.get_disk_used`` report them, keyed by those real temp
    paths (so the paths ``locate`` builds are creatable). Returns a mapping
    of drive label to its directory.
    """
    from bt2fusion import fsutil

    def make(usage: dict):
        roots = {}
        reported = {}
        for label, used in usage.items():
            path = tmp_path / f'drive_{label}'
            path.mkdir(parents=True, exist_ok=True)
            roots[label] = str(path)
            reported[str(path)] = used
        monkeypatch.setattr(fsutil, 'get_disk_used', lambda: dict(reported))
        return roots

    return make
