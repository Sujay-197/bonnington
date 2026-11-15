"""How awake Bonnington is: OFF, ASLEEP (mic closed), DORMANT (wake word only), AWAKE (models + window)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from enum import Enum

log = logging.getLogger(__name__)


SLEEP_AFTER_PROBES = 2


class Level(Enum):
    OFF = "off"
    ASLEEP = "asleep"
    DORMANT = "dormant"
    AWAKE = "awake"


def next_level(current: Level, *, fullscreen: bool, mic_busy: bool, manual_dnd: bool,
               wake_requested: bool, idle_s: float, idle_unload_s: float) -> Level:
    if manual_dnd or fullscreen or mic_busy:
        return Level.ASLEEP
    if wake_requested:
        return Level.AWAKE
    if current == Level.AWAKE:
        return Level.DORMANT if idle_s >= idle_unload_s else Level.AWAKE
    if current in (Level.ASLEEP, Level.OFF):
        return Level.DORMANT
    return current


class LifecycleController:
    def __init__(self, orch, mic, ui, *, idle_unload_s: float = 600.0,
                 probe: Callable[[], tuple[bool, bool]] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 probe_interval_s: float = 3.0) -> None:
        self.orch, self.mic, self.ui = orch, mic, ui
        self.idle_unload_s = idle_unload_s
        self.probe = probe or _default_probe
        self.clock = clock
        self.probe_interval_s = probe_interval_s
        self.level = Level.DORMANT
        self._dnd = False
        self._wake_requested = False
        self._override_probes = False
        self._busy_streak = 0  # consecutive probes that saw a game/call
        self._awake_since = 0.0
        self._kick: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.on_level_change: Callable[[Level], None] | None = None
        # Hotkey-first (False): mic closed while dormant so Bluetooth buds keep full audio quality.
        self.always_listening: Callable[[], bool] = lambda: True
        self.keep_window = False   # True: the dashboard window stays open while he is dormant
        orch.on_wake_requested = self.request_wake
        orch.on_session_end = self._kick_now

    def request_wake(self) -> None:
        """Called by the orchestrator (wake word) or the hotkey thread."""
        self._wake_requested = True
        if self._loop is not None and self._kick is not None:
            self._loop.call_soon_threadsafe(self._kick.set)

    def set_dnd(self, on: bool) -> None:
        self._dnd = on
        self._kick_now()

    def _kick_now(self) -> None:
        if self._loop is not None and self._kick is not None:
            self._loop.call_soon_threadsafe(self._kick.set)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._kick = asyncio.Event()
        while True:
            await self.step()
            self._kick.clear()
            try:
                await asyncio.wait_for(self._kick.wait(), self.probe_interval_s)
            except asyncio.TimeoutError:
                pass

    async def step(self) -> None:
        woke = self._wake_requested
        self._wake_requested = False
        if woke and self.level == Level.ASLEEP and not self._dnd:
            self._override_probes = True
        if self._override_probes:
            fullscreen = busy = False
        else:
            try:
                fullscreen, busy = await asyncio.to_thread(self.probe)
            except Exception as e:  # a probe failure must never kill the assistant
                log.warning("system probe failed: %s", e)
                fullscreen = busy = False
        # Debounce: a screenshot overlay or a notification must not put him to sleep, and nothing
        # puts him to sleep while you're mid-conversation.
        self._busy_streak = self._busy_streak + 1 if (fullscreen or busy) else 0
        if self._busy_streak < SLEEP_AFTER_PROBES or getattr(self.orch, "active", False):
            fullscreen = busy = False
        elif fullscreen or busy:
            log.info("sleeping: fullscreen=%s mic_busy=%s", fullscreen, busy)
        idle_s = self.clock() - max(self.orch.last_interaction, self._awake_since)
        new = next_level(self.level, fullscreen=fullscreen, mic_busy=busy, manual_dnd=self._dnd,
                         wake_requested=woke, idle_s=idle_s, idle_unload_s=self.idle_unload_s)
        await self._transition(new)
        if self.keep_window and self.level != Level.ASLEEP:
            self.ui.show()                 # the dashboard stays up (and comes back if it was closed)
        await self._sync_mic()

    async def _sync_mic(self) -> None:
        if self.level == Level.ASLEEP:
            want = False
        elif self.always_listening():
            want = True
        else:
            want = self.level == Level.AWAKE and bool(getattr(self.orch, "active", False))
        if want and not self.mic.is_open:
            await self.mic.open()
        elif not want and self.mic.is_open:
            await self.mic.close()

    async def _transition(self, new: Level) -> None:
        old = self.level
        if new == old:
            return
        log.info("level %s -> %s", old.value, new.value)
        if old == Level.AWAKE:
            await self.orch.go_dormant()
            if not self.keep_window:
                self.ui.hide()
        if new == Level.ASLEEP:
            self.ui.hide()                 # a game or a call: get out of the way entirely
        elif new == Level.DORMANT:
            self._override_probes = False
            if self.keep_window:
                self.ui.show()
        elif new == Level.AWAKE:
            self._awake_since = self.clock()
            self.ui.show()
        self.level = new
        if self.on_level_change:
            self.on_level_change(new)


def _default_probe() -> tuple[bool, bool]:
    import sys

    from .sysprobe import is_fullscreen_app, mic_in_use_by_other
    own = {sys.executable, getattr(sys, "_base_executable", sys.executable)}
    return is_fullscreen_app(), mic_in_use_by_other([p.replace("\\", "#") for p in own])
