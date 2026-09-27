"""Tests for detection, rewriting and launching."""

import pytest

from bt2fusion import (
    CHANNELS,
    detect,
    detect_from_config,
    detect_from_log,
    ensure_configs,
    errors,
    game,
    is_install_dir,
    rewrite,
)


def _write_configs(path, key):
    channel = CHANNELS.require(key)
    (path / 'platform.xml').write_bytes(channel.xml)
    (path / 'platform_exm.ini').write_bytes(channel.ini)
    return channel


# --- is_install_dir ---------------------------------------------------------

def test_is_install_dir(fake_install, tmp_path):
    assert is_install_dir(fake_install)
    assert not is_install_dir(tmp_path / 'nothing-here')
    assert not is_install_dir('')
    assert not is_install_dir(None)


# --- detect_from_config -----------------------------------------------------

def test_detect_from_config(fake_install):
    _write_configs(fake_install, 'bilibili')
    assert detect_from_config(fake_install).key == 'bilibili'


def test_detect_from_config_missing_files(fake_install):
    assert detect_from_config(fake_install) is None


def test_detect_from_config_unknown_blob(fake_install):
    (fake_install / 'platform.xml').write_bytes(b'\x00' * 64)
    (fake_install / 'platform_exm.ini').write_bytes(b'\x00' * 16)
    assert detect_from_config(fake_install) is None


def test_detect_from_config_uses_ini_when_xml_unknown(fake_install):
    """An unrecognised xml must not stop the ini being matched."""
    (fake_install / 'platform.xml').write_bytes(b'\x00' * 64)
    _write_configs(fake_install, 'netbar')
    (fake_install / 'platform.xml').write_bytes(b'\x00' * 64)
    assert detect_from_config(fake_install).key == 'netbar'


# --- detect_from_log --------------------------------------------------------

def test_detect_from_log_single_id(fake_install):
    (fake_install / 'myeasylog.log').write_text(
        'INFO [default] platform_config_.channel_id_:6\n', encoding='utf-8')
    assert detect_from_log(fake_install).key == '4399'


def test_detect_from_log_takes_the_last_entry(fake_install):
    (fake_install / 'myeasylog.log').write_text(
        'channel_id_:4\nchannel_id_:9\n', encoding='utf-8')
    assert detect_from_log(fake_install).key == 'douyu'


def test_detect_from_log_handles_multi_digit_ids(fake_install):
    """The original regex was anchored to a single digit at end-of-line."""
    (fake_install / 'myeasylog.log').write_text(
        'INFO channel_id_:12\n', encoding='utf-8')
    # id 12 is not registered, but it must not raise.
    assert detect_from_log(fake_install) is None


def test_detect_from_log_unknown_id_does_not_raise(fake_install):
    """Ids 3/5/7 have no channel; the original code raised IndexError."""
    for unknown in ('3', '5', '7', '99'):
        (fake_install / 'myeasylog.log').write_text(
            f'channel_id_:{unknown}\n', encoding='utf-8')
        assert detect_from_log(fake_install) is None


def test_detect_from_log_disambiguates_official_and_beta(fake_install):
    """id 1 maps to two channels; the config blobs break the tie."""
    _write_configs(fake_install, 'beta')
    (fake_install / 'myeasylog.log').write_text('channel_id_:1\n',
                                                encoding='utf-8')
    assert detect_from_log(fake_install).key == 'beta'


def test_detect_from_log_no_file(fake_install):
    assert detect_from_log(fake_install) is None


def test_detect_from_log_empty_file(fake_install):
    (fake_install / 'myeasylog.log').write_text('', encoding='utf-8')
    assert detect_from_log(fake_install) is None


def test_detect_from_log_garbage(fake_install):
    (fake_install / 'myeasylog.log').write_bytes(b'\xff\xfe\x00\x01')
    assert detect_from_log(fake_install) is None


# --- rewrite ----------------------------------------------------------------

def test_rewrite_changes_config(fake_install):
    _write_configs(fake_install, 'official')
    assert detect_from_config(fake_install).key == 'official'

    returned = rewrite('bilibili', path=fake_install)
    assert returned.key == 'bilibili'
    assert detect_from_config(fake_install).key == 'bilibili'


def test_rewrite_accepts_channel_object_and_string(fake_install):
    assert rewrite(CHANNELS.require('douyu'), path=fake_install).key == 'douyu'
    assert rewrite('lenovo', path=fake_install).key == 'lenovo'


