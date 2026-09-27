"""BT2 Fusion -- switch the login channel of 生死狙击2 (国服).

The game chooses which login method to present from two small config files in
its install directory, ``platform.xml`` and ``platform_exm.ini``. Except for
the independent Wegame and Steam builds, every channel shares the same client,
so switching channels amounts to swapping those two files.

The primary audience is players at an internet cafe: the client installed
there carries the cafe's own channel, so logging in with a personal account
means replacing that config. :func:`locate` therefore looks for a shortcut,
then the cafe layout (``<drive>:\\网络游戏\\生死狙击2``), before anything else.

Quick start::

    >>> from bt2fusion import CHANNELS, detect, rewrite
    >>> detect().channel
    <Channel 4399>
    >>> rewrite('4399')              # doctest: +SKIP
    <Channel(key='4399', channel_id=6, variant=0)>
"""

from . import channels, config, fsutil, game, profiles, shortcuts
from .channels import CHANNELS, DEFAULT_CHANNEL, LAUNCHER, Channel, Channels
from .config import get_install_dir, set_install_dir
from .errors import (
                     BT2FusionError,
                     InstallNotFoundError,
                     ProfileError,
                     UnknownChannelError,
)
from .game import (
                     DetectedChannel,
                     detect,
                     detect_from_config,
                     detect_from_log,
                     detect_from_registry,
                     ensure_configs,
                     find_all,
                     is_install_dir,
                     launch,
                     locate,
                     read_registry_channel,
                     reset_location_cache,
                     rewrite,
)

#: The single source of truth for the version. ``pyproject.toml`` reads it
#: through hatchling, and ``packaging/build.py`` reads it for the exe metadata.
__version__ = '1.0.0'

__all__ = [
                     'CHANNELS',
                     'DEFAULT_CHANNEL',
                     'LAUNCHER',
                     'BT2FusionError',
                     'Channel',
                     'Channels',
                     'DetectedChannel',
                     'InstallNotFoundError',
                     'ProfileError',
                     'UnknownChannelError',
                     '__version__',
                     'channels',
                     'config',
                     'detect',
                     'detect_from_config',
                     'detect_from_log',
                     'detect_from_registry',
                     'ensure_configs',
                     'find_all',
                     'fsutil',
                     'game',
                     'get_install_dir',
                     'is_install_dir',
                     'launch',
                     'locate',
                     'profiles',
                     'read_registry_channel',
                     'reset_location_cache',
                     'rewrite',
                     'set_install_dir',
                     'shortcuts',
]
