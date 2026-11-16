"""Global hotkey as a backup way to summon Bonnington."""

from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard


class HotkeyListener:
    def __init__(self, combo: str, on_press: Callable[[], None]) -> None:
        keyboard.HotKey.parse(combo)  # raises ValueError for an invalid combo
        self.combo = combo
        self.on_press = on_press
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        if self._listener is None:
            self._listener = keyboard.GlobalHotKeys({self.combo: self.on_press})
            self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
