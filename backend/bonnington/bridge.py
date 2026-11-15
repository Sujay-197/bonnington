"""WebSocket bridge to the UI. Binds to 127.0.0.1 only."""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import Server, ServerConnection, serve

from .events import MoodEvent, StateEvent, UIEvent

log = logging.getLogger(__name__)

HOST = "127.0.0.1"


class UIBridge:
    def __init__(self, port: int) -> None:
        self.port = port
        self.server: Server | None = None
        self._clients: set[ServerConnection] = set()
        self._snapshot: dict[str, str] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._changed = asyncio.Event()

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.server = await serve(self._handle, HOST, self.port)

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    def last_state_snapshot(self) -> list[str]:
        return list(self._snapshot.values())

    async def wait_for_clients(self, n: int) -> None:
        while len(self._clients) < n:
            self._changed.clear()
            await self._changed.wait()

    def broadcast(self, event: UIEvent) -> None:
        msg = event.to_json()
        if isinstance(event, (StateEvent, MoodEvent)):
            self._snapshot[event.type] = msg
        if not self._clients or self._loop is None:
            return
        for ws in list(self._clients):
            self._loop.call_soon_threadsafe(self._send, ws, msg)

    def _send(self, ws: ServerConnection, msg: str) -> None:
        async def go() -> None:
            try:
                await ws.send(msg)
            except Exception:  # client went away; drop it
                self._clients.discard(ws)
        asyncio.ensure_future(go())

    async def _handle(self, ws: ServerConnection) -> None:
        for msg in self.last_state_snapshot():
            await ws.send(msg)
        self._clients.add(ws)
        self._changed.set()
        try:
            await ws.wait_closed()
        finally:
            self._clients.discard(ws)
