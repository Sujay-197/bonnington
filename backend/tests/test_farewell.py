import pytest

from bonnington.orchestrator import is_farewell


@pytest.mark.parametrize("text,expected", [
    ("Alright then, Bora, that's it for today. Bye-bye.", True),
    ("Okay bye", True),
    ("Goodbye Bonnington", True),
    ("good night", True),
    ("That's all for now.", True),
    ("you can go now", True),
    ("go to sleep", True),
    ("we're done here", True),
    ("that's it, the exam is on the 24th", False),
    ("I said goodbye to my free time", False),
    ("What's left for this week?", False),
    ("I'm done with the passport task", False),
    ("", False),
])
def test_is_farewell(text, expected):
    assert is_farewell(text) is expected
