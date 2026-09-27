"""Tests for the channel registry and bundled profile data."""

import pytest

from bt2fusion import CHANNELS, Channel, UnknownChannelError, profiles


def test_channel_list_is_a_real_sequence():
    """The registry must behave like the list it subclasses.

    The original ``Channels(list)`` never called ``list.__init__``, so
    ``len()`` was 0 and iteration yielded nothing.
    """
    assert len(CHANNELS) == 7
    assert [c.key for c in CHANNELS] == [
        'official', 'netbar', 'bilibili', '4399', 'lenovo', 'douyu', 'beta']
    assert CHANNELS[0].key == 'official'
    assert 'official' in CHANNELS.keys()  # noqa: SIM118 - custom keys()
    assert isinstance(CHANNELS[0], Channel)
    assert isinstance(CHANNELS, list)


def test_labels_match_order():
    """Labels are derived from the registry, so they cannot drift."""
    assert len(CHANNELS.labels) == len(CHANNELS)
    for channel, label in zip(CHANNELS, CHANNELS.labels, strict=True):
        assert label == channel.label


def test_every_channel_has_a_display_name():
    """The GUI shows these; a missing name would render as a bare key."""
    for channel in CHANNELS:
        assert channel.name, f'{channel.key} has no display name'
        assert channel.label == channel.name


def test_display_names_are_unique():
    names = [c.label for c in CHANNELS]
    assert len(names) == len(set(names))


def test_labels_are_localised():
    """The audience reads Chinese; the labels must not be raw keys."""
    assert CHANNELS.require('official').label == '官方'
    assert CHANNELS.require('bilibili').label == 'B站'
    assert CHANNELS.require('beta').label == '体验服'
    assert CHANNELS.require('netbar').label == '网吧'


def test_official_and_beta_share_channel_id():
    """Both report id 1; only their config blobs differ."""
    shared = CHANNELS.get_from_id(1)
    assert {c.key for c in shared} == {'official', 'beta'}
    assert CHANNELS.get_from_id(6) == [CHANNELS.require('4399')]
    assert CHANNELS.get_from_id(5) == []


def test_get_from_platform():
    assert CHANNELS.get_from_platform('p4399').key == '4399'
    assert CHANNELS.get_from_platform('P4399').key == '4399'
    assert CHANNELS.get_from_platform('nope') is None
    assert CHANNELS.get_from_platform('') is None
    assert CHANNELS.get_from_platform(None) is None


def test_require_raises_on_unknown_channel():
    with pytest.raises(UnknownChannelError):
        CHANNELS.require('wegame')
    # KeyError subclasses print with quotes; __str__ makes it readable.
    assert 'wegame' in str(UnknownChannelError('unknown channel wegame'))


def test_every_channel_has_an_id_and_unique_key():
    keys = [c.key for c in CHANNELS]
    assert len(keys) == len(set(keys))
    for channel in CHANNELS:
        assert isinstance(channel.channel_id, int)
        assert channel.channel_id > 0


@pytest.mark.parametrize('key', ['official', 'netbar', 'beta', 'bilibili',
                                 '4399', 'lenovo', 'douyu'])
def test_profile_loads_and_is_nonempty(key):
    xml, ini = profiles.load_profile(key)
    assert isinstance(xml, bytes) and xml
    assert isinstance(ini, bytes) and ini
    assert len(xml) % 8 == 0, 'config is 8-byte block aligned'
    assert len(ini) % 8 == 0


def test_profiles_are_all_distinct():
    """No two channels may ship identical config pairs."""
    seen = {}
    for channel in CHANNELS:
        key = (channel.xml, channel.ini)
        assert key not in seen, (
            f'{channel.key} has the same config as {seen[key]}')
        seen[key] = channel.key


def test_official_and_beta_differ_only_by_config():
    official = CHANNELS.require('official')
    beta = CHANNELS.require('beta')
    assert official.channel_id == beta.channel_id
    assert official.xml != beta.xml


def test_netbar_ini_is_plaintext():
    """The one unencrypted profile documents the ini format."""
    _xml, ini = profiles.load_profile('netbar')
    assert ini == b'[channel]\r\nsub_channel_id=8192\r\n'
    assert b'sub_channel_id' in ini


def test_matches_requires_both_blobs():
    channel = CHANNELS.require('official')
    assert channel.matches(channel.xml, channel.ini)
    # None means "file absent" and must never match.
    assert not channel.matches(None, channel.ini)
    assert not channel.matches(channel.xml, None)
    assert not channel.matches(None, None)
    assert not channel.matches(channel.xml, b'nope')


def test_unknown_profile_raises():
    with pytest.raises(profiles.ProfileError):
        profiles.load_profile('does-not-exist')


def test_xml_blobs_share_a_common_header():
    """All profiles begin with the same 64-byte header (format evidence)."""
    headers = {c.xml[:64] for c in CHANNELS}
    assert len(headers) == 1


def test_profile_blobs_are_8_byte_block_aligned():
    """Rules out a 16-byte block cipher like AES for these files."""
    lengths = {len(c.xml) for c in CHANNELS} | {len(c.ini) for c in CHANNELS}
    assert all(length % 8 == 0 for length in lengths)


def test_available_profiles_lists_only_directories():
    """Non-directory files in the profiles folder must be ignored.

    A provenance README sits alongside the profile directories; treating it
    as a profile would yield a channel named 'README.md'.
    """
    found = profiles.available_profiles()
    assert set(found) == {c.key for c in CHANNELS}
    assert all('.' not in name for name in found)


def test_every_registered_channel_has_profile_data():
    """A channel with no data would fail only when first used."""
    for channel in CHANNELS:
        xml, ini = profiles.load_profile(channel.key)
        assert xml and ini, f'{channel.key} has empty profile data'


def test_profile_data_provenance_is_documented():
    """The profile data is redistributed third-party data, not ours.

    It comes from cloud-drive links shared by a Bilibili creator, so the
    attribution must ship alongside the files themselves.
    """
    from importlib import resources

    notice = resources.files('bt2fusion').joinpath(
        'data/profiles/README.md')
    assert notice.is_file(), 'profile provenance notice is missing'
    text = notice.read_text(encoding='utf-8')
    assert 'BV1NZ421m7Qy' in text, 'the source video is not cited'
    assert '考官家恒' in text, 'the original uploader is not credited'
