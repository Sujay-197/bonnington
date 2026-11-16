import numpy as np

from bonnington.vad import TurnDetector

F = np.zeros(1280, np.int16)


def test_turn_end_after_silence(fake_vad):
    td = TurnDetector(silence_ms=700, vad=fake_vad([1] * 5 + [0] * 9))
    events = [td.feed(F) for _ in range(14)]
    assert events[0] == "speech_start" and events[-1] == "turn_end"
    assert events.count("turn_end") == 1


def test_turn_capped_at_max(fake_vad):
    td = TurnDetector(max_turn_s=0.8, vad=fake_vad([1] * 20))
    assert "turn_end" in [td.feed(F) for _ in range(11)]


def test_silence_only_never_starts(fake_vad):
    td = TurnDetector(vad=fake_vad([0] * 30))
    assert {td.feed(F) for _ in range(30)} == {None}


def test_short_gap_does_not_end_turn(fake_vad):
    td = TurnDetector(silence_ms=700, vad=fake_vad([1, 0, 0, 0, 1, 0, 0]))
    assert [td.feed(F) for _ in range(7)].count("turn_end") == 0


def test_default_pause_before_turn_end_is_one_second(fake_vad):
    td = TurnDetector(vad=fake_vad([1] * 3 + [0] * 13))
    events = [td.feed(F) for _ in range(16)]
    assert events.index("turn_end") == 15          # 13 x 80 ms = 1040 ms of silence
