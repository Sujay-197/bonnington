import logging
import threading

from bonnington.__main__ import _run_backend


def test_a_startup_failure_is_logged_and_never_hangs_the_tray(caplog):
    state = {"ready": threading.Event()}

    async def broken(_state):
        raise RuntimeError("phone port in use")
    with caplog.at_level(logging.ERROR):
        _run_backend(state, broken)
    assert state["ready"].is_set()
    assert isinstance(state["error"], RuntimeError)
    assert "backend stopped" in caplog.text and "phone port in use" in caplog.text


def test_a_backend_that_dies_later_stops_the_tray():
    stopped = []
    state = {"ready": threading.Event(), "stop_tray": lambda: stopped.append(True)}

    async def dies(s):
        s["ready"].set()
        raise RuntimeError("boom")
    _run_backend(state, dies)
    assert stopped == [True]
