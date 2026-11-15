"""Open the configured mic through MicSource for a few seconds, twice (open/close/open), and report frames."""
import asyncio
import sys
import time

import numpy as np

from bonnington.audio.source import MicSource
from bonnington.config import load_settings


async def grab(mic, seconds):
    t0 = time.monotonic(); n = pk = 0
    async for f in mic.frames():
        n += 1; pk = max(pk, int(np.abs(f.astype(np.int32)).max()))
        if time.monotonic() - t0 > seconds:
            return n, pk


async def main():
    device = sys.argv[1] if len(sys.argv) > 1 else load_settings("data/settings.json").mic_device
    mic = MicSource(device=device)
    for i in (1, 2):
        await mic.open()
        n, pk = await asyncio.wait_for(grab(mic, 4), 20)
        await mic.close()
        print(f"{device} round {i}: {n} frames ({n * 0.08:.1f}s of audio) in 4s, peak {pk}", flush=True)
        await asyncio.sleep(1)

asyncio.run(main())
