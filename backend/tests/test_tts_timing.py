from bonnington.tts import estimate_word_offsets


def test_offsets_start_at_zero_and_increase():
    o = estimate_word_offsets("Ah. Britney. Again.", 1500)
    assert o[0] == 0 and o == sorted(o) and len(o) == 3 and o[-1] < 1500


def test_pause_after_period_is_longer_than_after_word():
    o = estimate_word_offsets("Hm. a b", 1000)
    assert (o[1] - o[0]) > (o[2] - o[1])


def test_single_word():
    assert estimate_word_offsets("Britney.", 700) == [0]


def test_empty_text():
    assert estimate_word_offsets("   ", 500) == []
