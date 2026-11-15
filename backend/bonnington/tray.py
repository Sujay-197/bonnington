"""System tray icon: shows the level, toggles do-not-disturb and headphones mode, quits."""

from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

_COLOURS = {"asleep": (95, 94, 90), "dormant": (180, 178, 169), "awake": (255, 255, 255), "off": (60, 60, 60)}


def _icon_image(level: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), outline=_COLOURS.get(level, (255, 255, 255)), width=6)
    return img


class Tray:
    def __init__(self, *, get_dnd: Callable[[], bool], set_dnd: Callable[[bool], None],
                 get_headphones: Callable[[], bool], set_headphones: Callable[[bool], None],
                 get_always_listening: Callable[[], bool], set_always_listening: Callable[[bool], None],
                 on_quit: Callable[[], None], phone_url: str | None = None) -> None:
        self._level = "dormant"
        menu = pystray.Menu(
            pystray.MenuItem(lambda _: f"Bonnington: {self._level}", None, enabled=False),
            pystray.MenuItem("Do not disturb", lambda: set_dnd(not get_dnd()),
                             checked=lambda _: get_dnd()),
            pystray.MenuItem('Always listening ("Hey Britney")',
                             lambda: set_always_listening(not get_always_listening()),
                             checked=lambda _: get_always_listening()),
            pystray.MenuItem("Headphones mode", lambda: set_headphones(not get_headphones()),
                             checked=lambda _: get_headphones()),
            pystray.MenuItem("Show phone mic link", lambda: self.icon.notify(phone_url, "Open on your phone"),
                             visible=phone_url is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: (on_quit(), self.icon.stop())),
        )
        self.icon = pystray.Icon("bonnington", _icon_image("dormant"), "Bonnington: dormant", menu)

    def set_level(self, level: str) -> None:
        self._level = level
        self.icon.icon = _icon_image(level)
        self.icon.title = f"Bonnington: {level}"
        self.icon.update_menu()

    def run(self) -> None:
        self.icon.run()  # blocks; must be on the main thread
