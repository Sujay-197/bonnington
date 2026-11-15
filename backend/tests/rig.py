"""Test rig for the Orchestrator: every dependency faked, time driven by mic frames (80 ms each)."""

from __future__ import annotations

import asyncio
import math
from collections import deque
from datetime import datetime, timedelta

import numpy as np

from bonnington.config import Settings
from bonnington.events import MoodEvent, StateEvent, SubtitleLineEvent, UserPartialEvent
from bonnington.orchestrator import Deps, Orchestrator
from bonnington.store import GrudgeStore
from bonnington.tts import Utterance

FRAME_S = 0.08
SETTLE_FRAMES = 130  # longer than the 8 s follow-up window (100 frames)
BASE_TIME = datetime(2026, 11, 15, 22, 0)


class FakeSource:
    def __init__(self, rig):
        self.rig = rig
        self.is_open = True

    async def open(self):
        self.is_open = True

    async def close(self):
        self.is_open = False

    async def frames(self):
        frame = np.zeros(1280, np.int16)
        while not self.rig.finished():
            yield frame
            self.rig.frames += 1
            self.rig.track_idle()
            for _ in range(4):
                await asyncio.sleep(0)


class FakeWake:
    def __init__(self, rig):
        self.rig = rig
        self.at: dict[int, str] = {}
        self.during_speaking: str | None = None

    def feed(self, frame):
        if self.rig.frames in self.at:
            return self.at.pop(self.rig.frames)
        if self.during_speaking and self.rig.orch.state == "speaking":
            kind, self.during_speaking = self.during_speaking, None
            return kind
        return None

    def reset(self):
        pass


class FakeTurn:
    """Scripted turns: (silent frames before speech, speech frames)."""

    def __init__(self, rig):
        self.rig = rig
        self.turns: deque[tuple[int, int]] = deque()
        self.cur: list[int] | None = None  # [pre_silence_left, speech_left, started]

    def feed(self, frame):
        if self.cur is None:
            if self.turns:
                pre, speech = self.turns.popleft()
            elif self.rig.orch.state == "listening":
                pre, speech = 0, 4
            else:
                return None
            self.cur = [pre, speech, 0]
        if self.cur[0] > 0:
            self.cur[0] -= 1
            return None
        if not self.cur[2]:
            self.cur[2] = 1
            return "speech_start"
        self.cur[1] -= 1
        if self.cur[1] <= 0:
            self.cur = None
            return "turn_end"
        return None

    def reset(self):
        if self.cur is not None and self.cur[2]:
            self.cur = None


class FakeSTT:
    def __init__(self):
        self.is_loaded = False
        self.partials: deque[str] = deque()
        self.finals: deque[str] = deque()

    def load(self):
        self.is_loaded = True

    def unload(self):
        self.is_loaded = False

    def start_turn(self):
        pass

    def feed(self, frame):
        return self.partials.popleft() if self.partials else None

    def finish(self):
        return self.finals.popleft() if self.finals else "hello"


class FakeBrain:
    def __init__(self):
        self.replies: deque[str] = deque()
        self.raise_exc: Exception | None = None
        self.inputs: list[str] = []
        self.resets = 0
        self.unloaded = False

    async def warm(self):
        if self.raise_exc:
            raise self.raise_exc

    async def unload(self):
        self.unloaded = True

    def reset_session(self):
        self.resets += 1

    async def stream_reply(self, text):
        self.inputs.append(text)
        if self.raise_exc:
            raise self.raise_exc
        reply = self.replies.popleft() if self.replies else "<mood:neutral>Fine."
        for i in range(0, len(reply), 5):
            await asyncio.sleep(0)
            yield reply[i:i + 5]


class FakeTTS:
    def __init__(self):
        self.is_loaded = False

    def load(self):
        self.is_loaded = True

    def unload(self):
        self.is_loaded = False

    def synth(self, s):
        return Utterance(np.zeros(2400, np.float32), 24000, s, [0])


class FakePlayer:
    PLAY_FRAMES = 5

    def __init__(self, rig):
        self.rig = rig
        self.played: list[str] = []
        self.stops = 0
        self._stopped = False
        self.is_playing = False

    def stop(self):
        self.stops += 1
        self._stopped = True

    async def play(self, u):
        self._stopped = False
        self.is_playing = True
        self.played.append(u.text)
        target = self.rig.frames + self.PLAY_FRAMES
        try:
            while self.rig.frames < target:
                if self._stopped:
                    return False
                await asyncio.sleep(0)
            return not self._stopped
        finally:
            self.is_playing = False


