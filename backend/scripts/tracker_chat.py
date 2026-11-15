"""Try the tracker against the real brain, in text (no mic, no voice).

Usage (from das_v0):  python backend/scripts/tracker_chat.py            -> scripted test in a scratch vault
                      python backend/scripts/tracker_chat.py --live     -> type to him, using your real vault
"""
import asyncio
import shutil
import sys
import time
from pathlib import Path

from bonnington.brain.llm import Brain
from bonnington.config import load_settings
from bonnington.vault.tools import build_tracker

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = [
    "I have a DBMS exam on the 24th at nine in the morning.",
    "Also add a task, renew my passport, by first of December.",
    "I scored 38 out of 50 in the DBMS midterm one.",
    "CN lab report three is due this Friday.",
    "Actually that last one is wrong, undo it.",
    "What's left for this week?",
    "Which of my projects are dying?",
    "Put campusai on hold until my exams are over.",
    "I renewed the passport.",
    "Explain what a B plus tree is.",
    "How am I doing in DBMS?",
]


async def main() -> None:
    live = "--live" in sys.argv
    s = load_settings(ROOT / "data" / "settings.json")
    if not live:
        s.vault_dir = str(ROOT / "data" / "vault_scratch")
        shutil.rmtree(s.vault_dir, ignore_errors=True)
    tracker = build_tracker(s, ROOT.parent)
    real_call = tracker.call

    def traced(name, args):
        out = real_call(name, args)
        print(f"      [tool] {name}({args}) -> {out.splitlines()[0][:110]}")
        return out
    tracker.call = traced
    brain = Brain(s.llm_model, tracker=tracker)
    await brain.warm()
    lines = iter(SCRIPT)
    while True:
        if live:
            text = await asyncio.to_thread(input, "you> ")
            if text.strip().lower() in ("", "quit", "exit"):
                break
        else:
            text = next(lines, None)
            if text is None:
                break
            print(f"\nYOU: {text}")
        t = time.perf_counter()
        first = None
        out = []
        async for c in brain.stream_reply(text):
            first = first or time.perf_counter() - t
            out.append(c)
        print(f"HIM ({(first or 0):.1f}s to first word, {time.perf_counter() - t:.1f}s total): {''.join(out).strip()}")
    if not live:
        print("\n--- vault ---")
        for f in sorted(Path(s.vault_dir).rglob("*.md")):
            body = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("- ") or l.startswith("status")]
            print(f"{f.relative_to(s.vault_dir).as_posix()}: {body}")

asyncio.run(main())
