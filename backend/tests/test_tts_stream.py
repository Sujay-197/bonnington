import asyncio
import queue
import threading
import time

import numpy as np

from bonnington.audio.player import AudioPlayer
from bonnington.config import Settings
from bonnington.tts import TTSEngine, Utterance


class FakeModel:
    """Stands in for FasterQwen3TTS: yields `n` chunks of 0.1 s, `delay` s apart."""

    def __init__(self, n=5, delay=0.02):
        self.n, self.delay, self.active, self.max_active, self.calls = n, delay, 0, 0, []

    def generate_voice_clone_streaming(self, text, **kw):
        self.calls.append(text)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            for _ in range(self.n):
                time.sleep(self.delay)
                yield np.full(2400, 0.1, np.float32), 24000, {}
        finally:
            self.active -= 1


def engine(model):
    e = TTSEngine(Settings())
    e._model = model
    return e


def drain(u):
    out = []
    while True:
        c = u.stream.get(timeout=2)
        if c is None:
            return out
        out.append(c)


def test_synth_returns_after_first_chunk_and_streams_the_rest():
    e = engine(FakeModel(n=5, delay=0.05))
    t = time.perf_counter()
    u = e.synth("Britney. Again.")
    assert time.perf_counter() - t < 0.2          # did not wait for all 5 chunks (0.25 s)
    assert u.sample_rate == 24000 and u.text == "Britney. Again."
    assert sum(len(c) for c in drain(u)) == 5 * 2400


def test_estimated_duration_and_offsets_available_immediately():
    u = engine(FakeModel()).synth("Britney. Again. Really.")
    assert u.duration_ms > 0 and len(u.word_offsets_ms) == 3 and u.word_offsets_ms[0] == 0
    drain(u)


def test_generations_never_overlap():
    m = FakeModel(n=4, delay=0.02)
    e = engine(m)
    a = e.synth("One.")
    b = e.synth("Two.")          # must wait for "One." to finish generating
    drain(a), drain(b)
    assert m.max_active == 1 and m.calls == ["One.", "Two."]


def test_cancel_stops_generation_early():
    m = FakeModel(n=200, delay=0.01)
    e = engine(m)
    u = e.synth("A very long sentence.")
    e.cancel()
    chunks = drain(u)
    assert len(chunks) < 50 and m.active == 0


def test_duration_estimate_learns_from_real_audio():
    e = engine(FakeModel(n=10, delay=0.0))        # 1.0 s of audio for 10 characters
    drain(e.synth("0123456789"))
    time.sleep(0.05)
    assert abs(e.synth("0123456789").duration_ms - 1000) < 300


async def test_player_plays_a_streamed_utterance(fake_output_stream):
    amps = []
    p = AudioPlayer(amps.append, stream_factory=fake_output_stream)
    q = queue.Queue()
    u = Utterance(np.zeros(0, np.float32), 24000, "x", [0], stream=q, est_duration_ms=200)

    def feed():
        for _ in range(3):
            time.sleep(0.02)
            q.put(np.full(1600, 0.25, np.float32))
        q.put(None)
    threading.Thread(target=feed, daemon=True).start()
    assert await p.play(u) is True
    assert max(amps) == 1.0 and amps[-1] == 0.0


async def test_player_stop_interrupts_a_streamed_utterance(fake_output_stream):
    p = AudioPlayer(lambda v: None, stream_factory=fake_output_stream)
    q = queue.Queue()
    for _ in range(50):
        q.put(np.zeros(2400, np.float32))
    u = Utterance(np.zeros(0, np.float32), 24000, "x", [0], stream=q, est_duration_ms=5000)
    task = asyncio.create_task(p.play(u))
    await asyncio.sleep(0.15)
    p.stop()
    assert await task is False
