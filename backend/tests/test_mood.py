from bonnington.brain.mood import MoodParser


def test_mood_tag_split_across_chunks():
    p = MoodParser("neutral")
    out = p.feed("<mo") + p.feed("od:annoyed>Britney") + p.feed(". Again.")
    assert out == "Britney. Again." and p.mood == "annoyed"


def test_missing_tag_keeps_previous_mood():
    p = MoodParser("smug")
    assert p.feed("Well then.") == "Well then." and p.mood == "smug"


def test_invalid_tag_stripped_and_mood_unchanged():
    p = MoodParser("neutral")
    assert p.feed("<mood:furious>Hm.") == "Hm." and p.mood == "neutral"


def test_tag_not_at_start_is_left_alone():
    p = MoodParser("neutral")
    assert p.feed("Hm <mood:smug>") == "Hm <mood:smug>"


def test_leading_whitespace_before_tag_ok():
    p = MoodParser("neutral")
    assert p.feed("  <mood:smug> Oh.") == "Oh." and p.mood == "smug"


def test_reset_keeps_mood_and_accepts_new_tag():
    p = MoodParser("neutral")
    p.feed("<mood:amused>Ha.")
    p.reset()
    assert p.mood == "amused"
    assert p.feed("<mood:serious>Focus.") == "Focus." and p.mood == "serious"


def test_short_reply_without_tag_flushes():
    p = MoodParser("neutral")
    assert p.feed("<m") == ""
    assert p.flush() == "<m"
