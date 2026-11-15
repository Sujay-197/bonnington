"""Live wake-word check: listens for 60 s and prints every hit."""
import asyncio
import time

from bonnington.audio.source import MicSource
from bonnington.config import load_settings
from bonnington.wake import KeywordWake


async def main() -> None:
    s = load_settings("data/settings.json")
    wake = KeywordWake(s.wake_phrases, s.kws_model_dir, boost=s.wake_boost, threshold=s.wake_threshold)
    mic = MicSource(device=s.mic_device)
    await mic.open()
    print('Listening 60 s. Say "Hey Britney" 5 times, "Hey Bonnington" 5 times, then just talk normally.\n')
    t0 = time.monotonic()
    async for frame in mic.frames():
        hit = wake.feed(frame)
        if hit:
            print(f"  {time.monotonic() - t0:5.1f}s  HIT: {hit}", flush=True)
        if time.monotonic() - t0 > 60:
            break
    await mic.close()
    print("done")

asyncio.run(main())
