"""WebSocket bridge to the UI. Binds to 127.0.0.1 only."""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.server import Server, ServerConnection, serve

from .events import UIEvent

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
SNAPSHOT_TYPES = ("state", "mood", "dashboard", "focus")  # replayed to a window that connects later


class UIBridge:
    def __init__(self, port: int) -> None:
        self.port = port
        self.server: Server | None = None
        self._clients: dict[ServerConnection, asyncio.Queue[str]] = {}
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
        if event.type in SNAPSHOT_TYPES:
            self._snapshot[event.type] = msg
        if not self._clients or self._loop is None:
            return
        for q in list(self._clients.values()):
            self._loop.call_soon_threadsafe(q.put_nowait, msg)

    async def _handle(self, ws: ServerConnection) -> None:
        for msg in self.last_state_snapshot():
            await ws.send(msg)
        q: asyncio.Queue[str] = asyncio.Queue()
        self._clients[ws] = q
        self._changed.set()
        async def pump() -> None:
            while True:  # one queue per client keeps event order intact
                await ws.send(await q.get())

        sender = asyncio.create_task(pump())
        try:
            await asyncio.wait({sender, asyncio.create_task(ws.wait_closed())},
                               return_when=asyncio.FIRST_COMPLETED)
        finally:
            sender.cancel()
            self._clients.pop(ws, None)
