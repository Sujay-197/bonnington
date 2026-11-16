import asyncio
import json
import ssl

import numpy as np
import pytest
import websockets

from bonnington.audio.phone import PhoneMicSource, authorised, ensure_cert, page_html

TOKEN = "482913"
SESSION = "paired-phone-secret-0123456789abcdef"


async def _take(src, n):
    out = []
    async for f in src.frames():
        out.append(f)
        if len(out) == n:
            return out


def _src(port):
    return PhoneMicSource(port=port, token=TOKEN, host="127.0.0.1", ssl_context=None, lan_ip="127.0.0.1",
                          session=SESSION)


@pytest.mark.parametrize("path,ok", [
    ("/ws?t=482913", True),
    ("/?t=482913", True),
    ("/ws?t=wrong", False),
    ("/ws", False),
    ("/ws?t=", False),
])
def test_authorised(path, ok):
    assert authorised(path, TOKEN) is ok


def test_page_contains_token_and_asks_for_16k_mono():
    html = page_html(TOKEN)
    assert "482913" in html and "16000" in html and "getUserMedia" in html


async def test_phone_audio_arrives_as_80ms_frames(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    await src.open()
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}") as ws:
        samples = (np.arange(2560) % 100).astype(np.int16)
        await ws.send(samples[:1000].tobytes())       # arbitrary chunk sizes
        await ws.send(samples[1000:].tobytes())
        frames = await asyncio.wait_for(_take(src, 2), 3)
    assert [f.shape for f in frames] == [(1280,), (1280,)]
    assert np.array_equal(np.concatenate(frames), samples)
    await src.stop()


async def test_wrong_token_is_rejected(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    with pytest.raises(websockets.exceptions.InvalidStatus):
        async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?t=nope"):
            pass
    assert not src.connected
    await src.stop()


async def test_silence_and_a_hint_while_no_phone_is_connected(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    await src.open()
    frames = await asyncio.wait_for(_take(src, 3), 3)
    assert all(not f.any() for f in frames) and frames[0].shape == (1280,)
    hint = src.status_hint()
    assert f"https://127.0.0.1:{unused_tcp_port}" in hint and "482913" in hint and "?t=" not in hint
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}"):
        await asyncio.sleep(0.05)
        assert src.connected and src.status_hint() is None
    await src.stop()


async def test_open_and_close_tell_the_phone_to_capture_or_pause(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}") as ws:
        assert json.loads(await asyncio.wait_for(ws.recv(), 2)) == {"capture": False}   # state on connect
        await src.open()
        assert json.loads(await asyncio.wait_for(ws.recv(), 2)) == {"capture": True}
        await src.close()
        assert json.loads(await asyncio.wait_for(ws.recv(), 2)) == {"capture": False}
    await src.stop()


async def test_audio_sent_while_closed_is_dropped(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}") as ws:
        await ws.send(np.ones(1280, np.int16).tobytes())     # closed: dropped
        await asyncio.sleep(0.05)
        await src.open()
        await ws.send(np.full(1280, 7, np.int16).tobytes())
        (frame,) = await asyncio.wait_for(_take(src, 1), 3)
    assert frame[0] == 7
    await src.stop()


async def test_page_is_served_over_http_with_token(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
    writer.write(f"GET /?t={TOKEN} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
    body = (await asyncio.wait_for(reader.read(), 3)).decode()
    writer.close()
    assert "200" in body.splitlines()[0] and "getUserMedia" in body
    await src.stop()


def test_ensure_cert_creates_a_loadable_certificate(tmp_path):
    cert, key = ensure_cert(tmp_path, "192.168.1.3")
    assert cert.exists() and key.exists()
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(cert, key)
    assert ensure_cert(tmp_path, "192.168.1.3") == (cert, key)    # reused, not regenerated


async def _get(port, path):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
    body = (await asyncio.wait_for(reader.read(), 3)).decode()
    writer.close()
    return body


async def test_plain_link_shows_a_code_form_not_forbidden(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    body = await _get(unused_tcp_port, "/")
    assert "200" in body.splitlines()[0] and "6-digit code" in body and "getUserMedia" not in body
    assert TOKEN not in body
    await src.stop()


async def test_wrong_code_shows_the_form_again_with_a_message(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    body = await _get(unused_tcp_port, "/?t=000000")
    assert "200" in body.splitlines()[0] and "didn't match" in body
    await src.stop()


async def test_too_many_wrong_codes_locks_out(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    for _ in range(8):
        await _get(unused_tcp_port, "/?t=000000")
    body = await _get(unused_tcp_port, f"/?t={TOKEN}")
    assert "429" in body.splitlines()[0]
    await src.stop()


def test_url_is_short():
    assert PhoneMicSource(8766, TOKEN, lan_ip="192.168.1.3").url == "https://192.168.1.3:8766"


async def test_connection_changes_are_reported(unused_tcp_port):
    src = _src(unused_tcp_port)
    seen = []
    src.on_connection_change = lambda: seen.append(src.connected)
    await src.start()
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}"):
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.1)
    assert seen == [True, False]
    assert src.mic_status() == "PHONE · NOT CONNECTED"
    await src.stop()
