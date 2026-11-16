import json

import websockets

from bonnington.bridge import UIBridge
from bonnington.events import MoodEvent, StateEvent


async def test_bridge_binds_localhost_and_replays_state(unused_tcp_port):
    b = UIBridge(unused_tcp_port)
    await b.start()
    b.broadcast(StateEvent("thinking"))
    b.broadcast(MoodEvent("annoyed"))
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws:
        got = {json.loads(await ws.recv())["type"] for _ in range(2)}
    assert got == {"state", "mood"}
    assert all(s.getsockname()[0] == "127.0.0.1" for s in b.server.sockets)
    await b.stop()


async def test_broadcast_reaches_connected_client(unused_tcp_port):
    b = UIBridge(unused_tcp_port)
    await b.start()
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws:
        await b.wait_for_clients(1)
        b.broadcast(StateEvent("speaking"))
        assert json.loads(await ws.recv()) == {"type": "state", "value": "speaking"}
    await b.stop()


def test_broadcast_without_clients_does_not_raise():
    UIBridge(1).broadcast(StateEvent("idle"))


async def test_many_events_arrive_in_order(unused_tcp_port):
    from bonnington.events import AmplitudeEvent
    b = UIBridge(unused_tcp_port)
    await b.start()
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws:
        await b.wait_for_clients(1)
        for i in range(200):
            b.broadcast(AmplitudeEvent(i / 1000))
        got = [json.loads(await ws.recv())["value"] for _ in range(200)]
    assert got == [round(i / 1000, 3) for i in range(200)]
    await b.stop()


async def test_a_web_page_cannot_connect(unused_tcp_port):
    import pytest
    from websockets.exceptions import InvalidStatus
    b = UIBridge(unused_tcp_port)
    await b.start()
    b.broadcast(StateEvent("thinking"))
    with pytest.raises(InvalidStatus):
        async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}", origin="https://evil.example"):
            pass
    await b.stop()


async def test_the_app_window_can_connect(unused_tcp_port):
    b = UIBridge(unused_tcp_port)
    await b.start()
    b.broadcast(StateEvent("thinking"))
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}", origin="http://tauri.localhost") as ws:
        assert json.loads(await ws.recv())["type"] == "state"
    await b.stop()
