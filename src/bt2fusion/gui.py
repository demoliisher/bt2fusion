"""The BT2 Fusion GUI.

Designed for a player who does not know what a config file is: it detects the
game, shows which channel is active, and switches with one click.

Built on CustomTkinter. The window is a single centred card on a tinted page,
with one obvious primary action (launch) and one secondary action (switch).
Labels are Chinese, because the audience knows these channels by their
Chinese names.
"""

from __future__ import annotations

import contextlib
import os
import sys

import customtkinter as ctk

from . import __version__, config
from .channels import CHANNELS
from .errors import BT2FusionError
from .game import (
    detect,
    ensure_configs,
    is_install_dir,
    launch,
    locate,
    reset_location_cache,
    rewrite,
)

__all__ = ['PALETTE', 'App', 'main']

#: Sized to the content. Note that ``winfo_height()`` excludes the ``pady``
#: applied by ``pack``, so measuring only widget boxes understates the real
#: bottom edge; this was settled by looking at the rendered window instead.
WINDOW_SIZE = (460, 380)

#: Colour roles. A single accent keeps the window calm; the launch button is
#: the only saturated element, so it reads as the primary action.
PALETTE = {
    'page': '#EEF1F6',
    'card': '#FFFFFF',
    'accent': '#2F6BFF',
    'accent_hover': '#4A80FF',
    'accent_text': '#FFFFFF',
    'switch': '#E8EDF6',
    'switch_hover': '#DCE4F2',
    'entry': '#F7F9FC',
    'entry_border': '#DCE2EC',
    'disabled_text': '#8A93A3',
    'text': '#1B2230',
    'muted': '#6B7484',
    'divider': '#E4E8EF',
}

#: Window / executable icon. The game's favicon; SVG is not accepted by
#: ``iconbitmap``, so the .ico is used.
ICON_NAME = 'favicon.ico'

#: Where the bundled channel profiles came from. The profiles are
#: redistributed third-party data, and since users may only ever see the
#: packaged .exe, the credit has to be reachable from inside the app.
SOURCE_URL = 'https://www.bilibili.com/video/BV1NZ421m7Qy'
SOURCE_CREDIT = '考官家恒'

#: Preferred fonts, in order. A CJK-capable face must come first, since the
#: interface is Chinese.
_FONT_CANDIDATES = (
    'Microsoft YaHei UI',
    'Microsoft YaHei',
    '微软雅黑',
    'SimHei',
    'Segoe UI',
    'Arial',
)


def _pick_font(root) -> str:
    """Return the first available font from :data:`_FONT_CANDIDATES`."""
    try:
        from tkinter import font as tkfont
        available = {name.lower() for name in tkfont.families(root)}
    except Exception:
        return _FONT_CANDIDATES[-1]

    for name in _FONT_CANDIDATES:
        if name.lower() in available:
            return name
    return _FONT_CANDIDATES[-1]


