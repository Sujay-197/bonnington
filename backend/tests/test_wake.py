import numpy as np
import pytest

from bonnington.hotkey import HotkeyListener
from bonnington.wake import SttWake, match_wake

F = np.zeros(1280, np.int16)
PHRASES = {"britney": "HEY BRITNEY", "bonnington": "HEY BONNINGTON"}


@pytest.mark.parametrize("text,expected", [
    ("Hey Brittany", "britney"),
    ("hey Britney, what's left", "britney"),
    ("Hey Mornington,", "bonnington"),
    ("hey Boydington", "bonnington"),
    ("Hi Bonnington", "bonnington"),
    ("okay Bonnington", "bonnington"),
    ("I listened to Brittany Spears", None),          # no greeting before the name
    ("hey there pretty", None),
    ("Lenovo has finally released its cheapest laptops", None),
])
def test_match_wake(text, expected):
    assert match_wake(text, PHRASES, min_similarity=0.7) == expected


class FakeRecognizer:
    """Scripted partial transcripts, one per fed frame."""

    def __init__(self, script):
        self.it = iter(script)
        self.resets = 0

    def feed(self, frame):
        return next(self.it, None)

    def reset(self):
        self.resets += 1


def test_detects_on_new_text_and_resets_stream():
    rec = FakeRecognizer(["", "hey", "hey Brittany"])
    w = SttWake(PHRASES, recognizer=rec)
    assert [w.feed(F) for _ in range(3)] == [None, None, "britney"]
    assert rec.resets == 1


def test_cooldown_suppresses_repeats():
    rec = FakeRecognizer(["hey Brittany"] * 30)
    w = SttWake(PHRASES, cooldown_s=2.0, recognizer=rec)
    hits = [w.feed(F) for _ in range(30)]
    assert hits.count("britney") == 2 and hits[0] == "britney"


def test_long_text_without_wake_resets_stream():
    rec = FakeRecognizer([" ".join(["blah"] * 40)])
    w = SttWake(PHRASES, recognizer=rec)
    assert w.feed(F) is None and rec.resets == 1


def test_hotkey_parses_combo():
    HotkeyListener("<ctrl>+<alt>+b", lambda: None)
    with pytest.raises(ValueError):
        HotkeyListener("not a combo++", lambda: None)
