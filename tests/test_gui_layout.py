"""Tests for GUI layout and behaviour.

Kept deliberately toolkit-agnostic where possible: the assertions read widget
state and window geometry rather than poking at toolkit internals, so the GUI
toolkit can change without rewriting the suite.

Tk requires a display; the whole module is skipped where one is unavailable.
"""

import pytest

from bt2fusion.channels import CHANNELS

ctk = pytest.importorskip('customtkinter')
tkinter = pytest.importorskip('tkinter')


@pytest.fixture
def app():
    from bt2fusion.gui import App

    # Bring up the window, skipping rather than erroring if this interpreter's
    # Tk cannot start. A uv-managed CPython 3.12 here fails intermittently
    # with "This probably means that tk wasn't installed properly", which is
    # an environment fault, not a regression -- the shipped exe bundles its
    # own Tcl/Tk and is unaffected. Deliberately no module-level probe root:
    # an extra create/destroy cycle made the race more likely.
    try:
        instance = App()
        instance.update()
    except tkinter.TclError as exc:  # pragma: no cover - environment fault
        pytest.skip(f'Tk unavailable in this interpreter: {exc}')

    yield instance

    # Cancel pending callbacks before destroying: CustomTkinter schedules a
    # recurring DPI-scaling check, and one firing after the root is gone
    # raises "invalid command name ...check_dpi_scaling".
    try:
        for job in instance.tk.call('after', 'info'):
            instance.after_cancel(job)
    except Exception:  # pragma: no cover - already torn down
        pass
    instance.destroy()


def _text(widget) -> str:
    return widget.cget('text')


def test_window_matches_declared_size(app):
    """The window is the size we asked for, in logical units.

    ``winfo_width`` reports *physical* pixels, which on a HiDPI display differ
    from the requested size by the scaling factor (1.25 here), so the geometry
    string -- which is in logical units -- is compared instead.
    """
    from bt2fusion.gui import WINDOW_SIZE

    app.update_idletasks()
    size = app.geometry().split('+')[0]
    width, height = (int(part) for part in size.split('x'))
    assert (width, height) == WINDOW_SIZE


def test_all_channels_are_offered(app):
    """Every registered channel must be selectable."""
    labels = app.selector.cget('values')
    assert list(labels) == list(CHANNELS.labels)


def test_dropdown_is_not_drawn_inside_the_window(app):
    """The channel list must not be clipped by the window.

    An earlier toolkit drew the dropdown on the same canvas, so a 7-item list
    extended past the window edge and the last entries were unreachable.
    CustomTkinter opens a real popup instead, which this asserts by checking
    the control reports no in-window popup geometry.
    """
    app.selector.set(CHANNELS.labels[0])
    app.update()

    # The popup, if any, is a separate toplevel rather than part of the canvas.
    in_window = [w for w in app.winfo_children()
                 if 'dropdown' in w.__class__.__name__.lower()]
    assert not in_window, 'dropdown appears to be drawn inside the window'


def test_current_channel_is_not_duplicated(app):
    """The channel must appear in exactly one place.

    It used to be shown both as a large heading and in the selector, which
    was redundant and pushed the window taller than necessary.
    """
    if app._current_index is None:
        pytest.skip('no channel detected on this machine')

    channel = CHANNELS[app._current_index]
    assert app.selector.get() == channel.label
    # No separate big label remains.
    assert not hasattr(app, 'current_label')
    assert not hasattr(app, 'current_hint')


def test_selector_shows_the_detected_channel(app):
    """The dropdown is where the current channel is communicated."""
    if app._current_index is None:
        pytest.skip('no channel detected on this machine')

    assert app.selector.get() == CHANNELS[app._current_index].label


