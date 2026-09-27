"""Capture a top-level window by title, for visual verification.

Finds the window through the Win32 API rather than guessing screen
coordinates, so captures stay correct regardless of where the window lands
or which window has focus.

Writes PNG using only the standard library, so it needs no image package.
That matters here: Pillow must not be present in the build environment, and
a dev tool is not a good reason to reintroduce it.

Usage:
    python tools/capture_window.py "<window title substring>" out.png
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import sys
import zlib

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.SetProcessDPIAware()


def find_window(title_part: str) -> int | None:
    """Handle of the first visible top-level window whose title matches."""
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if title_part.lower() in buf.value.lower():
            matches.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return matches[0] if matches else None


def capture(hwnd: int, path: str) -> tuple[int, int]:
    """Screenshot just the given window, including its frame."""
    rect = wt.RECT()
    # DwmGetWindowAttribute(9 = EXTENDED_FRAME_BOUNDS) excludes the drop
    # shadow that GetWindowRect includes.
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wt.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect))
    except Exception:
        user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect))

    width = rect.right - rect.left
    height = rect.bottom - rect.top

    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(memdc, bitmap)
    # PW_RENDERFULLCONTENT (2) captures composited content reliably.
    user32.PrintWindow(hwnd, memdc, 2)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG),
                    ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                    ('biBitCount', wt.WORD), ('biCompression', wt.DWORD),
                    ('biSizeImage', wt.DWORD), ('biXPelsPerMeter', wt.LONG),
                    ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                    ('biClrImportant', wt.DWORD)]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0

    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memdc, bitmap, 0, height, buf, ctypes.byref(header), 0)

    _write_png(path, width, height, buf.raw)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return width, height


def _write_png(path: str, width: int, height: int, bgra: bytes) -> None:
    """Write 32-bit BGRA pixels as a minimal PNG, standard library only."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type: none
        row = bgra[y * stride:(y + 1) * stride]
        # BGRA -> RGB
        raw.extend(bytes(c for i in range(0, len(row), 4)
                         for c in (row[i + 2], row[i + 1], row[i])))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack('>I', len(payload)) + tag + payload
                + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', header)
           + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as handle:
        handle.write(png)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    title, out = sys.argv[1], sys.argv[2]
    hwnd = find_window(title)
    if hwnd is None:
        print(f'no window matching {title!r}')
        return 1
    size = capture(hwnd, out)
    print(f'captured {size[0]}x{size[1]} -> {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
