"""Where audio comes from. Phase 1: a PC input device. An ESP32 source can implement the same protocol."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms
STALL_REOPEN_S = 0.3


class AudioSource(Protocol):
    is_open: bool

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    def frames(self) -> AsyncIterator[np.ndarray]: ...


def _default_stream_factory(**kw):
    import sounddevice as sd
    return sd.InputStream(**kw)


class MicSource:
    """Callback-driven capture. Never blocks on the driver: if no audio arrives for `stall_seconds`
    (unplugged device, a Bluetooth headset stuck switching profiles) the stream is dropped and reopened."""

    def __init__(self, device: int | str | None = None, retry_seconds: float = 5.0,
                 stall_seconds: float = 2.0, open_grace_seconds: float = 6.0, stream_factory=None) -> None:
        self.device = device
        self.retry_seconds = retry_seconds
        self.stall_seconds = stall_seconds
        self.open_grace_seconds = open_grace_seconds  # Bluetooth needs a few seconds to switch profile
        self.stream_factory = stream_factory or _default_stream_factory
        self._stream = None
        self._want_open = asyncio.Event()
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_audio = 0.0  # monotonic time the driver last delivered audio
        self.is_open = False

    async def open(self) -> None:
        self._want_open.set()
        self.is_open = True

    async def close(self) -> None:
        self._want_open.clear()
        self.is_open = False
        await self._drop_stream()

    async def _drop_stream(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            def kill() -> None:
                try:
                    s.abort()
                    s.close()
                except Exception:
                    pass
            await asyncio.to_thread(kill)
        while not self._queue.empty():
            self._queue.get_nowait()

    async def _wait_for_audio(self) -> None:
        while self._queue.empty():
            await asyncio.sleep(0.01)

    def _on_audio(self, indata, frames, time_info, status) -> None:  # PortAudio thread
        block = np.array(indata, dtype=np.int16).reshape(-1)
        self._last_audio = time.monotonic()
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, block)
            except RuntimeError:
                pass  # event loop already closed (shutting down)

    def _make_stream(self):
        s = self.stream_factory(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME, device=self.device, callback=self._on_audio)
        s.start()
        return s

    async def frames(self) -> AsyncIterator[np.ndarray]:
        self._loop = asyncio.get_running_loop()
        pending = np.zeros(0, np.int16)
        while True:
            await self._want_open.wait()  # paused while closed (e.g. Bonnington is dormant)
            try:
                if self._stream is None:
                    pending = np.zeros(0, np.int16)
                    self._stream = await asyncio.to_thread(self._make_stream)
                    # count the first audio as due within the open grace period, not the stall window
                    self._last_audio = time.monotonic() + max(0.0, self.open_grace_seconds - self.stall_seconds)
                if self._queue.empty():
                    try:
                        await asyncio.wait_for(self._wait_for_audio(), self.stall_seconds)
                    except asyncio.TimeoutError:
                        # Judge a stall by when the driver last delivered audio, not by how busy
                        # this program was: a blocked event loop must not look like a dead mic.
                        if time.monotonic() - self._last_audio < self.stall_seconds:
                            continue
                        if self._want_open.is_set():
                            log.warning("microphone stalled (no audio for %.1fs); reopening", self.stall_seconds)
                            await self._drop_stream()
                            await asyncio.sleep(STALL_REOPEN_S)
                        continue
                    if self._queue.empty():
                        continue
                block = self._queue.get_nowait()
            except Exception as e:
                if not self._want_open.is_set():
                    continue
                log.warning("microphone failed (%r); retrying in %.1fs", e, self.retry_seconds)
                await self._drop_stream()
                await asyncio.sleep(self.retry_seconds)
                continue
            if not self._want_open.is_set():
                continue
            pending = np.concatenate([pending, block]) if len(pending) else block
            while len(pending) >= FRAME:
                yield pending[:FRAME]
                pending = pending[FRAME:]
