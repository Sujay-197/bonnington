import numpy as np
import pytest

from bonnington.hotkey import HotkeyListener
from bonnington.wake import WakeDetector

F = np.zeros(1280, np.int16)
MODELS = {"britney": "a", "bonnington": "b"}


def test_fires_once_then_cooldown(fake_oww):
    w = WakeDetector(MODELS, 0.5, cooldown_s=2.0, oww=fake_oww([{"britney": .9}] * 30))
    hits = [w.feed(F) for _ in range(30)]
    assert hits.count("britney") == 2 and hits[0] == "britney"


def test_higher_score_wins(fake_oww):
    w = WakeDetector(MODELS, 0.5, oww=fake_oww([{"britney": .6, "bonnington": .8}]))
    assert w.feed(F) == "bonnington"


def test_below_threshold_is_none(fake_oww):
    w = WakeDetector(MODELS, 0.5, oww=fake_oww([{"britney": .49}]))
    assert w.feed(F) is None


def test_model_file_keys_map_to_names(fake_oww):
    w = WakeDetector({"britney": "data/wake/hey_britney.onnx"}, 0.5,
                     oww=fake_oww([{"hey_britney": .9}]))
    assert w.feed(F) == "britney"


def test_hotkey_parses_combo():
    HotkeyListener("<ctrl>+<alt>+b", lambda: None)
    with pytest.raises(ValueError):
        HotkeyListener("not a combo++", lambda: None)
