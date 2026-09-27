"""Compare Nuitka build modes and options by output size.

Each build lands in its own directory so results can be compared side by side.
Runs sequentially because Nuitka builds are CPU-heavy.

Usage:
    python tools/compare_builds.py            # all variants
    python tools/compare_builds.py onefile lto   # selected variants
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, 'packaging', 'launcher.py')
OUT = os.path.join(ROOT, 'build-compare')

BASE = [
    sys.executable, '-m', 'nuitka',
    '--assume-yes-for-downloads',
    '--enable-plugin=tk-inter',
    '--include-package=bt2fusion',
    '--include-package-data=bt2fusion',
    '--include-package-data=customtkinter',
    '--windows-console-mode=disable',
    '--nofollow-import-to=pytest',
    '--nofollow-import-to=unittest',
    '--nofollow-import-to=pydoc',
]

#: name -> extra flags.
#:
#: Note: ``--lto=yes`` is deliberately absent -- it fails on this toolchain
#: (Python 3.14 + Nuitka's bundled zig/lld-link) with undefined symbols such
#: as __QNAN, so it cannot be measured here.
VARIANTS = {
    'onefile': ['--mode=onefile'],
    'standalone': ['--mode=standalone'],
    'onefile-nodoc': ['--mode=onefile', '--python-flag=no_docstrings'],
    'onefile-noassert': ['--mode=onefile', '--python-flag=no_asserts'],
    'onefile-lean': [
        '--mode=onefile',
        '--python-flag=no_docstrings',
        '--python-flag=no_asserts',
        '--python-flag=no_site',
        '--nofollow-import-to=doctest',
        '--nofollow-import-to=pdb',
        '--nofollow-import-to=sqlite3',
        '--nofollow-import-to=unittest',
    ],
}


def build(name: str, extra: list[str]) -> tuple[float, int | None, str]:
    dest = os.path.join(OUT, name)
    shutil.rmtree(dest, ignore_errors=True)
    command = [
        *BASE,
        f'--output-dir={dest}',
        '--output-filename=bt2fusion.exe',
        *extra,
        ENTRY,
    ]
    start = time.time()
    result = subprocess.run(command, cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    elapsed = time.time() - start

    exe = os.path.join(dest, 'bt2fusion.exe')
    size = os.path.getsize(exe) if os.path.isfile(exe) else None
    status = 'ok' if size else f'FAILED rc={result.returncode}'
    return elapsed, size, status


def main() -> int:
    names = sys.argv[1:] or list(VARIANTS)
    os.chdir(ROOT)
    os.makedirs(OUT, exist_ok=True)

    rows = []
    for name in names:
        extra = VARIANTS.get(name)
        if extra is None:
            print(f'skip unknown variant {name!r}')
            continue
        print(f'building {name} ...', flush=True)
        elapsed, size, status = build(name, extra)
        rows.append((name, size, elapsed, status))
        mb = f'{size/1024/1024:.2f} MB' if size else '-'
        print(f'  {name}: {mb}  ({elapsed:.0f}s)  {status}', flush=True)

    print('\n=== summary ===')
    for name, size, elapsed, status in sorted(
            rows, key=lambda r: (r[1] is None, r[1] or 0)):
        mb = f'{size/1024/1024:7.2f} MB' if size else '        -   '
        print(f'  {name:<22} {mb}  {elapsed:5.0f}s  {status}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
