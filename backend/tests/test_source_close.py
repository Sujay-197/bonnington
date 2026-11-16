"""Closing the mic must close it, even while a stream is still being opened."""

import asyncio
import time

import numpy as np

from bonnington.audio.source import MAX_QUEUED_BLOCKS, MicSource
from conftest import CallbackStream


class SlowFactory:
    """Opening the device takes a while (a Bluetooth headset switching profile)."""

    def __init__(self, delay=0.3):
        self.delay, self.made = delay, []

    def __call__(self, **kw):
        time.sleep(self.delay)
        s = CallbackStream(kw["callback"], kw["blocksize"])
        self.made.append(s)
        return s


async def _take(src, n):
    out = []
    async for f in src.frames():
        out.append(f)
        if len(out) == n:
            return out


async def test_close_while_the_stream_is_opening_leaves_no_stream_running():
    fac = SlowFactory()
    src = MicSource(stream_factory=fac)
    await src.open()
    reader = asyncio.create_task(_take(src, 1))
    await asyncio.sleep(0.1)                 # the stream is being opened
    await src.close()
    await asyncio.sleep(0.5)
    assert fac.made and fac.made[0]._stop.is_set()      # the late stream was shut straight away
    assert src._stream is None and src._queue.qsize() == 0
    reader.cancel()


async def test_audio_is_not_queued_while_closed_and_the_queue_is_bounded():
    src = MicSource(stream_factory=SlowFactory(0))
    src._loop = asyncio.get_running_loop()
    block = np.zeros((1280, 1), np.int16)
    for _ in range(10):
        src._on_audio(block, 1280, None, None)
    await asyncio.sleep(0.01)
    assert src._queue.qsize() == 0           # closed: dropped
    await src.open()
    for _ in range(MAX_QUEUED_BLOCKS * 3):
        src._on_audio(block, 1280, None, None)
    await asyncio.sleep(0.01)
    assert src._queue.qsize() <= MAX_QUEUED_BLOCKS
