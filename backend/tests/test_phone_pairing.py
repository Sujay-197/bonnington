"""The 6-digit code only pairs a phone; the audio socket needs the long session secret it hands out."""

import asyncio

import pytest
import websockets

from bonnington.audio.phone import LOCKOUT_S, MAX_BAD_CODES, PhoneMicSource

CODE = "482913"
SESSION = "s3ss10n-" + "x" * 32


def _src(port, clock=None):
    return PhoneMicSource(port=port, token=CODE, host="127.0.0.1", ssl_context=None, lan_ip="127.0.0.1",
                          session=SESSION, clock=clock)


async def _get(port, path, cookie=None):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    extra = f"Cookie: {cookie}\r\n" if cookie else ""
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n{extra}Connection: close\r\n\r\n".encode())
    body = (await asyncio.wait_for(reader.read(), 3)).decode()
    writer.close()
    return body


async def test_the_right_code_hands_out_the_session_not_the_code(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    body = await _get(unused_tcp_port, f"/?t={CODE}")
    assert "200" in body.splitlines()[0] and "getUserMedia" in body
    assert f'"{SESSION}"' in body and f'"{CODE}"' not in body
    assert f"bon_s={SESSION}" in body and "HttpOnly" in body
    await src.stop()


async def test_the_bare_code_cannot_open_the_audio_socket(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    with pytest.raises(websockets.exceptions.InvalidStatus):
        async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?t={CODE}"):
            pass
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}"):
        await asyncio.sleep(0.05)
        assert src.connected
    await src.stop()


async def test_a_paired_phone_comes_back_with_its_cookie(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    body = await _get(unused_tcp_port, "/", cookie=f"bon_s={SESSION}")
    assert "getUserMedia" in body
    await src.stop()


async def test_a_paired_phone_is_never_locked_out(unused_tcp_port):
    src = _src(unused_tcp_port)
    await src.start()
    for _ in range(MAX_BAD_CODES):
        await _get(unused_tcp_port, "/?t=000000")
    assert "429" in (await _get(unused_tcp_port, f"/?t={CODE}")).splitlines()[0]
    assert "getUserMedia" in await _get(unused_tcp_port, "/", cookie=f"bon_s={SESSION}")
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}/ws?s={SESSION}"):
        await asyncio.sleep(0.05)
        assert src.connected
    await src.stop()


async def test_each_lockout_lasts_twice_as_long_as_the_last(unused_tcp_port):
    now = [1000.0]
    src = _src(unused_tcp_port, clock=lambda: now[0])
    await src.start()

    async def locked():
        return "429" in (await _get(unused_tcp_port, f"/?t={CODE}")).splitlines()[0]

    for _ in range(MAX_BAD_CODES):
        await _get(unused_tcp_port, "/?t=000000")
    assert await locked()
    now[0] += LOCKOUT_S + 1
    for _ in range(MAX_BAD_CODES):
        await _get(unused_tcp_port, "/?t=000000")
    assert await locked()
    now[0] += LOCKOUT_S + 1                   # the second lockout is 2 x LOCKOUT_S
    assert await locked()
    now[0] += LOCKOUT_S
    assert not await locked()
    await src.stop()