def test_switch_button_wording(app):
    """「切换到」 when actionable, 「已是此渠道」 when not."""
    if app._current_index is None:
        pytest.skip('no channel detected on this machine')

    app.selector.set(CHANNELS[app._current_index].label)
    app.on_select(CHANNELS[app._current_index].label)
    app.update()
    assert _text(app.switcher) == '已是此渠道'
    assert app.switcher.cget('state') == 'disabled'

    other = (app._current_index + 1) % len(CHANNELS)
    app.selector.set(CHANNELS[other].label)
    app.on_select(CHANNELS[other].label)
    app.update()
    assert _text(app.switcher) == '切换到'
    assert app.switcher.cget('state') == 'normal'


def test_window_is_sized_to_its_content(app):
    """No large empty area below the last element."""
    app.update_idletasks()
    app.update()

    card = app.winfo_children()[0]
    last = card.winfo_children()[-1]
    slack = (card.winfo_y() + card.winfo_height()) - \
            (last.winfo_y() + last.winfo_height())
    assert 0 <= slack < 80, f'window carries {slack}px of empty space'


def test_layout_order(app):
    """Game directory above; channel switch, then launch, then credit."""
    card = app.winfo_children()[0]
    texts = [w.cget('text') for w in card.winfo_children()
             if w.__class__.__name__ == 'CTkLabel' and w.cget('text')]

    assert texts[0] == '游戏目录', texts
    assert texts[1] == '渠道切换', texts
    assert texts[2].startswith('配置文件来源'), texts


def test_no_redundant_subtitle(app):
    """The logo named the game; a subtitle underneath repeated it."""
    from bt2fusion.gui import WINDOW_SIZE

    card = app.winfo_children()[0]
    texts = [w.cget('text') for w in card.winfo_children()
             if w.__class__.__name__ == 'CTkLabel' and w.cget('text')]

    assert '生死狙击2 渠道切换' not in texts, texts
    # Only three captions remain: the two sections and the credit.
    assert len(texts) == 3, texts
    assert WINDOW_SIZE[1] <= 440


def test_window_uses_the_game_favicon(app):
    """The window icon comes from the bundled favicon."""
    from bt2fusion.gui import ICON_NAME

    assert ICON_NAME == 'favicon.ico'
    # Reaching this far means _set_icon() did not raise; a missing or
    # unreadable icon must never prevent the window from opening.
    assert app.winfo_exists()


def test_no_logo_is_rendered(app):
    """The grey-on-transparent wordmark read poorly on the white card."""
    from importlib import resources

    from bt2fusion.gui import App as GuiApp

    data = resources.files('bt2fusion').joinpath('data')
    assert not data.joinpath('bt2_logo.png').is_file()
    # The logo label is gone; only three captions remain.
    assert not hasattr(app, '_logo')
    del GuiApp  # imported only to assert the module is reachable


def test_selected_channel_maps_to_a_real_channel(app):
    """The dropdown label must resolve back to a registry entry."""
    for channel in CHANNELS:
        app.selector.set(channel.label)
        assert app._selected_channel() is channel


def test_credit_for_profile_data_is_visible_in_app(app):
    """Users may only ever receive the packaged .exe.

    The bundled channel profiles are redistributed third-party data, so the
    credit has to be reachable from the interface itself, not just from the
    repository.
    """
    from bt2fusion.gui import SOURCE_CREDIT

    assert SOURCE_CREDIT in _text(app.credit)
    assert callable(getattr(app, 'on_about', None))


def test_source_url_points_at_the_original_video():
    from bt2fusion.gui import SOURCE_URL

    assert SOURCE_URL == 'https://www.bilibili.com/video/BV1NZ421m7Qy'


def test_app_pins_the_light_theme(app):
    """The palette is a light design, so the mode must not follow the OS.

    CustomTkinter defaults to the system setting; on a machine running dark
    mode the card and every unstyled control would come out dark.
    """
    import customtkinter as ctk

    assert ctk.get_appearance_mode() == 'Light'


def test_launch_button_uses_the_community_nickname(app):
    """「热油」 is what players actually call the game."""
    assert _text(app.launch_button) == '热油，启动！'
