"""Live wake-word check: listens for 60 s, prints every hit and logs it to data/wake_test.log."""
import asyncio
import time

from bonnington.audio.source import MicSource
from bonnington.config import load_settings
from bonnington.wake import KeywordWake

LOG = "data/wake_test.log"


def log(line: str) -> None:
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main() -> None:
    s = load_settings("data/settings.json")
    wake = KeywordWake(s.wake_phrases, s.kws_model_dir, boost=s.wake_boost, threshold=s.wake_threshold)
    mic = MicSource(device=s.mic_device)
    await mic.open()
    print('Listening 60 s. Say "Hey Britney" 5 times, "Hey Bonnington" 5 times, then just talk normally.\n')
    log(f"start threshold={s.wake_threshold} boost={s.wake_boost}")
    t0 = time.monotonic()
    async for frame in mic.frames():
        hit = wake.feed(frame)
        if hit:
            log(f"  {time.monotonic() - t0:5.1f}s  HIT: {hit}")
        if time.monotonic() - t0 > 60:
            break
    await mic.close()
    log("done")


asyncio.run(main())