class Rig:
    def __init__(self, tmp_path):
        self.frames = 0
        self.events: list = []
        self.settings = Settings()
        self.store = GrudgeStore(tmp_path / "b.db")
        self.wake = FakeWake(self)
        self.turn = FakeTurn(self)
        self.stt = FakeSTT()
        self.brain = FakeBrain()
        self.tts = FakeTTS()
        self.player = FakePlayer(self)
        self.load_delay_frames = 0
        self._played_files: list[str] = []
        self._active = False
        self._idle_streak = 0
        self._max_frames = 3000
        deps = Deps(source=FakeSource(self), wake=self.wake, turn=self.turn, stt=self.stt,
                    brain=self.brain, tts=self.tts, player=self.player, bridge=self,
                    store=self.store, settings=self.settings,
                    now=lambda: BASE_TIME + timedelta(seconds=self.clock()),
                    run_blocking=self.run_blocking, play_file=self.play_file)
        self.orch = Orchestrator(deps, clock=self.clock, sleep=self.sleep)

    # --- plumbing -------------------------------------------------------------
    def broadcast(self, ev):
        self.events.append(ev)

    def clock(self) -> float:
        return self.frames * FRAME_S

    async def wait_frames(self, n: int):
        target = self.frames + n
        while self.frames < target and not self.finished():
            await asyncio.sleep(0)

    async def sleep(self, seconds: float):
        await self.wait_frames(math.ceil(seconds / FRAME_S))

    async def run_blocking(self, fn, *args):
        if fn == self.stt.load and self.load_delay_frames:
            await self.wait_frames(self.load_delay_frames)
        return fn(*args)

    async def play_file(self, path: str):
        self._played_files.append(path)

    def track_idle(self):
        if self.orch.state == "idle" and not self.orch.loading:
            self._idle_streak += 1
        else:
            self._active = True
            self._idle_streak = 0

    def finished(self) -> bool:
        if self.frames >= self._max_frames:
            return True
        return self._active and self._idle_streak >= SETTLE_FRAMES

    async def run_until_idle(self):
        await asyncio.wait_for(self.orch.run(), timeout=30)

    # --- scripting ------------------------------------------------------------
    def wake_on_frame(self, i: int, kind: str):
        self.wake.at[i] = kind

    def speech(self, frames: range):
        self.turn.turns.append((0, len(frames)))

    def stt_final(self, text: str):
        self.stt.finals.append(text)

    def stt_partials(self, texts: list[str]):
        self.stt.partials.extend(texts)

    def brain_says(self, text: str):
        self.brain.replies.append(text)

    def brain_raises(self, exc: Exception):
        self.brain.raise_exc = exc

    def during_speaking_wake(self, kind: str):
        self.wake.during_speaking = kind

    def load_takes(self, seconds: float):
        self.load_delay_frames = math.ceil(seconds / FRAME_S)

    def two_turns_in_followup(self):
        self.wake_on_frame(0, "britney")
        self.turn.turns.extend([(0, 4), (10, 4)])
        self.stt.finals.extend(["first", "second"])

    def reply_then_speech_after(self, seconds: float):
        self.wake_on_frame(0, "britney")
        self.turn.turns.extend([(0, 4), (round(seconds / FRAME_S), 4)])

    # --- observations ---------------------------------------------------------
    def event_types(self) -> list[str]:
        out = []
        for e in self.events:
            if isinstance(e, (StateEvent, MoodEvent)):
                out.append(f"{e.type}:{e.value}")
            else:
                out.append(e.type)
        return out

    def subtitles(self) -> list[str]:
        return [e.text for e in self.events if isinstance(e, SubtitleLineEvent)]

    def user_partials(self) -> list[str]:
        return [e.text for e in self.events if isinstance(e, UserPartialEvent)]

    def spoken(self) -> list[str]:
        return list(self.player.played)

    def played_files(self) -> list[str]:
        return list(self._played_files)

    @property
    def brain_inputs(self) -> list[str]:
        return self.brain.inputs

    @property
    def brain_calls(self) -> int:
        return len(self.brain.inputs)
