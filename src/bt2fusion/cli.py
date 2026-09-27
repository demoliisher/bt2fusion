"""Command-line interface: ``bt2fusion`` / ``python -m bt2fusion``."""

from __future__ import annotations

import argparse
import sys

from . import __version__, config
from .channels import CHANNELS
from .errors import BT2FusionError
from .game import (
    detect,
    ensure_configs,
    find_all,
    installer_ini,
    is_install_dir,
    launch,
    locate,
    read_registry_channel,
    reset_location_cache,
    rewrite,
)

__all__ = ['build_parser', 'main']


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='bt2fusion',
        description='Switch the login channel of 生死狙击2 (国服).',
    )
    parser.add_argument('--version', action='version',
                        version=f'bt2fusion {__version__}')
    parser.add_argument(
        '-C', '--path', metavar='DIR',
        help='game install directory (default: auto-detect)')

    sub = parser.add_subparsers(dest='command')

    p_status = sub.add_parser('status', help='show the current channel')
    p_status.add_argument('--json', action='store_true',
                          help='emit machine-readable output')

    sub.add_parser('list', help='list every supported channel')

    p_set = sub.add_parser('set', help='switch to another channel')
    p_set.add_argument('channel', help='channel key, e.g. bilibili')
    p_set.add_argument('--no-verify', action='store_true',
                       help='skip the post-write consistency check')

    sub.add_parser('repair', help='recreate missing config files')
    sub.add_parser('launch', help='start the game')
    sub.add_parser('where', help='print the detected install directory')
    sub.add_parser('find', help='list every install directory found')

    p_path = sub.add_parser('set-path', help='remember the install directory')
    p_path.add_argument('dir', help='game install directory')

    sub.add_parser('forget-path', help='forget the remembered directory')
    return parser


def _resolve_path(args) -> str | None:
    if args.path:
        if not is_install_dir(args.path):
            raise BT2FusionError(
                f'{args.path} does not look like a BT2 install directory '
                f'(no launcher found)')
        return args.path
    return locate()


def cmd_status(args) -> int:
    path = _resolve_path(args)
    result = detect(path)
    platform, channel_id = read_registry_channel()

    if args.json:
        import json
        print(json.dumps({
            'channel': result.channel.key if result.channel else None,
            'config_channel': (result.config_channel.key
                               if result.config_channel else None),
            'registry_channel': (result.registry_channel.key
                                 if result.registry_channel else None),
            'consistent': result.consistent,
            'source': result.source,
            'install_dir': path,
            'registry_platform': platform,
            'registry_channel_id': channel_id,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f'install dir : {path or "(not found)"}')
    if result.config_channel:
        print(f'channel     : {result.config_channel.key} '
              f'(id={result.config_channel.channel_id})  [from config files]')
    else:
        print('channel     : unknown')
    if result.registry_channel:
        print(f'registry    : {result.registry_channel.key} '
              f'(platform={platform!r}, channel_id={channel_id})')
    if not result.consistent:
        print('note        : config and registry disagree; the registry '
              'updates when the game is next launched')
    return 0


def cmd_list(args) -> int:
    print(f'{"KEY":<10} {"ID":>3} {"VARIANT":>7} {"PLATFORM":<10}')
    print('-' * 34)
    for channel in CHANNELS:
        print(f'{channel.key:<10} {channel.channel_id:>3} '
              f'{channel.variant:>7} {channel.platform or "-":<10}')
    return 0


def cmd_set(args) -> int:
    path = _resolve_path(args)
    if not path:
        raise BT2FusionError(
            'install directory not found; pass --path DIR to set it')

    requested = CHANNELS.require(args.channel)
    before = detect(path)

    applied = rewrite(requested, path=path)

    if not args.no_verify:
        after = detect(path)
        if after.config_channel is None or \
                after.config_channel.key != applied.key:
            got = (after.config_channel.key if after.config_channel
                   else 'unknown')
            print(f'warning: wrote {applied.key!r} but detected {got!r}',
                  file=sys.stderr)
        elif not after.consistent:
            print(f'note: registry still says '
                  f'{after.registry_channel.key!r}; it updates when the game '
                  f'is next launched')

    was = before.channel.key if before.channel else 'unknown'
    print(f'{was} -> {applied.key}')
    return 0


def cmd_repair(args) -> int:
    path = _resolve_path(args)
    if not path:
        raise BT2FusionError(
            'install directory not found; pass --path DIR to set it')
    channel = ensure_configs(path)
    print(f'config files ensured: {channel.key}')
    return 0


def cmd_launch(args) -> int:
    path = _resolve_path(args)
    if not path:
        raise BT2FusionError(
            'install directory not found; pass --path DIR to set it')
    print(f'launching from {path}')
    launch(path)
    return 0


def cmd_where(args) -> int:
    path = _resolve_path(args)
    if not path:
        print('not found', file=sys.stderr)
        return 1
    print(path)
    info = installer_ini(path)
    if info:
        for key in ('instdir', 'lnkname', 'register_key'):
            if key in info:
                print(f'  {key}: {info[key]}')
    return 0


def cmd_find(args) -> int:
    found = find_all(refresh=True)
    if not found:
        print('no install directory found', file=sys.stderr)
        return 1
    for path in found:
        print(path)
    return 0


def cmd_set_path(args) -> int:
    if not is_install_dir(args.dir):
        raise BT2FusionError(
            f'{args.dir} does not look like a BT2 install directory')
    config.set_install_dir(args.dir)
    reset_location_cache()
    print(f'remembered: {args.dir}')
    return 0


def cmd_forget_path(args) -> int:
    config.clear()
    reset_location_cache()
    print('forgotten')
    return 0


_COMMANDS = {
    'status': cmd_status,
    'list': cmd_list,
    'set': cmd_set,
    'repair': cmd_repair,
    'launch': cmd_launch,
    'where': cmd_where,
    'find': cmd_find,
    'set-path': cmd_set_path,
    'forget-path': cmd_forget_path,
}


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        return _COMMANDS[args.command](args)
    except BT2FusionError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
