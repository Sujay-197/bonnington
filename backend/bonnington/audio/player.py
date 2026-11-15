"""Plays utterances on the default output device and reports loudness for the globe."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable

import numpy as np

AMPLITUDE_HZ = 30
_FULL_SCALE_RMS = 0.25


def _default_stream_factory(**kw):
    import sounddevice as sd
    return sd.OutputStream(**kw)


class AudioPlayer:
    def __init__(self, on_amplitude: Callable[[float], None], stream_factory=None) -> None:
        self.on_amplitude = on_amplitude
        self.stream_factory = stream_factory or _default_stream_factory
        self._stop = threading.Event()
        self.is_playing = False

    def stop(self) -> None:
        self._stop.set()

    async def play(self, u) -> bool:
        self._stop.clear()
        self.is_playing = True
        try:
            return await asyncio.to_thread(self._play_blocking, u)
        finally:
            self.is_playing = False
            self.on_amplitude(0.0)

    def _play_blocking(self, u) -> bool:
        block = max(1, u.sample_rate // AMPLITUDE_HZ)
        stream = self.stream_factory(samplerate=u.sample_rate, channels=1, dtype="float32")
        stream.start()
        try:
            for pcm in self._chunks(u):
                for i in range(0, len(pcm), block):
                    if self._stop.is_set():
                        return False
                    chunk = pcm[i:i + block]
                    rms = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0
                    self.on_amplitude(min(1.0, rms / _FULL_SCALE_RMS))
                    stream.write(chunk.reshape(-1, 1))
            return not self._stop.is_set()
        finally:
            stream.stop()
            stream.close()

    def _chunks(self, u):
        """The utterance's audio: all at once, or chunk by chunk as it is generated."""
        if getattr(u, "stream", None) is None:
            yield np.asarray(u.pcm, dtype=np.float32).reshape(-1)
            return
        while not self._stop.is_set():
            try:
                pcm = u.stream.get(timeout=0.1)
            except queue.Empty:
                continue
            if pcm is None:
                return
            yield np.asarray(pcm, dtype=np.float32).reshape(-1)
