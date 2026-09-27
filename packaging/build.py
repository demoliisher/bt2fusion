"""Build a single-file Windows executable with Nuitka.

Nuitka compiles the package to C and links it against CPython, producing a
markedly smaller binary than PyInstaller's archive-based one-file bundle.

Build from a clean Python 3.12 virtual environment. Two things drive the
size, and both are properties of the interpreter rather than of any flag:

* **Do not install Pillow.** CustomTkinter imports it only inside a
  ``try/except ImportError`` and needs it solely for ``CTkImage``, which this
  GUI does not use. If Pillow is present Nuitka compiles PIL's Python layer
  into the binary and bundles its extension modules.
* **Python 3.12 rather than 3.14.** 3.12 ships Tcl/Tk 8.6, 3.14 ships Tk 9.0,
  which is roughly twice the size.

Measured, onefile, identical GUI:

    3.12, no Pillow     8.9 MB
    3.14, no Pillow    12.1 MB   (Tk 9.0 accounts for the difference)
    3.14 + Pillow      16.2 MB

Usage::

    py -3.12 -m venv .venv-build
    .venv-build\\Scripts\\pip install customtkinter nuitka
    .venv-build\\Scripts\\python packaging/build.py --clean

Output: ``dist/bt2fusion.exe`` (windowed, no console).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, 'src')
ENTRY = os.path.join(ROOT, 'packaging', 'launcher.py')
#: Shown in Explorer and on the window title bar.
ICON = os.path.join(ROOT, 'src', 'bt2fusion', 'data', 'favicon.ico')

#: Nuitka names its work directories after the entry script, which is
#: ``launcher.py`` -- hence ``launcher.build``, not ``bt2fusion.build``.
BUILD_DIRS = ('dist', 'launcher.build', 'launcher.dist',
              'launcher.onefile-build')

#: Python version whose Tcl/Tk is small enough to be worth preferring.
PREFERRED_PYTHON = (3, 12)


def project_version() -> str:
    """The version from ``bt2fusion.__version__``, without importing the GUI.

    Read out of the source instead of importing: ``bt2fusion/__init__.py``
    pulls in the whole package, and the build must work from a plain
    checkout with only the dependencies present. Keeping one copy of the
    number is the point -- the exe metadata used to drift from the title bar.
    """
    init = os.path.join(SRC_DIR, 'bt2fusion', '__init__.py')
    with open(init, encoding='utf-8') as handle:
        match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]",
                          handle.read(), re.MULTILINE)
    if not match:
        raise SystemExit(f'could not read __version__ from {init}')
    return match.group(1)


def build_command() -> list[str]:
    version = project_version()
    return [
        sys.executable, '-m', 'nuitka',
        '--mode=onefile',
        '--output-dir=dist',
        '--output-filename=bt2fusion.exe',
        '--assume-yes-for-downloads',
        # Tkinter needs its support files gathered explicitly.
        '--enable-plugin=tk-inter',
        # Resolved from SRC_DIR on PYTHONPATH (see main), not from an
        # installed copy: this project is not distributed as a package, so
        # the build must not depend on having run `pip install`.
        '--include-package=bt2fusion',
        '--include-package-data=bt2fusion',
        # CustomTkinter loads its theme JSON from package data at runtime.
        '--include-package-data=customtkinter',
        '--windows-console-mode=disable',
        f'--windows-icon-from-ico={ICON}',
        '--windows-company-name=bt2fusion',
        '--windows-product-name=BT2 Fusion',
        '--windows-file-description=\u751f\u6b7b\u72d9\u51fb2 \u6e20\u9053\u5207\u6362',
        f'--windows-product-version={version}',
        f'--windows-file-version={version}',
        # Keep test/dev-only modules out of the binary.
        '--nofollow-import-to=pytest',
        '--nofollow-import-to=unittest',
        '--nofollow-import-to=pydoc',
        ENTRY,
    ]


def check_environment(*, force: bool) -> bool:
    """Verify the environment produces the smallest artefact.

    The project is pinned to Python 3.12 and expects no Pillow. Both
    deviations are silent otherwise -- the build succeeds either way, just
    larger -- so they are refused rather than merely warned about. Pass
    ``--force`` to build anyway.

    Returns True when the build may proceed.
    """
    version = sys.version_info[:2]
    problems: list[str] = []

    print(f'building with Python {sys.version.split()[0]}')

    if version != PREFERRED_PYTHON:
        problems.append(
            f'Python {PREFERRED_PYTHON[0]}.{PREFERRED_PYTHON[1]} is required. '
            f'This project is pinned to it because 3.12 ships Tcl/Tk 8.6 '
            f'while 3.13+ ship Tk 9.0, which is about twice the size '
            f'(16.2 MB vs 8.9 MB for an identical GUI).')

    if importlib.util.find_spec('PIL') is not None:
        problems.append(
            'Pillow is installed and would be bundled, adding about 4 MB. '
            'This GUI does not use it. Rebuild from a venv without Pillow.')

    if shutil.which('ccache') is None:
        print('  note: ccache not found; the C compile step will be slower.')

    if problems:
        print()
        for problem in problems:
            print(f'  ERROR: {problem}')
        if not force:
            print('\nRefusing to build. Pass --force to override.\n')
            return False
        print('\n--force given; building anyway.\n')
    else:
        print('  environment OK\n')
    return True


def build_env() -> dict:
    """Environment for the Nuitka subprocess.

    Puts ``src/`` on PYTHONPATH so the package resolves from the working
    tree. The project is a Windows GUI utility, not a library anyone
    installs, so building must work from a plain checkout with only the
    dependencies present.
    """
    env = dict(os.environ)
    existing = env.get('PYTHONPATH')
    env['PYTHONPATH'] = (f'{SRC_DIR}{os.pathsep}{existing}' if existing
                         else SRC_DIR)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', action='store_true',
                        help='remove dist/ and Nuitka build leftovers first')
    parser.add_argument('--force', action='store_true',
                        help='build even if the environment is not pinned '
                             '(produces a larger artefact)')
    args = parser.parse_args()

    os.chdir(ROOT)

    if args.clean:
        for name in BUILD_DIRS:
            shutil.rmtree(os.path.join(ROOT, name), ignore_errors=True)

    if not check_environment(force=args.force):
        return 1

    command = build_command()
    print('running:', ' '.join(command[:6]), '...')
    result = subprocess.run(command, cwd=ROOT, env=build_env())
    if result.returncode != 0:
        return result.returncode

    exe = os.path.join(ROOT, 'dist', 'bt2fusion.exe')
    if os.path.isfile(exe):
        size = os.path.getsize(exe) / (1024 * 1024)
        print(f'\nbuilt {exe}  ({size:.1f} MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
