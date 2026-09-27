"""Tests for shortcut-based install discovery.

Shortcuts are matched by their **target**, never by filename: the game ships
as both ``生死狙击2`` and the English ``Battle Teams 2``, so name matching
misses valid shortcuts.
"""

import os

import pytest

from bt2fusion import game, shortcuts
from bt2fusion.channels import LAUNCHER


def _write_lnk(path, target, extra=b''):
    """Write a minimal .lnk that embeds ``target`` as UTF-16LE text.

    Not a spec-complete shortcut: the parser under test scans for printable
    strings rather than decoding the binary format, so embedding the path is
    enough to exercise it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b'\x4c\x00\x00\x00' + b'\x01\x14\x02\x00\x00\x00\x00\x00'
    body = (target + '\x00').encode('utf-16le')
    path.write_bytes(header + body + extra)


@pytest.fixture
def shortcut_dir(tmp_path, monkeypatch, no_ambient_state):
    """A fake Desktop populated with shortcuts, in place of the real one.

    Depends on ``no_ambient_state`` explicitly so this override is applied
    after the autouse fixture blanks the shortcut directories.
    """
    desktop = tmp_path / 'Desktop'
    desktop.mkdir()
    monkeypatch.setattr(shortcuts, 'shortcut_dirs', lambda: [str(desktop)])
    return desktop


# --- parsing ----------------------------------------------------------------

def test_extracts_target_from_shortcut(tmp_path):
    lnk = tmp_path / 'game.lnk'
    _write_lnk(lnk, r'D:\Wooduan\SSJJ2-WD\WDlauncher.exe')

    assert shortcuts.paths_from_shortcut(str(lnk)) == [r'D:\Wooduan\SSJJ2-WD']


def test_matches_shortcut_regardless_of_name(tmp_path):
    """The English shortcut name must work exactly like the Chinese one.

    This is the bug that made an existing desktop shortcut invisible.
    """
    for name in ('Battle Teams 2.lnk', '生死狙击2.lnk', 'whatever.lnk'):
        lnk = tmp_path / name
        _write_lnk(lnk, r'D:\Wooduan\SSJJ2-WD\WDlauncher.exe')
        assert shortcuts.paths_from_shortcut(str(lnk)) == [r'D:\Wooduan\SSJJ2-WD']


def test_parses_cafe_layout_from_shortcut(tmp_path):
    lnk = tmp_path / 'game.lnk'
    _write_lnk(lnk, r'E:\网络游戏\生死狙击2\WDlauncher.exe')

    assert shortcuts.paths_from_shortcut(str(lnk)) == [r'E:\网络游戏\生死狙击2']


def test_unreadable_shortcut_returns_empty(tmp_path):
    lnk = tmp_path / 'broken.lnk'
    lnk.write_bytes(b'\x00\x01\x02')
    assert shortcuts.paths_from_shortcut(str(lnk)) == []


def test_missing_shortcut_returns_empty(tmp_path):
    assert shortcuts.paths_from_shortcut(str(tmp_path / 'nope.lnk')) == []


# --- validation -------------------------------------------------------------

def test_only_existing_targets_are_accepted(shortcut_dir, tmp_path, fake_install):
    """A shortcut whose target is gone must not be trusted."""
    _write_lnk(shortcut_dir / 'gone.lnk',
               r'Z:\nowhere\WDlauncher.exe')
    assert shortcuts.find_install_from_shortcuts() is None


def test_discovers_via_shortcut(shortcut_dir, fake_install):
    _write_lnk(shortcut_dir / 'Battle Teams 2.lnk',
               os.path.join(str(fake_install), LAUNCHER.name))

    assert shortcuts.find_install_from_shortcuts() == str(fake_install)


def test_ignores_shortcuts_pointing_elsewhere(shortcut_dir, fake_install):
    """Unrelated shortcuts must not produce a false positive."""
    _write_lnk(shortcut_dir / 'Chrome.lnk',
               r'C:\Program Files\Google\Chrome\chrome.exe')
    _write_lnk(shortcut_dir / 'word.lnk', r'C:\Office\WINWORD.EXE')

    assert shortcuts.find_install_from_shortcuts() is None


def test_ignores_directories_without_launcher(shortcut_dir, tmp_path):
    """The target directory must actually contain the launcher."""
    empty = tmp_path / 'empty'
    empty.mkdir()
    _write_lnk(shortcut_dir / 'fake.lnk',
               os.path.join(str(empty), LAUNCHER.name))

    assert shortcuts.find_install_from_shortcuts() is None


def test_finds_all_installs_from_shortcuts(shortcut_dir, tmp_path):
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    for path in (a, b):
        path.mkdir()
        (path / LAUNCHER.name).write_bytes(b'MZ')
    _write_lnk(shortcut_dir / 'one.lnk',
               os.path.join(str(a), LAUNCHER.name))
    _write_lnk(shortcut_dir / 'two.lnk',
               os.path.join(str(b), LAUNCHER.name))

    found = shortcuts.find_all_installs_from_shortcuts()
    assert str(a) in found
    assert str(b) in found


# --- traversal --------------------------------------------------------------

def test_recurses_into_subdirectories(shortcut_dir, fake_install):
    nested = shortcut_dir / 'Some Vendor' / 'Games'
    _write_lnk(nested / 'game.lnk',
               os.path.join(str(fake_install), LAUNCHER.name))

    assert shortcuts.find_install_from_shortcuts() == str(fake_install)


def test_recursion_is_bounded(shortcut_dir, fake_install, monkeypatch):
    """A deep Start Menu tree must not be walked indefinitely."""
    monkeypatch.setattr(shortcuts, '_MAX_DEPTH', 1)
    deep = shortcut_dir / 'a' / 'b' / 'c' / 'd'
    _write_lnk(deep / 'game.lnk',
               os.path.join(str(fake_install), LAUNCHER.name))

    assert shortcuts.find_install_from_shortcuts() is None


def test_iter_shortcuts_finds_lnk_files(shortcut_dir):
    _write_lnk(shortcut_dir / 'a.lnk', r'D:\x\WDlauncher.exe')
    (shortcut_dir / 'notes.txt').write_text('ignore me')

    names = [os.path.basename(p) for p in shortcuts.iter_shortcuts()]
    assert names == ['a.lnk']


# --- integration with locate ------------------------------------------------

def test_locate_prefers_shortcut(shortcut_dir, fake_install, fake_drives):
    """A shortcut is the cheapest signal, so locate() uses it first."""
    _write_lnk(shortcut_dir / 'game.lnk',
               os.path.join(str(fake_install), LAUNCHER.name))
    # A cafe install also exists; the shortcut should still win.
    roots = fake_drives({'D': 100})
    cafe = os.path.join(roots['D'], game.CAFE_SUBPATHS[0])
    os.makedirs(cafe)
    (__import__('pathlib').Path(cafe) / LAUNCHER.name).write_bytes(b'MZ')

    assert game.locate(refresh=True) == str(fake_install)


def test_locate_uses_shortcut_dir_directly(shortcut_dir, fake_install):
    """The shortcut path is returned with no drive scanning at all."""
    _write_lnk(shortcut_dir / '生死狙击2.lnk',
               os.path.join(str(fake_install), LAUNCHER.name))

    assert game.locate(refresh=True) == str(fake_install)
