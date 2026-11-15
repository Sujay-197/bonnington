"""Bonnington's brain: a streaming chat session against a local Ollama model."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import ollama

from .mood import MoodParser
from .persona import build_system_prompt

log = logging.getLogger(__name__)

KEEP_ALIVE = "30m"
MAX_HISTORY = 20
NUM_CTX = 4096  # short conversations; keeps the KV cache small so TTS + LLM fit in 16 GB


class BrainUnavailable(Exception):
    """Ollama is not reachable or the model is missing."""


MAX_TOOL_ROUNDS = 4


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Ollama returns dicts or objects depending on version; read either."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class Brain:
    def __init__(self, model: str, client: Any | None = None, tracker: Any | None = None) -> None:
        self.model = model
        self.client = client if client is not None else ollama.AsyncClient()
        self.tracker = tracker  # gives him the user's data and the tools to change it
        self.history: list[dict[str, str]] = []

    def reset_session(self) -> None:
        self.history = []

    def _append(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        self.history = self.history[-MAX_HISTORY:]

    def _system(self) -> dict[str, str]:
        text = build_system_prompt(tracker=self.tracker is not None)
        if self.tracker is not None:
            text += "\n\n" + self.tracker.snapshot()
        return {"role": "system", "content": text}

    def _messages(self) -> list[dict[str, str]]:
        return [self._system(), *self.history]

    async def _call(self, **kw: Any) -> Any:
        try:
            return await self.client.chat(model=self.model, options={"num_ctx": NUM_CTX}, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError) as e:
            raise BrainUnavailable(f"Ollama is not reachable: {e}") from e
        except ollama.ResponseError as e:
            raise BrainUnavailable(f"Ollama error for {self.model}: {e}") from e

    async def warm(self) -> None:
        await self._call(messages=[], keep_alive=KEEP_ALIVE)

    async def unload(self) -> None:
        await self._call(messages=[], keep_alive=0)

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        self._append("user", user_text)
        extra: list[dict[str, Any]] = []   # this turn's tool calls and results
        said: list[str] = []
        tools_ran = retried = False
        try:
            for round_no in range(MAX_TOOL_ROUNDS + 1):
                kw: dict[str, Any] = dict(messages=[self._system(), *self.history, *extra], stream=True,
                                          think=False, keep_alive=KEEP_ALIVE)
                if self.tracker is not None and round_no < MAX_TOOL_ROUNDS:
                    kw["tools"] = self.tracker.tool_specs()
                stream = await self._call(**kw)
                # After he has already spoken this turn, a new round's leading mood tag must not be read aloud.
                strip = MoodParser("neutral") if said else None
                # Guard: hold his first sentence until we know whether it claims a save that never happened.
                held: list[str] | None = [] if (self.tracker is not None and not tools_ran and not retried) else None
                judged = claim = False
                round_text: list[str] = []
                calls: list[tuple[str, dict]] = []

                async for chunk in stream:
                    msg = _field(chunk, "message") or {}
                    for tc in _field(msg, "tool_calls") or []:
                        fn = _field(tc, "function") or {}
                        calls.append((str(_field(fn, "name", "")), dict(_field(fn, "arguments") or {})))
                    text = _field(msg, "content") or ""
                    if not text:
                        continue
                    round_text.append(text)
                    out = strip.feed(text) if strip else text
                    if not out:
                        continue
                    if held is None:
                        said.append(out)
                        yield out
                        continue
                    held.append(out)
                    if not judged and _first_sentence_done("".join(held)):
                        judged = True
                        claim = _claims_a_save("".join(held))
                        if not claim:           # an ordinary reply: let it flow
                            for h in held:
                                said.append(h)
                                yield h
                            held = None
                rest = strip.flush() if strip else ""
                if rest:
                    if held is None:
                        said.append(rest)
                        yield rest
                    else:
                        held.append(rest)
                if held is not None:
                    if not judged:
                        claim = _claims_a_save("".join(held))
                    if claim and not calls:
                        log.warning("claimed a save without a tool call; retrying: %s", "".join(held)[:120])
                        retried = True
                        extra.append({"role": "assistant", "content": "".join(round_text)})
                        extra.append({"role": "user", "content": _NUDGE})
                        continue
                    for h in held:
                        said.append(h)
                        yield h
                if not calls:
                    break
                extra.append({"role": "assistant", "content": "".join(round_text),
                              "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in calls]})
                for name, args in calls:
                    result = self.tracker.call(name, args) if self.tracker is not None else "ERROR: no tools"
                    log.info("tool %s(%s) -> %s", name, args, result)
                    extra.append({"role": "tool", "tool_name": name, "content": result})
                tools_ran = True
        except (httpx.HTTPError, ConnectionError) as e:
            raise BrainUnavailable(f"Ollama stream failed: {e}") from e
        finally:
            if said:
                self._append("assistant", "".join(said))


_CLAIM = re.compile(r"\b(noted|recorded|saved|filed|logged|added|marked|undone|removed|deleted|placed|"
                    r"updated|scheduled|ticked|crossed)\b", re.IGNORECASE)
_NUDGE = ("[system check] You said you recorded or changed something, but you called no tool. "
          "Nothing was saved. If the user asked for a change, call the right tool now and then confirm it; "
          "otherwise answer without claiming to have saved anything.")


def _spoken(text: str) -> str:
    return re.sub(r"^\s*<mood:[^>]*>", "", text)


def _first_sentence_done(text: str) -> bool:
    body = _spoken(text)
    return bool(re.search(r"[.!?\u2026](\s|$)", body)) or len(body) > 200


def _claims_a_save(text: str) -> bool:
    body = _spoken(text)
    first = re.split(r"(?<=[.!?\u2026])\s", body, maxsplit=1)[0]
    return bool(_CLAIM.search(first))
