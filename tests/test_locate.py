"""Tests for install-directory discovery.

The primary use case is a player at an internet cafe: a machine they have
never used, where the game sits in the shared 网维大师/云更新 layout
``<drive>:\\网络游戏\\生死狙击2``. Nothing is remembered on such a machine,
so the cafe layout must be found without any stored state.
"""

import os

import pytest

from bt2fusion import config, game, is_install_dir
from bt2fusion.channels import LAUNCHER


def _make_install(root, subpath):
    """Create a fake install at ``root/subpath`` and return the path."""
    path = os.path.join(root, subpath)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, LAUNCHER.name), 'wb') as handle:
        handle.write(b'MZ fake launcher')
    return path


# --- the cafe layout --------------------------------------------------------

def test_finds_cafe_layout(fake_drives):
    """<drive>:\\网络游戏\\生死狙击2 is the cafe layout and top priority."""
    roots = fake_drives({'D': 100})
    expected = _make_install(roots['D'], game.CAFE_SUBPATHS[0])

    assert game.locate(refresh=True) == expected


def test_finds_cafe_layout_on_a_non_system_drive(fake_drives):
    """Cafe machines often put games on a drive other than C:."""
    roots = fake_drives({'C': 200, 'E': 50})
    _make_install(roots['C'], 'Windows')
    expected = _make_install(roots['E'], game.CAFE_SUBPATHS[0])

    assert game.locate(refresh=True) == expected


def test_cafe_layout_wins_over_remembered_dir(fake_drives, tmp_path):
    """A stale remembered path must not shadow the cafe layout.

    On a shared or diskless machine a remembered directory from a previous
    machine is common, while the cafe layout is authoritative.
    """
    roots = fake_drives({'C': 200, 'D': 100})
    stale = _make_install(str(tmp_path), 'stale-install')
    config.set_install_dir(stale)

    expected = _make_install(roots['D'], game.CAFE_SUBPATHS[0])
    assert game.locate(refresh=True) == expected


def test_cafe_layout_wins_over_official_layout(fake_drives):
    """When both exist, prefer the cafe one."""
    roots = fake_drives({'D': 100})
    _make_install(roots['D'], game.OFFICIAL_SUBPATHS[0])
    expected = _make_install(roots['D'], game.CAFE_SUBPATHS[0])

    assert game.locate(refresh=True) == expected


# --- fallbacks --------------------------------------------------------------

def test_finds_official_layout_as_fallback(fake_drives):
    roots = fake_drives({'D': 100})
    expected = _make_install(roots['D'], game.OFFICIAL_SUBPATHS[0])

    assert game.locate(refresh=True) == expected


def test_falls_back_to_remembered_dir(fake_drives, tmp_path):
    """With no conventional layout, the remembered path is used."""
    fake_drives({'C': 200})
    remembered = _make_install(str(tmp_path), 'my-install')
    config.set_install_dir(remembered)

    assert game.locate(refresh=True) == remembered


def test_ignores_remembered_dir_that_no_longer_exists(fake_drives, tmp_path):
    fake_drives({'C': 200})
    config.set_install_dir(str(tmp_path / 'gone'))

    assert game.locate(refresh=True) is None


def test_returns_none_when_absent(fake_drives):
    fake_drives({'C': 200})
    # find_file is stubbed to return None by the autouse fixture.
    assert game.locate(refresh=True) is None


def test_falls_back_to_full_scan(fake_drives, monkeypatch):
    """The whole-disk scan is the last resort."""
    fake_drives({'C': 200})
    monkeypatch.setattr(game.fsutil, 'find_file',
                        lambda *a, **k: r'X:\somewhere\SSJJ2')

    assert game.locate(refresh=True) == r'X:\somewhere\SSJJ2'


def test_directory_without_launcher_is_not_an_install(fake_drives):
    """The 网络游戏 directory alone is not enough; the launcher must be there."""
    roots = fake_drives({'D': 100})
    path = os.path.join(roots['D'], game.CAFE_SUBPATHS[0])
    os.makedirs(path)

    assert not is_install_dir(path)


# --- caching ----------------------------------------------------------------

def test_locate_result_is_cached(fake_drives, monkeypatch):
    roots = fake_drives({'D': 100})
    expected = _make_install(roots['D'], game.CAFE_SUBPATHS[0])

    assert game.locate(refresh=True) == expected

    # Remove the install; a cached answer must still be returned.
    os.remove(os.path.join(expected, LAUNCHER.name))
    assert game.locate() == expected


def test_reset_location_cache_clears_it(fake_drives):
    roots = fake_drives({'D': 100})
    expected = _make_install(roots['D'], game.CAFE_SUBPATHS[0])
    game.locate(refresh=True)

    os.remove(os.path.join(expected, LAUNCHER.name))
    game.reset_location_cache()
    assert game.locate() is None


# --- find_all ---------------------------------------------------------------

def test_find_all_reports_every_copy(fake_drives):
    """A shared machine may host more than one copy."""
    roots = fake_drives({'C': 200, 'D': 100})
    cafe = _make_install(roots['D'], game.CAFE_SUBPATHS[0])
    official = _make_install(roots['C'], game.OFFICIAL_SUBPATHS[0])

    found = game.find_all(refresh=True)
    assert cafe in found
    assert official in found


def test_find_all_empty(fake_drives):
    fake_drives({'C': 200})
    assert game.find_all(refresh=True) == []


# --- drive ordering ---------------------------------------------------------

def test_busiest_drive_is_searched_first(fake_drives):
    """Games normally live on the fullest drive, so check it first."""
    roots = fake_drives({'C': 20, 'D': 300})
    _make_install(roots['D'], game.CAFE_SUBPATHS[0])
    assert game._drive_roots()[0] == roots['D']


def test_drive_roots_probes_when_disk_info_unavailable(monkeypatch):
    def boom():
        raise OSError('no disk info')

    monkeypatch.setattr(game.fsutil, 'get_disk_used', boom)
    roots = game._drive_roots()
    assert isinstance(roots, list)
    assert all(root.endswith(':\\') for root in roots)


@pytest.mark.parametrize('subpath', game.CAFE_SUBPATHS)
def test_each_cafe_subpath_is_honoured(fake_drives, subpath):
    roots = fake_drives({'D': 100})
    expected = _make_install(roots['D'], subpath)
    assert game.locate(refresh=True) == expected
