"""End-to-end smoke test without a mic: feeds a recorded clip through the real VAD, STT, brain and TTS.

Audio output goes to a null device. Usage (from das_v0): python backend/scripts/e2e_file.py data/bench/02.wav
"""
import asyncio
import sys
import time

import numpy as np
import soundfile as sf

from bonnington.audio.player import AudioPlayer
from bonnington.brain.llm import Brain
from bonnington.config import load_settings
from bonnington.orchestrator import Deps, Orchestrator
from bonnington.store import GrudgeStore
from bonnington.stt import build_stt
from bonnington.tts import TTSEngine
from bonnington.vad import TurnDetector
from bonnington.wake import SttWake

T0 = time.monotonic()


class NullStream:
    def __init__(self, samplerate, **_):
        self.sr = samplerate

    def start(self): pass
    def stop(self): pass
    def close(self): pass

    def write(self, block):
        time.sleep(len(block) / self.sr)


class Bridge:
    def broadcast(self, ev):
        if ev.type != "amplitude":
            print(f"[{time.monotonic() - T0:6.1f}s] {ev.to_json()}", flush=True)


class FileSource:
    """Silence in real time; once the orchestrator is truly listening, plays the clip once, then silence."""

    def __init__(self, clip):
        self.clip = clip
        self.orch = None
        self.is_open = True
        self.done = False

    async def open(self): pass
    async def close(self): pass

    async def frames(self):
        silence = np.zeros(1280, np.int16)
        pos = None
        quiet_after = 0
        while not self.done:
            await asyncio.sleep(0.08)
            if pos is None and self.orch.state == "listening" and not self.orch.loading:
                pos = 0
            if pos is not None and pos + 1280 <= len(self.clip):
                yield self.clip[pos:pos + 1280]
                pos += 1280
            else:
                yield silence
                if pos is not None and self.orch.state == "idle":
                    quiet_after += 1
                    if quiet_after > 10:
                        self.done = True


async def main():
    s = load_settings("data/settings.json")
    clip = sf.read(sys.argv[1], dtype="int16")[0].reshape(-1)
    src = FileSource(clip)
    player = AudioPlayer(lambda v: None, stream_factory=NullStream)
    deps = Deps(source=src, wake=SttWake(s.wake_phrases, s, min_similarity=s.wake_similarity),
                turn=TurnDetector(silence_ms=s.turn_silence_ms), stt=build_stt(s), brain=Brain(s.llm_model), tts=TTSEngine(s),
                player=player, bridge=Bridge(), store=GrudgeStore("data/e2e_test.db"), settings=s)
    orch = Orchestrator(deps)
    src.orch = orch
    orch.trigger("hotkey")
    await asyncio.wait_for(orch.run(), 180)
    await orch.go_dormant()
    print("E2E DONE", flush=True)

asyncio.run(main())
