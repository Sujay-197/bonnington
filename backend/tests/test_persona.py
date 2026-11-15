from datetime import datetime

from bonnington.brain.persona import build_summons_note, build_system_prompt
from bonnington.store import SummonsContext


def test_system_prompt_pins_persona():
    p = build_system_prompt()
    for must in ["Bonnington", "<mood:", "neutral", "disappointed", "profanity", "short"]:
        assert must in p
    assert "James Spader" not in p


def test_summons_note_britney():
    ctx = SummonsContext("britney", 215, 240.0, 5, datetime(2026, 11, 15, 23, 40))
    n = build_summons_note(ctx)
    assert '"Hey Britney"' in n and "215" in n and "4 min" in n and "23:40" in n


def test_summons_note_first_ever():
    ctx = SummonsContext("bonnington", 0, None, 1, datetime(2026, 11, 15, 9, 5))
    n = build_summons_note(ctx)
    assert "first time" in n.lower() and '"Hey Bonnington"' in n


def test_summons_note_hotkey_and_hours():
    ctx = SummonsContext("hotkey", 3, 7200.0, 1, datetime(2026, 11, 15, 9, 5))
    n = build_summons_note(ctx)
    assert "hotkey" in n and "2 h" in n
