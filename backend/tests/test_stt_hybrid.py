import numpy as np
import pytest

from bonnington.stt import HybridSTT
from bonnington.wake import normalise_names

F = np.zeros(1280, np.int16)


class FakeSTT:
    def __init__(self, partial=None, final=""):
        self.is_loaded = False
        self.partial, self.final = partial, final
        self.fed = self.starts = 0

    def load(self): self.is_loaded = True
    def unload(self): self.is_loaded = False
    def start_turn(self): self.starts += 1

    def feed(self, frame):
        self.fed += 1
        return self.partial

    def finish(self): return self.final


def test_partials_from_streaming_final_from_accurate():
    live, acc = FakeSTT(partial="am i", final="main eye moving"), FakeSTT(final="Am I moving slowly?")
    h = HybridSTT(live, acc)
    h.load()
    h.start_turn()
    assert h.feed(F) == "am i"
    assert h.finish() == "Am I moving slowly?"
    assert live.fed == acc.fed == 1 and live.starts == acc.starts == 1 and h.is_loaded


def test_falls_back_to_streaming_final_when_accurate_is_empty():
    h = HybridSTT(FakeSTT(final="hello"), FakeSTT(final=""))
    h.load()
    h.start_turn()
    assert h.finish() == "hello"


def test_unload_unloads_both():
    live, acc = FakeSTT(), FakeSTT()
    h = HybridSTT(live, acc)
    h.load()
    h.unload()
    assert not live.is_loaded and not acc.is_loaded and not h.is_loaded


@pytest.mark.parametrize("heard,fixed", [
    ("Hello mornings and how are you", "Hello mornings and how are you"),
    ("Mornington, tell me something useful", "Bonnington, tell me something useful"),
    ("Hey Bonington", "Hey Bonnington"),
    ("hey Boydington what's up", "hey Bonnington what's up"),
    ("Hey Brittany.", "Hey Britney."),
    ("I flew to Washington this morning", "I flew to Washington this morning"),
])
def test_normalise_names(heard, fixed):
    assert normalise_names(heard) == fixed
