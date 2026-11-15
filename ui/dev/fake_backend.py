"""Stand-in backend for looking at the window without mic or models.

Serves the UI's WebSocket on 127.0.0.1:8770 with real dashboard data built from a scratch vault and
your real project history, and cycles through a short scripted conversation.
Run from das_v0:  uv run --no-sync --project backend python ui/dev/fake_backend.py
Then open ui/src/index.html?port=8770 (or run a static server on ui/src).
"""
import asyncio
import shutil
from datetime import date, time, timedelta
from pathlib import Path

from bonnington.bridge import UIBridge
from bonnington.config import Settings
from bonnington.events import AmplitudeEvent, MoodEvent, StateEvent, SubtitleLineEvent, UserFinalEvent
from bonnington.presenter import Presenter
from bonnington.tts import estimate_word_offsets
from bonnington.vault.tools import build_tracker

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = [
    ("What's left for this week?", "serious", "One lab report by Friday, an exam in nine days, and something already overdue. Splendid."),
    ("What was I last doing in medrag?", "smug", "You were last asking whether you really need containers. You do not."),
    ("How am I doing in DBMS?", "amused", "Seventy-three percent. Respectable, in the way beige is a colour."),
    ("I have a CN quiz tomorrow at ten.", "neutral", "Filed. CN quiz, tomorrow, ten a.m."),
]


async def main() -> None:
    s = Settings()
    s.vault_dir = str(ROOT / "data" / "vault_demo")
    shutil.rmtree(s.vault_dir, ignore_errors=True)
    tracker = build_tracker(s, ROOT.parent)
    today = date.today()
    v = tracker.vault
    v.add_exam("DBMS", today + timedelta(days=9), time(9, 0), title="Midterm 2")
    v.add_assignment("CN", "Lab report 3", today + timedelta(days=5))
    v.add_assignment("Bio", "Assignment 2", today - timedelta(days=3))
    v.add_task("Renew passport", today + timedelta(days=16))
    v.add_task("Call the bank")
    v.add_score("DBMS", "Midterm 1", 38, 50, today - timedelta(days=5))
    v.add_score("DBMS", "Quiz 1", 6, 10, today - timedelta(days=12))
    v.add_score("CN", "Quiz 1", 16, 25, today - timedelta(days=8))

    bridge = UIBridge(8770)
    await bridge.start()
    p = Presenter(tracker, bridge, britney_count=lambda: 214, mic="phone", models_loaded=lambda: True)
    tracker.on_change, tracker.on_tool = p.changed, p.tool_ran
    p.refresh()
    print("fake backend on ws://127.0.0.1:8770", flush=True)
    line_id = 0
    while True:
        for user, mood, reply in SCRIPT:
            bridge.broadcast(StateEvent("idle"))
            await asyncio.sleep(4)
            bridge.broadcast(StateEvent("listening"))
            await asyncio.sleep(1.5)
            bridge.broadcast(UserFinalEvent(user))
            p.user_said(user)
            bridge.broadcast(StateEvent("thinking"))
            await asyncio.sleep(1.2)
            if "quiz tomorrow" in user:
                tracker.call("add_exam", {"subject": "CN", "date": "tomorrow", "time": "10am", "title": "Quiz"})
            bridge.broadcast(MoodEvent(mood))
            bridge.broadcast(StateEvent("speaking"))
            line_id += 1
            dur = int(len(reply) * 65)
            bridge.broadcast(SubtitleLineEvent(line_id, reply, dur, estimate_word_offsets(reply, dur)))
            for i in range(dur // 100):
                bridge.broadcast(AmplitudeEvent(0.3 + 0.3 * abs((i % 7) - 3) / 3))
                await asyncio.sleep(0.1)
            bridge.broadcast(AmplitudeEvent(0))
            p.reply_done(reply)
            bridge.broadcast(StateEvent("listening"))
            await asyncio.sleep(4)
            p.session_ended()
        if tracker.vault.exams():
            try:
                tracker.vault.remove("exam", "CN Quiz")
            except Exception:
                pass
            p.refresh()

asyncio.run(main())
