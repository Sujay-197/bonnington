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
