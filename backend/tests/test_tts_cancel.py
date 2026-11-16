"""A sentence still waiting for the speech model when he is interrupted must never be generated."""

import threading
import time

from test_tts_stream import FakeModel, drain, engine


def test_a_sentence_queued_behind_an_interrupted_one_is_never_generated():
    model = FakeModel(n=5, delay=0.05)
    e = engine(model)
    first = e.synth("one")                    # holds the model
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("u", e.synth("two")))
    t.start()                                 # waits for the model, like the next sentence of a reply
    time.sleep(0.05)
    e.cancel()                                # he is interrupted
    drain(first)
    t.join(2)
    assert drain(got["u"]) == []
    assert model.calls == ["one"]


def test_speech_after_an_interruption_works_normally():
    model = FakeModel(n=3, delay=0.01)
    e = engine(model)
    drain(e.synth("one"))
    e.cancel()
    assert len(drain(e.synth("three"))) == 3
    assert model.calls == ["one", "three"]


def test_unload_does_not_wait_for_a_queued_sentence():
    model = FakeModel(n=20, delay=0.05)
    e = engine(model)
    first = e.synth("one")
    threading.Thread(target=lambda: drain(e.synth("two")), daemon=True).start()
    time.sleep(0.05)
    start = time.monotonic()
    e.cancel()
    drain(first)
    with e._gen_lock:                         # what unload() waits for
        pass
    assert time.monotonic() - start < 0.5
    assert model.calls == ["one"]