def _asset(*parts) -> str:
    """Absolute path to a bundled asset, independent of the CWD."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


class App(ctk.CTk):
    """The main window."""

    def __init__(self, path: str | None = None):
        # Pin the light theme. CustomTkinter defaults to following the OS, and
        # this palette is a light design: in dark mode the card and every
        # unstyled control would come out dark.
        ctk.set_appearance_mode('light')

        super().__init__(fg_color=PALETTE['page'])
        self.title(f'生死狙击2 渠道切换  v{__version__}')
        self.geometry(f'{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}')
        self.resizable(False, False)
        self._set_icon()
        self._centre()

        self.font = _pick_font(self)
        self.path = path or locate()

        # Index into CHANNELS, not display order, so the two cannot drift.
        # ``None`` means "no config files found".
        self._current_index: int | None = None

        self._build()
        self._load_state()

    def _set_icon(self) -> None:
        """Use the game's favicon as the window icon.

        Deliberately uses ``iconbitmap`` only. The alternative, ``CTkImage``,
        would load Pillow -- a ~10 MB dependency -- to draw a 32px icon, and
        Pillow is otherwise unused by this program.

        Best-effort: a missing or unreadable icon must never stop the window
        from opening.
        """
        path = _asset('data', ICON_NAME)
        if not os.path.isfile(path):
            return
        with contextlib.suppress(Exception):
            self.iconbitmap(path)

    def _centre(self) -> None:
        """Place the window in the middle of the screen."""
        self.update_idletasks()
        width, height = WINDOW_SIZE
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 3
        self.geometry(f'{width}x{height}+{x}+{y}')

    # --- construction -------------------------------------------------------

    def _build(self) -> None:
        pad = {'padx': 22}

        card = ctk.CTkFrame(self, fg_color=PALETTE['card'], corner_radius=14)
        card.pack(fill='both', expand=True, padx=26, pady=18)

        # --- game directory --------------------------------------------------
        # No header block and no leading divider: with the logo gone there is
        # nothing above to separate from, so the card opens straight into the
        # first section. Branding lives in the window icon instead.
        #
        # The path sits above the channel controls because it is context
        # (where we are operating), not an action.
        ctk.CTkLabel(card, text='游戏目录', font=(self.font, 12),
                     text_color=PALETTE['muted']).pack(
            anchor='w', pady=(24, 0), **pad)

        path_row = ctk.CTkFrame(card, fg_color='transparent')
        path_row.pack(fill='x', pady=(6, 0), **pad)

        self.pathbox = ctk.CTkEntry(
            path_row, height=34, font=(self.font, 12),
            fg_color=PALETTE['entry'], border_color=PALETTE['entry_border'],
            text_color=PALETTE['text'], corner_radius=8)
        self.pathbox.pack(side='left', fill='x', expand=True)
        if self.path:
            self.pathbox.insert(0, self.path)

        ctk.CTkButton(
            path_row, width=94, height=34, text='选择目录',
            font=(self.font, 12), fg_color=PALETTE['switch'],
            hover_color=PALETTE['switch_hover'], text_color=PALETTE['text'],
            corner_radius=8, command=self.on_browse).pack(
            side='left', padx=(12, 0))

        self._divider(card)

        # --- channel switch --------------------------------------------------
        ctk.CTkLabel(card, text='渠道切换', font=(self.font, 12),
                     text_color=PALETTE['muted']).pack(anchor='w', **pad)

        row = ctk.CTkFrame(card, fg_color='transparent')
        row.pack(fill='x', pady=(6, 0), **pad)

        self.switcher = ctk.CTkButton(
            row, width=112, height=38, text='切换到', font=(self.font, 14),
            fg_color=PALETTE['switch'], hover_color=PALETTE['switch_hover'],
            text_color=PALETTE['text'],
            text_color_disabled=PALETTE['disabled_text'],
            corner_radius=8, command=self.on_switch)
        self.switcher.pack(side='left')

        # CTkOptionMenu opens a real popup, so it cannot be clipped by the
        # window the way a canvas-drawn dropdown can.
        self.selector = ctk.CTkOptionMenu(
            row, values=list(CHANNELS.labels), font=(self.font, 14),
            dropdown_font=(self.font, 14), width=240, height=38,
            fg_color=PALETTE['switch'], button_color=PALETTE['switch'],
            button_hover_color=PALETTE['switch_hover'],
            text_color=PALETTE['text'], dropdown_fg_color=PALETTE['card'],
            dropdown_hover_color=PALETTE['switch'],
            dropdown_text_color=PALETTE['text'],
            corner_radius=8, command=self.on_select)
        self.selector.pack(side='left', padx=(12, 0), fill='x', expand=True)

        # --- primary action, last --------------------------------------------
        # "热油" is the community's nickname for 生死狙击2; the phrasing is
        # deliberately colloquial to match how players talk about the game.
        self.launch_button = ctk.CTkButton(
            card, height=54, text='热油，启动！', font=(self.font, 19, 'bold'),
            fg_color=PALETTE['accent'], hover_color=PALETTE['accent_hover'],
            text_color=PALETTE['accent_text'], corner_radius=10,
            command=self.on_launch)
        self.launch_button.pack(fill='x', pady=(18, 0), **pad)

        # Status line, normally empty. Pinned to a small height so the space
        # it reserves stays modest while still absorbing a message without
        # shifting the layout below it.
        self.status = ctk.CTkLabel(
            card, text='', font=(self.font, 11), height=16,
            text_color=PALETTE['muted'])
        self.status.pack(pady=(8, 0))

        # --- footer: credit for the redistributed profile data --------------
        # Kept understated (small, muted) but present: users may only ever
        # receive the packaged .exe, so the attribution must live in the app.
        self.credit = ctk.CTkLabel(
            card, text=f'配置文件来源：B站 @{SOURCE_CREDIT}',
            font=(self.font, 10), text_color=PALETTE['muted'],
            cursor='hand2')
        self.credit.pack(pady=(12, 16))
        self.credit.bind('<Button-1>', lambda _event: self.on_about())

    def _divider(self, parent, pady=(6, 14)) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=PALETTE['divider']).pack(
            fill='x', pady=pady, padx=22)

    # --- state --------------------------------------------------------------

    def _load_state(self) -> None:
        """Reflect what is on disk.

        The current channel is conveyed through the selector rather than a
        separate heading, so there is only one place to look.
        """
        if not self.path:
            self._current_index = None
            self.status.configure(text='未找到游戏，请点「选择目录」')
            self._set_switcher_enabled(False)
            return

        result = detect(self.path)
        if result.config_channel is not None:
            self._current_index = CHANNELS.index(result.config_channel)
            self.selector.set(result.config_channel.label)
            self.status.configure(text='')
        else:
            self._current_index = None
            self.status.configure(text='配置文件缺失，点「切换到」可重新生成')

        self._refresh_switcher()

    def _selected_channel(self):
        """The Channel currently chosen in the dropdown, or ``None``."""
        label = self.selector.get()
        return CHANNELS.get(next(
            (c.key for c in CHANNELS if c.label == label), ''))

    def _set_switcher_enabled(self, enabled: bool) -> None:
        self.switcher.configure(state='normal' if enabled else 'disabled')

    def _refresh_switcher(self) -> None:
        """Match the button to whether a switch is actually needed."""
        target = self._selected_channel()
        pending = (self._current_index is None or target is None
                   or CHANNELS.index(target) != self._current_index)

        if pending:
            self.switcher.configure(text='切换到', state='normal',
                                    text_color=PALETTE['text'])
        else:
            self.switcher.configure(text='已是此渠道', state='disabled')

    # --- events -------------------------------------------------------------

    def on_select(self, _label: str) -> None:
        self._refresh_switcher()

    def on_switch(self) -> None:
        target = self._selected_channel()
        if target is None or not self.path:
            self.status.configure(text='请先选择游戏目录')
            return

        try:
            if self._current_index is None:
                # Config files are missing: recreate them for this channel.
                ensure_configs(self.path, channel=target)
            else:
                rewrite(target, path=self.path)
        except (BT2FusionError, OSError) as exc:
            self.status.configure(text=f'切换失败：{exc}')
            return

        # Re-detect rather than assume, so the display reflects the disk.
        result = detect(self.path)
        if result.config_channel is not None:
            self._current_index = CHANNELS.index(result.config_channel)
        self._refresh_switcher()
        self.status.configure(text=f'已切换到 {target.label}')

    def on_browse(self) -> None:
        from tkinter import messagebox
        from tkinter.filedialog import askdirectory

        chosen = askdirectory(initialdir=self.path or os.path.expanduser('~'),
                              title='请选择生死狙击2的安装目录')
        if not chosen:
            return  # Cancelled: keep everything as it was.

        chosen = os.path.normpath(chosen)
        if not is_install_dir(chosen):
            messagebox.showwarning(
                '目录不正确',
                '这个目录里没有找到 WDlauncher.exe。\n\n'
                '请选择包含 WDlauncher.exe 的目录，通常是游戏根目录。')
            return

        self.path = chosen
        with contextlib.suppress(OSError):
            # Failing to remember the choice is not fatal.
            config.set_install_dir(chosen)
            reset_location_cache()

        self.pathbox.delete(0, 'end')
        self.pathbox.insert(0, chosen)
        self._load_state()

    def on_launch(self) -> None:
        if not self.path:
            self.status.configure(text='请先选择游戏目录')
            return
        try:
            launch(self.path)
        except (BT2FusionError, OSError) as exc:
            self.status.configure(text=f'启动失败：{exc}')
            return
        self.status.configure(text='正在启动游戏…')

    def on_about(self) -> None:
        """Show the data provenance, with a link to the original source.

        The channel profiles are redistributed from a third party, so the
        credit is shown in-app rather than only in the repository.
        """
        import webbrowser
        from tkinter import messagebox

        proceed = messagebox.askokcancel(
            '数据来源',
            f'本程序内置的各渠道配置文件，由 B站 UP 主「{SOURCE_CREDIT}」'
            f'提供。\n\n'
            f'{SOURCE_URL}\n\n'
            f'没有这份分享就没有本程序 —— 这里做的是把“手动找文件、手动替换”'
            f'自动化。\n\n'
            f'配置文件的权利属于游戏官方及各渠道方，本程序仅作转载与自动化。\n\n'
            f'点击「确定」将打开原视频。')
        if proceed:
            with contextlib.suppress(Exception):
                webbrowser.open(SOURCE_URL)


def main(argv=None) -> int:
    """Entry point for the ``bt2fusion-gui`` script."""
    import argparse

    parser = argparse.ArgumentParser(
        prog='bt2fusion-gui', description='生死狙击2 渠道切换')
    parser.add_argument('-C', '--path', metavar='DIR', help='游戏安装目录')
    args = parser.parse_args(argv)

    if args.path and not is_install_dir(args.path):
        print(f'错误：{args.path} 不是有效的游戏目录', file=sys.stderr)
        return 2

    App(path=args.path).mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
