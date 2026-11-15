"""How awake Bonnington is: OFF, ASLEEP (mic closed), DORMANT (wake word only), AWAKE (models + window)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from enum import Enum

log = logging.getLogger(__name__)


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
        self._awake_since = 0.0
        self._kick: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.on_level_change: Callable[[Level], None] | None = None
        orch.on_wake_requested = self.request_wake

    def request_wake(self) -> None:
        """Called by the orchestrator (wake word) or the hotkey thread."""
        self._wake_requested = True
        if self._loop is not None and self._kick is not None:
            self._loop.call_soon_threadsafe(self._kick.set)

    def set_dnd(self, on: bool) -> None:
        self._dnd = on
        if self._loop is not None and self._kick is not None:
            self._loop.call_soon_threadsafe(self._kick.set)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._kick = asyncio.Event()
        await self.mic.open()
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
        idle_s = self.clock() - max(self.orch.last_interaction, self._awake_since)
        new = next_level(self.level, fullscreen=fullscreen, mic_busy=busy, manual_dnd=self._dnd,
                         wake_requested=woke, idle_s=idle_s, idle_unload_s=self.idle_unload_s)
        await self._transition(new)

    async def _transition(self, new: Level) -> None:
        old = self.level
        if new == old:
            return
        log.info("level %s -> %s", old.value, new.value)
        if old == Level.AWAKE:
            await self.orch.go_dormant()
            self.ui.hide()
        if new == Level.ASLEEP:
            await self.mic.close()
        elif new == Level.DORMANT:
            self._override_probes = False
            await self.mic.open()
        elif new == Level.AWAKE:
            self._awake_since = self.clock()
            await self.mic.open()
            self.ui.show()
        self.level = new
        if self.on_level_change:
            self.on_level_change(new)


def _default_probe() -> tuple[bool, bool]:
    import sys

    from .sysprobe import is_fullscreen_app, mic_in_use_by_other
    own = {sys.executable, getattr(sys, "_base_executable", sys.executable)}
    return is_fullscreen_app(), mic_in_use_by_other([p.replace("\\", "#") for p in own])
