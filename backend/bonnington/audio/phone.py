"""Phone as microphone: the phone opens a page served here and streams its mic over your Wi-Fi.

Bluetooth earbuds stay in music mode (full quality) because their own mic is never opened.
Audio only travels phone -> this PC on the local network. A 6-digit code pairs the phone once; after
that only a long session secret (kept in a cookie) opens the audio socket, so guessing the code is slow
and never enough to listen in or speak for the user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import socket
import ssl
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Response

log = logging.getLogger(__name__)

FRAME = 1280  # 80 ms at 16 kHz
FRAME_S = 0.08
_OPENSSL_FALLBACKS = (r"C:\Program Files\Git\mingw64\bin\openssl.exe", r"C:\Program Files\Git\usr\bin\openssl.exe")


def lan_ip() -> str:
    """This PC's address on the local network. No packet is sent: connecting a UDP socket only picks a route."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def authorised(path: str, token: str) -> bool:
    given = parse_qs(urlsplit(path).query).get("t", [""])[0]
    return bool(token) and given == token


SESSION_COOKIE = "bon_s"


def _given_session(request) -> str:
    """The session secret a request carries: in the link (?s=) or in the cookie set at pairing."""
    given = parse_qs(urlsplit(request.path).query).get("s", [""])[0]
    if given:
        return given
    for part in request.headers.get("Cookie", "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == SESSION_COOKIE:
            return value
    return ""


def secrets_equal(given: str, expected: str) -> bool:
    import hmac
    return bool(given) and bool(expected) and hmac.compare_digest(given, expected)


def ensure_cert(directory: Path, ip: str) -> tuple[Path, Path]:
    """A self-signed certificate so the phone's browser will allow microphone access (it requires HTTPS)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cert, key = directory / "cert.pem", directory / "key.pem"
    if cert.exists() and key.exists():
        return cert, key
    openssl = shutil.which("openssl") or next((p for p in _OPENSSL_FALLBACKS if Path(p).exists()), None)
    if openssl is None:
        raise RuntimeError("openssl not found (it ships with Git for Windows); cannot create the phone-mic certificate")
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
         "-keyout", str(key), "-out", str(cert), "-subj", "/CN=Bonnington phone mic",
         "-addext", f"subjectAltName=IP:{ip},IP:127.0.0.1"],
        check=True, capture_output=True)
    return cert, key


def page_html(token: str) -> str:
    return _PAGE.replace("__TOKEN__", token)


def code_form_html(wrong: bool = False) -> str:
    note = "That code didn't match. Try again." if wrong else "Enter the 6-digit code shown on your PC."
    return _CODE_FORM.replace("__NOTE__", note)


MAX_BAD_CODES = 8
LOCKOUT_S = 60.0           # the first lockout; each one after it lasts twice as long as the last
MAX_LOCKOUT_S = 3600.0     # at most 8 guesses an hour once someone keeps trying

_CODE_FORM = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bonnington mic</title>
<style>
  html,body{margin:0;height:100%;background:#000;color:#ddd;font-family:Georgia,serif;
    display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
  input{font:inherit;font-size:32px;letter-spacing:8px;text-align:center;width:220px;padding:12px;
    border-radius:12px;border:1px solid #777;background:#111;color:#fff}
  button{font:inherit;font-size:20px;margin-top:20px;padding:12px 28px;border-radius:999px;
    border:1px solid #777;background:#111;color:#fff}
  p{color:#888;font-size:15px;padding:0 24px}
</style></head><body>
<p>__NOTE__</p>
<form method="get" action="/">
  <input name="t" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autofocus aria-label="6-digit code">
  <br><button type="submit">Connect</button>
</form>
</body></html>
"""


class PhoneMicSource:
    """The 6-digit `token` only pairs a phone: the page it unlocks carries `session`, a long secret,
    and only that opens the audio socket. A paired phone keeps it in a cookie, so it is never locked out."""

    def __init__(self, port: int, token: str, host: str = "0.0.0.0",
                 ssl_context: ssl.SSLContext | None = None, lan_ip: str | None = None,
                 session: str | None = None, clock=None) -> None:
        import secrets
        self.port, self.token, self.host, self.ssl_context = port, token, host, ssl_context
        self.session = session or secrets.token_urlsafe(32)
        self._clock = clock or time.monotonic
        self._ip = lan_ip
        self._locked_until = 0.0
        self._lockouts = 0
        self._server = None
        self._phone: ServerConnection | None = None
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._pending = np.zeros(0, np.int16)
        self._want_open = asyncio.Event()
        self._bad: list[float] = []  # times of recent wrong codes
        self.on_connection_change = None   # called when the phone connects or drops
        self.is_open = False

    # --- lifecycle --------------------------------------------------------------
    @property
    def url(self) -> str:
        return f"https://{self._ip or lan_ip()}:{self.port}"

    @property
    def connected(self) -> bool:
        return self._phone is not None

    def connect_hint(self) -> dict[str, str] | None:
        """What to show on the dashboard while no phone is connected."""
        return None if self.connected else {"url": self.url, "code": self.token}

    def mic_status(self) -> str:
        return "PHONE · CONNECTED" if self.connected else "PHONE · NOT CONNECTED"

    def _notify(self) -> None:
        if self.on_connection_change is not None:
            try:
                self.on_connection_change()
            except Exception:
                log.exception("connection-change listener failed")

    def status_hint(self) -> str | None:
        if self.connected:
            return None
        return f"Phone mic not connected. Open {self.url} on your phone and enter code {self.token}."

    async def start(self) -> None:
        self._server = await serve(self._handle, self.host, self.port, ssl=self.ssl_context,
                                   process_request=self._process_request, max_size=2 ** 20)
        log.info("phone mic page: %s", self.url)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def open(self) -> None:
        self._want_open.set()
        self.is_open = True
        await self._tell_phone()

    async def close(self) -> None:
        self._want_open.clear()
        self.is_open = False
        self._drain()
        await self._tell_phone()

    def _drain(self) -> None:
        self._pending = np.zeros(0, np.int16)
        while not self._queue.empty():
            self._queue.get_nowait()

    async def _tell_phone(self) -> None:
        if self._phone is not None:
            try:
                await self._phone.send(json.dumps({"capture": self.is_open}))
            except Exception:
                pass

    # --- server -----------------------------------------------------------------
    def _process_request(self, connection: ServerConnection, request):
        paired = secrets_equal(_given_session(request), self.session)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return None if paired else connection.respond(403, "Forbidden\n")   # the bare code never opens audio
        if paired:
            return self._page(paired_now=False)
        now = self._clock()
        if now < self._locked_until:
            return connection.respond(429, "Too many wrong codes. Wait and try again.\n")
        tried = bool(parse_qs(urlsplit(request.path).query).get("t", [""])[0])
        if authorised(request.path, self.token):
            self._bad = []
            return self._page(paired_now=True)
        if tried:
            self._bad = [t for t in self._bad if now - t < LOCKOUT_S] + [now]
            log.warning("phone mic: wrong code tried")
            if len(self._bad) >= MAX_BAD_CODES:
                self._lockouts += 1
                self._locked_until = now + min(LOCKOUT_S * 2 ** (self._lockouts - 1), MAX_LOCKOUT_S)
                self._bad = []
                log.warning("phone mic: %d wrong codes; locked for %.0f s", MAX_BAD_CODES, self._locked_until - now)
        return self._html(code_form_html(wrong=tried))

    def _page(self, paired_now: bool) -> Response:
        extra = [("Set-Cookie", f"{SESSION_COOKIE}={self.session}; Max-Age=31536000; Path=/; Secure; HttpOnly; "
                                "SameSite=Strict")] if paired_now else []
        return self._html(page_html(self.session), extra)

    @staticmethod
    def _html(text: str, extra: list[tuple[str, str]] | None = None) -> Response:
        body = text.encode()
        return Response(200, "OK", Headers([("Content-Type", "text/html; charset=utf-8"),
                                            ("Content-Length", str(len(body))),
                                            ("Cache-Control", "no-store"), *(extra or [])]), body)

    async def _handle(self, ws: ServerConnection) -> None:
        if self._phone is not None:      # a newer connection replaces the old one
            try:
                await self._phone.close()
            except Exception:
                pass
        self._phone = ws
        self._drain()
        log.info("phone mic connected")
        self._notify()
        try:
            await self._tell_phone()
            async for msg in ws:
                if isinstance(msg, bytes) and self.is_open:
                    self._ingest(msg)
        except Exception:
            pass
        finally:
            if self._phone is ws:
                self._phone = None
                log.info("phone mic disconnected")
                self._notify()

    def _ingest(self, data: bytes) -> None:
        block = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2")
        self._pending = np.concatenate([self._pending, block]) if len(self._pending) else block
        while len(self._pending) >= FRAME:
            self._queue.put_nowait(self._pending[:FRAME].copy())
            self._pending = self._pending[FRAME:]

    # --- AudioSource ------------------------------------------------------------
    async def frames(self) -> AsyncIterator[np.ndarray]:
        silence = np.zeros(FRAME, np.int16)
        while True:
            await self._want_open.wait()
            try:
                # With no phone (or a paused page) hand out silence in real time, so the
                # conversation loop keeps moving and can time out normally.
                frame = await asyncio.wait_for(self._queue.get(), 0.3 if self.connected else FRAME_S)
            except asyncio.TimeoutError:
                frame = silence
            if self._want_open.is_set():
                yield frame


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bonnington mic</title>
<style>
  html,body{margin:0;height:100%;background:#000;color:#ddd;font-family:Georgia,serif;
    display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
  #dot{width:120px;height:120px;border-radius:50%;border:2px solid #555;margin-bottom:28px;transition:all .15s}
  #dot.live{border-color:#fff} #dot.talk{border-color:#fac775}
  button{font:inherit;font-size:20px;padding:14px 28px;border-radius:999px;border:1px solid #777;
    background:#111;color:#fff}
  #msg{margin-top:20px;font-size:15px;color:#888;padding:0 24px;min-height:3em}
</style></head><body>
<div id="dot"></div>
<button id="go">Start microphone</button>
<div id="msg">Keep this page open while you talk to Bonnington.</div>
<script>
const TOKEN = "__TOKEN__";
const dot = document.getElementById("dot"), msg = document.getElementById("msg"), go = document.getElementById("go");
let ws = null, capture = false, ctx = null;
const WORKLET = `
class Tap extends AudioWorkletProcessor {
  constructor(){ super(); this.buf = new Int16Array(1280); this.n = 0; }
  process(inputs){
    const ch = inputs[0][0]; if (!ch) return true;
    let peak = 0;
    for (let i = 0; i < ch.length; i++) {
      const v = Math.max(-1, Math.min(1, ch[i])); peak = Math.max(peak, Math.abs(v));
      this.buf[this.n++] = v * 32767;
      if (this.n === 1280) { this.port.postMessage({pcm: this.buf.slice().buffer, peak}, []); this.n = 0; }
    }
    return true;
  }
}
registerProcessor("tap", Tap);`;

function connect() {
  ws = new WebSocket(`wss://${location.host}/ws?s=${encodeURIComponent(TOKEN)}`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { msg.textContent = "Connected. Bonnington will listen when summoned."; };
  ws.onmessage = (e) => { try { capture = !!JSON.parse(e.data).capture; } catch {} dot.className = capture ? "live" : ""; };
  ws.onclose = () => { dot.className = ""; msg.textContent = "Disconnected. Reconnecting…"; setTimeout(connect, 1000); };
  ws.onerror = () => ws.close();
}

go.onclick = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: {
      channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    ctx = new AudioContext({ sampleRate: 16000 });
    await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" })));
    const node = new AudioWorkletNode(ctx, "tap");
    node.port.onmessage = (e) => {
      if (capture && ws && ws.readyState === 1) {
        ws.send(e.data.pcm);
        dot.className = e.data.peak > 0.05 ? "live talk" : "live";
      }
    };
    ctx.createMediaStreamSource(stream).connect(node);
    go.style.display = "none";
    if (navigator.wakeLock) { try { await navigator.wakeLock.request("screen"); } catch {} }
    document.addEventListener("visibilitychange", async () => {
      if (document.visibilityState === "visible") {
        if (ctx.state !== "running") await ctx.resume();
        if (navigator.wakeLock) { try { await navigator.wakeLock.request("screen"); } catch {} }
      }
    });
    connect();
  } catch (err) {
    msg.textContent = "Microphone blocked: " + err.message;
  }
};
</script></body></html>
"""
