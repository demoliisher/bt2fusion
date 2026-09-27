"""The channel registry.

A *channel* is one switchable login provider. Most map one-to-one onto the
``channel_id`` the game records, but ``official`` and ``beta`` share id 1 and
differ only in their config blobs, so a channel is identified by the pair
``(channel_id, variant)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import profiles
from .errors import UnknownChannelError

__all__ = ['CHANNELS', 'Channel', 'Channels', 'Launcher']

#: Name of the game's launcher executable.
LAUNCHER_NAME = 'WDlauncher.exe'


@dataclass(frozen=True)
class Launcher:
    """The game launcher."""

    name: str = LAUNCHER_NAME


@dataclass
class Channel:
    """One switchable login channel.

    Attributes:
        key: stable lowercase identifier, used on the command line and as the
            profile directory name.
        channel_id: the id the game reports as ``channel_id_`` and stores in
            the registry.
        name: human-readable name shown in the GUI. Chinese, because the
            audience is Chinese players who know these channels by their
            Chinese names.
        variant: disambiguates channels sharing a ``channel_id``.
        platform: the registry ``Platform`` token, when known (``p4399``).
        sub_channel_id: the ``sub_channel_id`` ini value, when known.
    """

    key: str
    channel_id: int
    name: str = ''
    variant: int = 0
    platform: str | None = None
    sub_channel_id: int | None = None
    _xml: bytes | None = field(default=None, repr=False, compare=False)
    _ini: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def label(self) -> str:
        """Display name shown to the player."""
        return self.name or self.key

    @property
    def xml(self) -> bytes:
        """Contents of ``platform.xml`` for this channel."""
        self._ensure_loaded()
        return self._xml  # type: ignore[return-value]

    @property
    def ini(self) -> bytes:
        """Contents of ``platform_exm.ini`` for this channel."""
        self._ensure_loaded()
        return self._ini  # type: ignore[return-value]

    def _ensure_loaded(self) -> None:
        if self._xml is None or self._ini is None:
            self._xml, self._ini = profiles.load_profile(self.key)

    def matches(self, xml: bytes | None, ini: bytes | None) -> bool:
        """True when both blobs are byte-identical to this channel's.

        ``None`` means "that file was absent", and never matches.
        """
        if xml is None or ini is None:
            return False
        return self.xml == xml and self.ini == ini

    def __repr__(self) -> str:
        return (f'Channel(key={self.key!r}, channel_id={self.channel_id}, '
                f'variant={self.variant})')


class Channels(list):
    """Ordered registry of every supported channel.

    Subclasses ``list`` and is genuinely populated, so ``len()``, iteration,
    indexing, membership and slicing all behave normally.
    """

    def get_from_id(self, channel_id: int) -> list[Channel]:
        """Every channel reporting ``channel_id`` (may be empty or multiple)."""
        return [c for c in self if c.channel_id == channel_id]

    def get(self, key: str) -> Channel | None:
        """Look up a channel by key, or ``None``."""
        for channel in self:
            if channel.key == key:
                return channel
        return None

    def get_from_platform(self, platform: str) -> Channel | None:
        """Look up a channel by its registry ``Platform`` token."""
        if not platform:
            return None
        for channel in self:
            if channel.platform and channel.platform.lower() == platform.lower():
                return channel
        return None

    def require(self, key: str) -> Channel:
        """Like :meth:`get`, but raise :class:`UnknownChannelError`."""
        found = self.get(key)
        if found is None:
            raise UnknownChannelError(
                f'unknown channel {key!r}; known: {", ".join(self.keys())}')
        return found

    def keys(self) -> list[str]:
        return [channel.key for channel in self]

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(channel.label for channel in self)


def _build() -> Channels:
    return Channels((
        Channel('official', 1, name='官方'),
        # `netbar` IS the cafe channel: a three-in-one entry (顺网 / 官服 /
        # 易乐玩) that the game launcher switches between internally. A cafe
        # player whose account is on any of those three needs no external
        # switch; the standalone `official` profile coexists and does not
        # conflict with it. Kept as the "网吧"/netbar wording because that is
        # what the launcher and the registry call it.
        Channel('netbar', 2, name='网吧', sub_channel_id=8192),
        Channel('bilibili', 4, name='B站'),
        Channel('4399', 6, name='4399', platform='p4399',
                sub_channel_id=0x6000),
        Channel('lenovo', 8, name='联想', platform='lenovo'),
        Channel('douyu', 9, name='斗鱼', platform='douyu'),
        # Shares channel_id 1 with `official`; distinguished by its config.
        Channel('beta', 1, name='体验服', variant=1),
    ))


#: The default registry. Constructing it does not touch the filesystem.
CHANNELS = _build()

#: Channel assumed when nothing better can be determined.
DEFAULT_CHANNEL = 'official'

#: Name of the game launcher.
LAUNCHER = Launcher()
