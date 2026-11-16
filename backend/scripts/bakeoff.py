"""Persona bake-off: same Bonnington prompts against each candidate brain; prints replies + time to first token."""
import asyncio
import sys
import time
from datetime import datetime

from bonnington.brain.llm import Brain
from bonnington.brain.persona import build_summons_note
from bonnington.store import SummonsContext

PROMPTS = [
    build_summons_note(SummonsContext("britney", 214, 240.0, 3, datetime(2026, 11, 15, 23, 40)))
    + " How are you doing?",
    "What exams do I have this week?",
    "I'm going to skip studying tonight and play games instead.",
    build_summons_note(SummonsContext("bonnington", 214, 3600.0, 1, datetime(2026, 11, 16, 9, 5)))
    + " Morning.",
]


async def run(model: str) -> None:
    b = Brain(model)
    await b.warm()
    print(f"\n===== {model}")
    for p in PROMPTS:
        b.reset_session()
        t0 = time.perf_counter()
        first = None
        out = []
        async for c in b.stream_reply(p):
            if first is None:
                first = time.perf_counter() - t0
            out.append(c)
        print(f"[{first*1000:.0f} ms first token, {time.perf_counter()-t0:.1f}s total] {''.join(out).strip()}")
    await b.unload()


async def main() -> None:
    for m in sys.argv[1:]:
        await run(m)

asyncio.run(main())
