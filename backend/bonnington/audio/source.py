"""Where audio comes from. Phase 1: the PC's default mic. An ESP32 source can implement the same protocol."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms


class AudioSource(Protocol):
    is_open: bool

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    def frames(self) -> AsyncIterator[np.ndarray]: ...


def _default_stream_factory(**kw):
    import sounddevice as sd
    return sd.InputStream(**kw)


class MicSource:
    """Blocking reads in a worker thread. Survives device loss by reopening the current default device."""

    def __init__(self, device: int | None = None, retry_seconds: float = 5.0, stream_factory=None) -> None:
        self.device = device
        self.retry_seconds = retry_seconds
        self.stream_factory = stream_factory or _default_stream_factory
        self._stream = None
        self._want_open = asyncio.Event()
        self.is_open = False

    async def open(self) -> None:
        self._want_open.set()
        self.is_open = True

    async def close(self) -> None:
        self._want_open.clear()
        self.is_open = False
        self._drop_stream()

    def _drop_stream(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass

    def _make_stream(self):
        s = self.stream_factory(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME, device=self.device)
        s.start()
        return s

    async def frames(self) -> AsyncIterator[np.ndarray]:
        while True:
            await self._want_open.wait()  # paused while closed (e.g. Bonnington is asleep)
            try:
                if self._stream is None:
                    self._stream = await asyncio.to_thread(self._make_stream)
                data, _overflow = await asyncio.to_thread(self._stream.read, FRAME)
            except Exception as e:
                if not self._want_open.is_set():
                    continue
                log.warning("microphone failed (%s); retrying in %.1fs", e, self.retry_seconds)
                self._drop_stream()
                await asyncio.sleep(self.retry_seconds)
                continue
            if not self._want_open.is_set():
                continue
            yield np.asarray(data, dtype=np.int16).reshape(-1)