def test_rewrite_rejects_bad_input(fake_install):
    with pytest.raises(errors.UnknownChannelError):
        rewrite('wegame', path=fake_install)
    with pytest.raises(TypeError):
        rewrite(3.5, path=fake_install)
    with pytest.raises(errors.BT2FusionError):
        rewrite(999, path=fake_install)


def test_rewrite_without_install_dir_raises(no_real_install):
    with pytest.raises(errors.InstallNotFoundError):
        game.rewrite('official', path=None)


# --- ensure_configs ---------------------------------------------------------

def test_ensure_configs_creates_missing_files(fake_install):
    channel = ensure_configs(fake_install)
    assert channel is not None
    assert (fake_install / 'platform.xml').is_file()
    assert (fake_install / 'platform_exm.ini').is_file()


def test_ensure_configs_repairs_from_log(fake_install):
    (fake_install / 'myeasylog.log').write_text('channel_id_:9\n',
                                                encoding='utf-8')
    assert ensure_configs(fake_install).key == 'douyu'
    assert detect_from_config(fake_install).key == 'douyu'


def test_ensure_configs_leaves_valid_files_alone(fake_install):
    _write_configs(fake_install, '4399')
    before = (fake_install / 'platform.xml').read_bytes()
    assert ensure_configs(fake_install).key == '4399'
    assert (fake_install / 'platform.xml').read_bytes() == before


# --- detect (never writes) --------------------------------------------------

def test_detect_does_not_write(fake_install):
    """Detection is read-only, even when the config is missing."""
    assert not (fake_install / 'platform.xml').exists()
    detect(fake_install)
    assert not (fake_install / 'platform.xml').exists()
    assert not (fake_install / 'platform_exm.ini').exists()


def test_detect_reports_config_channel(fake_install):
    _write_configs(fake_install, 'lenovo')
    result = detect(fake_install)
    assert result.config_channel.key == 'lenovo'
    assert bool(result) is True


def test_detect_on_empty_dir(fake_install):
    result = detect(fake_install)
    assert result.channel is None
    assert bool(result) is False


# --- consistency between config and registry --------------------------------

def test_detected_channel_consistency_logic():
    official = CHANNELS.require('official')
    beta = CHANNELS.require('beta')

    # Config wins over registry, because that is what a switch rewrites.
    result = game.DetectedChannel(config_channel=official,
                                  registry_channel=beta)
    assert result.channel is official
    assert result.consistent is False

    same = game.DetectedChannel(config_channel=official,
                                registry_channel=official)
    assert same.consistent is True

    only_one = game.DetectedChannel(config_channel=official)
    assert only_one.consistent is True
    assert only_one.channel is official

    registry_only = game.DetectedChannel(registry_channel=beta)
    assert registry_only.channel is beta
    assert registry_only.consistent is True

    empty = game.DetectedChannel()
    assert empty.channel is None
    assert bool(empty) is False


# --- installer.ini ----------------------------------------------------------

def test_installer_ini_parsing(fake_install):
    (fake_install / 'installer.ini').write_text(
        '[Settings]\n'
        'INSTDIR=D:\\Wooduan\\SSJJ2-WD\n'
        'REGISTER_KEY=HKEY_LOCAL_MACHINE\\Software\\Wooduan\\SSJJ2-WD\n'
        'LNKNAME=生死狙击2\n',
        encoding='utf-8')
    info = game.installer_ini(fake_install)
    assert info['instdir'] == 'D:\\Wooduan\\SSJJ2-WD'
    assert info['lnkname'] == '生死狙击2'


def test_installer_ini_decodes_gbk(fake_install):
    """The real installer writes ANSI/GBK, not UTF-8.

    Decoding it as UTF-8 turns the game name into mojibake.
    """
    content = ('[Settings]\r\n'
               'INSTDIR=D:\\Wooduan\\SSJJ2-WD\r\n'
               'LNKNAME=生死狙击2\r\n')
    (fake_install / 'installer.ini').write_bytes(content.encode('gbk'))
    info = game.installer_ini(fake_install)
    assert info['lnkname'] == '生死狙击2'
    assert info['instdir'] == 'D:\\Wooduan\\SSJJ2-WD'


def test_installer_ini_missing(fake_install):
    assert game.installer_ini(fake_install) == {}


def test_installer_ini_ignores_comments_and_sections(fake_install):
    (fake_install / 'installer.ini').write_text(
        '; comment\n# another\n[Settings]\nKEY=value\n', encoding='utf-8')
    info = game.installer_ini(fake_install)
    assert info == {'key': 'value'}
