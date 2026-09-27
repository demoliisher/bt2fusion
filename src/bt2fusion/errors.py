"""Exception hierarchy for BT2 Fusion."""

__all__ = [
    'BT2FusionError',
    'InstallNotFoundError',
    'ProfileError',
    'UnknownChannelError',
]


class BT2FusionError(Exception):
    """Base class for every error raised by this package."""


class InstallNotFoundError(BT2FusionError, FileNotFoundError):
    """The game install directory could not be located."""


class UnknownChannelError(BT2FusionError, KeyError):
    """A channel was requested by a name or index that does not exist."""

    def __str__(self) -> str:  # KeyError reprs its message; make it readable.
        return ' '.join(str(arg) for arg in self.args)


class ProfileError(BT2FusionError):
    """A channel profile is missing or unreadable."""
