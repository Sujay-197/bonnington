"""The conversation loop: wake -> listen -> think -> speak -> follow-up window -> idle."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from .brain.chunker import SentenceChunker
from .brain.llm import BrainUnavailable
from .brain.mood import MoodParser
from .brain.persona import build_summons_note
from .config import Settings
from .events import (ClearSubtitlesEvent, MoodEvent, StateEvent, SubtitleLineEvent,
                     UserFinalEvent, UserPartialEvent)
from .store import GrudgeStore, SummonKind
from .tts import estimate_word_offsets
from .wake import normalise_names

log = logging.getLogger(__name__)

State = Literal["idle", "listening", "thinking", "speaking", "followup"]
OFFLINE_TEXT = "My brain is offline. Start Ollama."
HM_AFTER_S = 3.0
PREROLL_FRAMES = 6  # 0.5 s kept from before speech is detected in a follow-up
MAX_BUFFER_FRAMES = 25  # last 2 s of audio kept while models load (replay blocks the loop ~0.5 s)


_FAREWELLS = ("bye", "bye bye", "goodbye", "good night", "goodnight", "see you", "see you later",
              "that's it for today", "that's it for now", "that's it for tonight", "that's all for today",
              "that's all for now", "that's all for tonight", "that's all", "that's it", "you can go",
              "you can go now", "go to sleep", "we're done", "we're done here", "go away", "be gone",
              "stop listening", "dismissed")
_LEAVING_NOTE = " [They are leaving. Give one short parting line and nothing else.]"


def is_farewell(text: str) -> bool:
    """True when the user is ending the conversation: a goodbye at the end of what they said, or on its own."""
    import re
    words = re.findall(r"[a-z']+", text.lower().replace("-", " ").replace("\u2019", "'"))
    if not words:
        return False
    joined = " " + " ".join(words) + " "
    for phrase in _FAREWELLS:
        if joined.endswith(" " + phrase + " "):
            return True
        if len(words) <= 5 and f" {phrase} " in joined and phrase not in ("that's it", "that's all"):
            return True
    return False


@dataclass
class Deps:
    source: Any
    wake: Any
    turn: Any
    stt: Any
    brain: Any
    tts: Any
    player: Any
    bridge: Any
    store: GrudgeStore
    settings: Settings
    now: Callable[[], datetime] = field(default=datetime.now)
    run_blocking: Callable[..., Awaitable[Any]] = field(default=asyncio.to_thread)
    play_file: Callable[[str], Awaitable[None]] | None = None


class Orchestrator:
    def __init__(self, deps: Deps, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.d = deps
        self._clock = clock
        self._sleep = sleep
        self.state: State = "idle"
        self.loading = False
        self.last_interaction = clock()
        self.on_wake_requested: Callable[[], None] | None = None
        self.on_session_end: Callable[[], None] | None = None
        self.on_user_text: Callable[[str], None] | None = None     # what the user just said
        self.on_reply_done: Callable[[str], None] | None = None    # everything he said in reply
        self._phase: str | None = None
        self._pending: SummonKind | None = None
        self._note: str | None = None
        self._buffer: list = []
        self._load_task: asyncio.Task | None = None
        self._reply_task: asyncio.Task | None = None
        self._window_start = 0.0
        self._heard_speech = False
        self._preroll: deque = deque(maxlen=PREROLL_FRAMES + 1)
        self._parser = MoodParser("neutral")
        self._line_id = 0
        self._leaving = False

    # --- public ---------------------------------------------------------------
    @property
    def active(self) -> bool:
        """True while a conversation is pending or under way (the mic must stay open)."""
        return self.state != "idle" or self._pending is not None or self.loading

    def trigger(self, kind: SummonKind) -> None:
        """Hotkey entry point. Safe to call from another thread."""
        self._pending = kind
        if self.on_wake_requested:
            self.on_wake_requested()

    async def run(self) -> None:
        try:
            async for frame in self.d.source.frames():
                self._on_frame(frame)
        finally:
            for t in (self._reply_task, self._load_task):
                if t is not None and not t.done():
                    t.cancel()

    def models_loaded(self) -> bool:
        return bool(self.d.stt.is_loaded and self.d.tts.is_loaded)

    async def ensure_awake(self) -> None:
        if self.models_loaded():
            return
        if self._load_task is None or self._load_task.done():
            self._start_loading()
        await self._load_task

    async def go_dormant(self) -> None:
        if self._reply_task is not None and not self._reply_task.done():
            self._interrupt()
        self._set_state("idle")
        await self.d.run_blocking(self.d.stt.unload)
        try:
            await self.d.brain.unload()
        except BrainUnavailable:
            pass
        await self.d.run_blocking(self.d.tts.unload)

    # --- frame handling ---------------------------------------------------------
    def _on_frame(self, frame) -> None:
        s = self.d.settings
        if self._pending is not None:
            kind, self._pending = self._pending, None
            if self.state != "listening":
                self._summon(kind)
                return
        if self.state == "idle":
            hit = self.d.wake.feed(frame)
            if hit:
                self._summon(hit)
        elif self.state == "followup":
            hit = self.d.wake.feed(frame)
            if hit:
                self._summon(hit)
                return
            self._preroll.append(frame)
            if self.d.turn.feed(frame) == "speech_start":
                self._heard_speech = True
                self._set_state("listening")
                self.d.stt.start_turn()
                for f in self._preroll:  # includes the audio from just before speech was detected
                    self._feed_stt(f)
                self._preroll.clear()
            elif self._clock() - self._window_start >= s.followup_seconds:
                self._end_session()
        elif self.state == "listening":
            if self.loading:
                self._buffer.append(frame)
                del self._buffer[:-MAX_BUFFER_FRAMES]
                return
            self._listen(frame)
        elif s.headphones_mode:  # thinking / speaking: only a wake word may barge in
            hit = self.d.wake.feed(frame)
            if hit:
                self._summon(hit)

    def _listen(self, frame) -> None:
        self._feed_stt(frame)
        ev = self.d.turn.feed(frame)
        if ev == "speech_start":
            self._heard_speech = True
        elif ev == "turn_end":
            self._finish_turn()
        elif not self._heard_speech and \
                self._clock() - self._window_start >= self.d.settings.followup_seconds:
            self._end_session()

    def _feed_stt(self, frame) -> None:
        partial = self.d.stt.feed(frame)
        if partial is not None:
            self.d.bridge.broadcast(UserPartialEvent(partial))

    def _finish_turn(self) -> None:
        text = normalise_names(self.d.stt.finish().strip())
        if not text:
            # Noise or a breath, not words: keep listening until the window runs out.
            log.info("heard nothing (noise); still listening")
            self._heard_speech = False
            self.d.turn.reset()
            self.d.stt.start_turn()
            return
        self.d.bridge.broadcast(UserFinalEvent(text))
        log.info("heard: %s", text)
        if self.on_user_text:
            self.on_user_text(text)
        msg = f"{self._note} {text}" if self._note else text
        self._note = None
        self._leaving = is_farewell(text)
        if self._leaving:
            msg += _LEAVING_NOTE
        self.last_interaction = self._clock()
        self._set_state("thinking")
        self._reply_task = asyncio.create_task(self._reply(msg))

    # --- summons / loading ----------------------------------------------------------
    def _summon(self, kind: SummonKind) -> None:
        was = self.state
        if was in ("thinking", "speaking"):
            self._interrupt()
        ctx = self.d.store.record_summons(kind, self.d.now())
        self.last_interaction = self._clock()
        if was == "idle":
            self.d.brain.reset_session()
            self._note = build_summons_note(ctx)
        if self.on_wake_requested:
            self.on_wake_requested()
        hint = getattr(self.d.source, "status_hint", lambda: None)()
        if hint:  # e.g. the phone mic page isn't open
            log.warning("mic problem: %s", hint)
            self._line_id += 1
            self.d.bridge.broadcast(SubtitleLineEvent(self._line_id, hint, 8000, []))
        self.d.turn.reset()
        self._window_start = self._clock()
        self._heard_speech = False
        if not self.models_loaded():
            self._start_loading()
            self._set_state("listening")
        else:
            self._set_state("listening")
            self.d.stt.start_turn()

    def _start_loading(self) -> None:
        self.loading = True
        self._buffer = []
        self._load_task = asyncio.create_task(self._load())

    async def _load(self) -> None:
        d = self.d
        loads = asyncio.gather(d.run_blocking(d.stt.load), d.brain.warm(),
                               d.run_blocking(d.tts.load), return_exceptions=True)
        sleeper = asyncio.ensure_future(self._sleep(HM_AFTER_S))
        try:
            await asyncio.wait({loads, sleeper}, return_when=asyncio.FIRST_COMPLETED)
            if not loads.done() and d.play_file is not None:
                await d.play_file(d.settings.hm_wav)
            for r in await loads:
                if isinstance(r, Exception) and not isinstance(r, BrainUnavailable):
                    log.error("model load failed: %r", r)
        finally:
            sleeper.cancel()
            self.loading = False
        if self.state == "listening":
            d.stt.start_turn()
            self._emit_phase()
            self._window_start = self._clock()
            buffered, self._buffer = self._buffer, []
            for f in buffered:
                if self.state != "listening":
                    break
                self._listen(f)

    # --- replying -------------------------------------------------------------------
    def _interrupt(self) -> None:
        if self._reply_task is not None and not self._reply_task.done():
            self._reply_task.cancel()
        self._reply_task = None
        if hasattr(self.d.tts, "cancel"):
            self.d.tts.cancel()
        self.d.player.stop()
        self.d.bridge.broadcast(ClearSubtitlesEvent())

    async def _reply(self, msg: str) -> None:
        d = self.d
        queue: asyncio.Queue = asyncio.Queue()
        producer = asyncio.create_task(self._produce(msg, queue))
        spoken: list[str] = []
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                self._set_state("speaking")
                log.info("says: %s", item.text)
                spoken.append(item.text)
                self._line_id += 1
                d.bridge.broadcast(SubtitleLineEvent(self._line_id, item.text, item.duration_ms,
                                                     list(item.word_offsets_ms)))
                if not await d.player.play(item):
                    return  # interrupted
            self.last_interaction = self._clock()
            if self.on_reply_done and spoken:
                self.on_reply_done(" ".join(spoken))
            if self._leaving:              # they said goodbye: stop listening
                self._end_session()
                return
            self._window_start = self._clock()
            d.turn.reset()
            self._preroll.clear()
            self._set_state("followup")
        except BrainUnavailable as e:
            log.warning("brain unavailable: %s", e)
            d.bridge.broadcast(MoodEvent("serious"))
            self._line_id += 1
            d.bridge.broadcast(SubtitleLineEvent(self._line_id, OFFLINE_TEXT, 4000,
                                                 estimate_word_offsets(OFFLINE_TEXT, 1500)))
            await self._sleep(4.0)
            d.bridge.broadcast(ClearSubtitlesEvent())
            self._end_session()
        finally:
            producer.cancel()

    async def _produce(self, msg: str, queue: asyncio.Queue) -> None:
        d = self.d
        parser = self._parser
        parser.reset()
        chunker = SentenceChunker()
        mood_sent = False

        async def say(sentences: list[str]) -> None:
            for s in sentences:
                await queue.put(await d.run_blocking(d.tts.synth, s))

        try:
            async for chunk in d.brain.stream_reply(msg):
                text = parser.feed(chunk)
                if parser.resolved and not mood_sent:
                    d.bridge.broadcast(MoodEvent(parser.mood))
                    mood_sent = True
                await say(chunker.feed(text))
            rest = parser.flush()
            if not mood_sent:
                d.bridge.broadcast(MoodEvent(parser.mood))
            await say(chunker.feed(rest) + chunker.flush())
            await queue.put(None)
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # hand errors to the consumer
            await queue.put(e)

    # --- state ----------------------------------------------------------------------
    def _end_session(self) -> None:
        self._note = None
        self._set_state("idle")
        if self.on_session_end:
            self.on_session_end()

    def _set_state(self, s: State) -> None:
        self.state = s
        self._emit_phase()

    def _emit_phase(self) -> None:
        if self.state == "listening" and self.loading:
            phase = "waking"
        elif self.state == "followup":
            phase = "listening"  # he is still listening for a reply; the UI shows the cue
        else:
            phase = self.state
        if phase != self._phase:
            log.info("state -> %s", phase)
            self._phase = phase
            self.d.bridge.broadcast(StateEvent(phase))  # type: ignore[arg-type]
