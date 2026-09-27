"""Frozen-build entry point: always open the GUI.

The console script ``bt2fusion`` runs the CLI, but a windowed executable has
no console to print to, so the frozen build opens the GUI instead. Pass
``--cli`` to force the command-line interface (useful with a console build).
"""

import sys


def main() -> int:
    if '--cli' in sys.argv[1:]:
        argv = [a for a in sys.argv[1:] if a != '--cli']
        from bt2fusion.cli import main as cli_main
        return cli_main(argv)

    try:
        from bt2fusion.gui import main as gui_main
    except ImportError as exc:  # pragma: no cover - depends on build extras
        print(f'GUI unavailable ({exc}); falling back to the CLI.',
              file=sys.stderr)
        from bt2fusion.cli import main as cli_main
        return cli_main(sys.argv[1:])

    return gui_main(sys.argv[1:])


if __name__ == '__main__':
    sys.exit(main())
