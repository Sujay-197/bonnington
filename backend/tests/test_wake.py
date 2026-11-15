import numpy as np
import pytest

from bonnington.hotkey import HotkeyListener
from bonnington.wake import KeywordWake, keyword_line

F = np.zeros(1280, np.int16)
PHRASES = {"britney": "HEY BRITNEY", "bonnington": "HEY BONNINGTON"}


class FakeSpotter:
    def __init__(self, script):
        self.it = iter(script)
        self.resets = 0

    def feed(self, frame):
        return next(self.it, "")

    def reset(self):
        self.resets += 1


def test_detects_and_maps_label():
    w = KeywordWake(PHRASES, spotter=FakeSpotter(["", "bonnington"]))
    assert [w.feed(F), w.feed(F)] == [None, "bonnington"]


def test_cooldown_suppresses_repeats():
    w = KeywordWake(PHRASES, cooldown_s=2.0, spotter=FakeSpotter(["britney"] * 30))
    hits = [w.feed(F) for _ in range(30)]
    assert hits.count("britney") == 2 and hits[0] == "britney"


def test_unknown_label_ignored():
    w = KeywordWake(PHRASES, spotter=FakeSpotter(["alexa"]))
    assert w.feed(F) is None


def test_keyword_line_format():
    line = keyword_line(["▁HE", "Y", "▁B", "RI", "T", "NE", "Y"], "britney", boost=1.5, threshold=0.3)
    assert line == "▁HE Y ▁B RI T NE Y :1.5 #0.3 @britney"


def test_hotkey_parses_combo():
    HotkeyListener("<ctrl>+<alt>+b", lambda: None)
    with pytest.raises(ValueError):
        HotkeyListener("not a combo++", lambda: None)
