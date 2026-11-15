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
            options = {"num_ctx": NUM_CTX, **kw.pop("options", {})}
            return await self.client.chat(model=self.model, options=options, **kw)
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
                history = self.history
                if retried and not tools_ran:
                    history = [*self.history[:-1], {"role": "user", "content": user_text + _FORCE}]
                kw: dict[str, Any] = dict(messages=[self._system(), *history, *extra], stream=True,
                                          think=False, keep_alive=KEEP_ALIVE)
                if self.tracker is not None and round_no < MAX_TOOL_ROUNDS:
                    kw["tools"] = self.tracker.tool_specs()
                if retried:
                    kw["options"] = {"temperature": 0}     # the redo should be literal, not creative
                stream = await self._call(**kw)
                # After he has already spoken this turn, a new round's leading mood tag must not be read aloud.
                strip = MoodParser("neutral") if said else None
                # Guard: until a tool has run this turn, release his words a sentence at a time and hold
                # back everything from the first sentence that claims a save.
                guard = self.tracker is not None and not tools_ran
                pending = ""              # text not yet split into complete sentences
                held: list[str] = []      # from the first claiming sentence onwards
                round_text: list[str] = []
                calls: list[tuple[str, dict]] = []
                round_started = False

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
                    if out and tools_ran and not round_started:
                        out = re.sub(r"^\s*</\s*", "", out)
                    if not out:
                        continue
                    round_started = True
                    if not guard:
                        said.append(out)
                        yield out
                        continue
                    pending += out
                    sentences, pending = _complete_sentences(pending)
                    for sentence in sentences:
                        if held or _claims_a_save(sentence):
                            held.append(sentence)
                        else:
                            said.append(sentence)
                            yield sentence
                tail = pending + (strip.flush() if strip else "")
                if tail:
                    if guard and (held or _claims_a_save(tail)):
                        held.append(tail)
                    else:
                        said.append(tail)
                        yield tail
                if held and not calls:
                    log.warning("claimed a save without a tool call: %s", "".join(held)[:120])
                    if retried:            # still no tool call: say so, never let the claim stand
                        line = _FAILED if said else "<mood:serious>" + _FAILED
                        said.append(line)
                        yield line
                        break
                    retried = True
                    continue
                if not calls:
                    for h in held:
                        said.append(h)
                        yield h
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


_FAILED = "I did not manage to save that. Tell me again, plainly."
_SENTENCE = re.compile(r".*?[.!?\u2026]+[\"')\]]*\s+", re.DOTALL)


def _complete_sentences(text: str) -> tuple[list[str], str]:
    """Split off the sentences that are certainly finished (followed by whitespace); return them and the rest."""
    out = []
    pos = 0
    for m in _SENTENCE.finditer(text):
        out.append(m.group(0))
        pos = m.end()
    return out, text[pos:]


_VERBS = r"(noted|recorded|saved|filed|logged|added|marked|undone|removed|deleted|placed|put|updated|ticked|crossed|wiped)"
_CLAIM = re.compile(
    r"\bI(?:'ve| have| just|'ll| will| shall)?\s+(?:\w+\s+){0,2}" + _VERBS + r"\b"
    r"|\b(?:is|are|has been|have been|been)\s+(?:now\s+|duly\s+)?" + _VERBS + r"\b", re.IGNORECASE)
_FORCE = ("\n[Record or change this with the matching tool now. "
          "Do not answer in words until the tool has run.]")


def _spoken(text: str) -> str:
    return re.sub(r"^\s*<mood:[^>]*>", "", text)


def _claims_a_save(text: str) -> bool:
    return bool(_CLAIM.search(_spoken(text)))
