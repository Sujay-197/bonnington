import socket

import pytest


@pytest.fixture
def unused_tcp_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeOllama:
    """Stands in for ollama.AsyncClient: scripted streamed chunks, records every call."""

    def __init__(self):
        self.script: list[str] = []
        self.calls: list[dict] = []
        self.raise_on_chat: Exception | None = None

    async def chat(self, **kw):
        self.calls.append(kw)
        if self.raise_on_chat is not None:
            raise self.raise_on_chat
        if not kw.get("stream"):
            return {"message": {"content": ""}}

        async def gen():
            for s in self.script:
                yield {"message": {"content": s}}
        return gen()


@pytest.fixture
def fake_ollama():
    return FakeOllama()


class FakeOutputStream:
    """Mimics sounddevice.OutputStream: write() blocks for the block's real duration."""

    def __init__(self, samplerate, channels=1, dtype="float32", **_):
        self.samplerate = samplerate
        self.written = 0
        self.closed = False

    def start(self):
        pass

    def write(self, block):
        import time
        self.written += len(block)
        time.sleep(len(block) / self.samplerate)

    def stop(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def fake_output_stream():
    return FakeOutputStream


class CallbackStream:
    """Mimics sounddevice.InputStream in callback mode. Delivers `frames` blocks (None = forever) then goes silent."""

    def __init__(self, callback, blocksize, frames=None, start_delay=0.0):
        import threading
        self.callback, self.blocksize, self.frames, self.start_delay = callback, blocksize, frames, start_delay
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        import time

        import numpy as np
        n = 0
        time.sleep(self.start_delay)
        while not self._stop.is_set() and (self.frames is None or n < self.frames):
            self.callback(np.zeros((self.blocksize, 1), np.int16), self.blocksize, None, None)
            n += 1
            time.sleep(0.002)

    def start(self):
        self._t.start()

    def abort(self):
        self._stop.set()

    stop = abort

    def close(self):
        self._stop.set()


class StallingFactory:
    """First stream stalls after `stall_after` blocks; later streams are healthy."""

    def __init__(self, stall_after, start_delay=0.0):
        self.stall_after, self.opens, self.kw, self.start_delay = stall_after, 0, {}, start_delay

    def __call__(self, **kw):
        self.opens += 1
        self.kw = kw
        frames = self.stall_after if self.opens == 1 else None
        return CallbackStream(kw["callback"], kw["blocksize"], frames, self.start_delay)


@pytest.fixture
def stalling_factory():
    return StallingFactory


@pytest.fixture
def fake_vad():
    def make(script):
        it = iter(script)
        return lambda frame: bool(next(it, 0))
    return make



@pytest.fixture
def rig(tmp_path):
    from rig import Rig
    return Rig(tmp_path)


class FakeRegistry:
    def __init__(self):
        self._rows = []

    def add(self, path, last_stop, last_start=1):
        self._rows.append((path, last_start, last_stop))

    def entries(self):
        return list(self._rows)


@pytest.fixture
def fake_registry():
    return FakeRegistry()


class _FakeMic:
    def __init__(self):
        self.is_open = True

    async def open(self):
        self.is_open = True

    async def close(self):
        self.is_open = False


class _FakeUI:
    def __init__(self):
        self.shown = False

    def show(self):
        self.shown = True

    def hide(self):
        self.shown = False


class _FakeOrch:
    def __init__(self, world):
        self.world = world
        self.unloaded = False
        self.last_interaction = 0.0
        self.on_wake_requested = None
        self.on_session_end = None
        self.active = False

    async def go_dormant(self):
        self.unloaded = True


class FakeWorld:
    def __init__(self):
        self.fullscreen = False
        self.mic_busy = False
        self.now = 0.0
        self.mic = _FakeMic()
        self.ui = _FakeUI()
        self.orch = _FakeOrch(self)
        self._c = None

    def controller(self):
        from bonnington.lifecycle import LifecycleController
        self._c = LifecycleController(self.orch, self.mic, self.ui, idle_unload_s=600,
                                      probe=lambda: (self.fullscreen, self.mic_busy),
                                      clock=lambda: self.now)
        return self._c

    def wake(self):
        self._c.request_wake()

    async def tick(self):
        await self._c.step()


@pytest.fixture
def fake_world():
    return FakeWorld()
