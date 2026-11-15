import asyncio

import numpy as np

from bonnington.audio.player import AudioPlayer
from bonnington.tts import Utterance


async def test_player_stop_returns_false_and_zeroes_amplitude(fake_output_stream):
    amps = []
    p = AudioPlayer(amps.append, stream_factory=fake_output_stream)
    u = Utterance(np.ones(48000, np.float32) * 0.1, 24000, "x", [0])
    task = asyncio.create_task(p.play(u))
    await asyncio.sleep(0.1)
    p.stop()
    assert await task is False and amps[-1] == 0.0 and not p.is_playing


async def test_player_completes_and_reports_amplitude(fake_output_stream):
    amps = []
    p = AudioPlayer(amps.append, stream_factory=fake_output_stream)
    u = Utterance(np.ones(2400, np.float32) * 0.25, 24000, "x", [0])   # 100 ms
    assert await p.play(u) is True
    assert max(amps) == 1.0 and amps[-1] == 0.0 and len(amps) >= 3


async def test_amplitude_scales_with_rms(fake_output_stream):
    amps = []
    p = AudioPlayer(amps.append, stream_factory=fake_output_stream)
    await p.play(Utterance(np.ones(800, np.float32) * 0.05, 24000, "x", [0]))
    assert abs(amps[0] - 0.2) < 1e-6
