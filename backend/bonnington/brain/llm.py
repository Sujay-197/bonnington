"""Bonnington's brain: a streaming chat session against a local Ollama model."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import ollama

from ..vault.tools import CHANGE_TOOLS
from .mood import MoodParser
from .persona import build_system_prompt

log = logging.getLogger(__name__)

KEEP_ALIVE = "30m"
MAX_HISTORY = 20
NUM_CTX = 4096  # short conversations; keeps the KV cache small so TTS + LLM fit in 16 GB


class BrainUnavailable(Exception):
    """Ollama is not reachable or the model is missing."""


MAX_TOOL_ROUNDS = 4
MAX_REPLY_TOKENS = 400


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
        self._trim()

    def _trim(self) -> None:
        """Keep the last MAX_HISTORY messages, never starting mid-exchange (a tool result without its call)."""
        h = self.history[-MAX_HISTORY:]
        while h and h[0]["role"] != "user" and len(h) < len(self.history):
            h = h[1:]
        self.history = h

    def _system(self) -> dict[str, str]:
        text = build_system_prompt(tracker=self.tracker is not None)
        if self.tracker is not None:
            text += "\n\n" + self.tracker.snapshot()
        return {"role": "system", "content": text}

    def _made_change(self, name: str, result: str) -> bool:
        check = getattr(self.tracker, "made_change", None)
        if check is not None:
            return bool(check(name, result))
        return name in CHANGE_TOOLS and not result.startswith("ERROR")

    def _messages(self) -> list[dict[str, str]]:
        return [self._system(), *self.history]

    async def _call(self, **kw: Any) -> Any:
        try:
            options = {"num_ctx": NUM_CTX, "num_predict": MAX_REPLY_TOKENS, **kw.pop("options", {})}
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
        tools_ran = retried = empty_retried = False
        changed = False      # a tool call this turn really changed something; until then every claim is held
        hinted = self.tracker is not None and looks_like_a_report(user_text)
        change = wants_change(user_text)
        last_result = ""
        try:
            for round_no in range(MAX_TOOL_ROUNDS + 1):
                history = self.history
                if retried and not tools_ran:
                    history = [*self.history[:-1],
                               {"role": "user", "content": user_text + (_FORCE if change else _GENTLE)}]
                elif hinted and not tools_ran:
                    history = [*self.history[:-1], {"role": "user", "content": user_text + _HINT}]
                nudge = [{"role": "user", "content": _NOT_SAVED}] if retried and tools_ran else []
                kw: dict[str, Any] = dict(messages=[self._system(), *history, *extra, *nudge], stream=True,
                                          think=False, keep_alive=KEEP_ALIVE)
                if self.tracker is not None and round_no < MAX_TOOL_ROUNDS:
                    kw["tools"] = self.tracker.tool_specs()
                    if retried and not change:
                        # Small talk (or a question) that produced a false "I've noted it": the redo may
                        # look things up, but must not change anything nobody asked to change.
                        kw["tools"] = [t for t in kw["tools"] if t["function"]["name"] not in CHANGE_TOOLS]
                stream = await self._call(**kw)
                # After he has already spoken this turn, a new round's leading mood tag must not be read aloud.
                strip = MoodParser("neutral") if said else None
                # Guard: until a tool has run this turn, release his words a sentence at a time and hold
                # back everything from the first sentence that claims a save.
                guard = self.tracker is not None and not changed
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
                    out = re.sub(r"</\s*$", "", out)
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
                if not calls and not round_started and not held and not said and not tools_ran and not retried:
                    if empty_retried:      # he came back with nothing twice: say something rather than go silent
                        said.append(_EMPTY)
                        yield _EMPTY
                        break
                    log.warning("empty reply; asking again")
                    empty_retried = True
                    continue
                silent_redo = retried and not changed and not calls and not round_started
                if (held or silent_redo) and not calls:
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
                    last_result = result
                    changed = changed or self._made_change(name, result)
                tools_ran = True
            if tools_ran and not said and last_result and not last_result.startswith("ERROR"):
                line = "<mood:neutral>" + last_result.splitlines()[0]   # he saved but said nothing: read it back plainly
                said.append(line)
                yield line
        except (httpx.HTTPError, ConnectionError) as e:
            raise BrainUnavailable(f"Ollama stream failed: {e}") from e
        except ollama.ResponseError as e:   # raised mid-stream, e.g. "model runner has unexpectedly stopped"
            raise BrainUnavailable(f"Ollama error for {self.model}: {e}") from e
        finally:
            # Tool calls and results stay in his memory: otherwise past turns look as if things
            # were saved just by saying so, and he imitates that.
            self.history.extend(extra)
            if said:
                self._append("assistant", "".join(said))
            self._trim()


_FAILED = "I did not manage to save that. Tell me again, plainly."
_EMPTY = "<mood:neutral>Say that again."
_HINT = ("\n[This may be something to record. Record it now with the matching tool, using what was said, "
         "if so; ask for missing details afterwards.]")

_QUESTION = re.compile(r"^\s*(what|what's|when|when's|which|who|how|where|why|do|does|did|is|are|am|can|could|"
                       r"should|will|would|have i|tell me|show me|list|explain)\b", re.IGNORECASE)
_THING = re.compile(r"\b(exams?|tests?|quiz|quizzes|midterms?|viva|assignments?|lab report|submission|deadline|"
                    r"presentation|review)\b", re.IGNORECASE)
_DATED = re.compile(r"\b(today|tonight|tomorrow|day after|next|this|due|by|mon|tues?|wed(nes)?|thur?s?|fri|"
                    r"sat(ur)?|sun)(day)?\b|\b\d{1,2}(st|nd|rd|th)\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|"
                    r"nov|dec)[a-z]*\b", re.IGNORECASE)
_SCORED = re.compile(r"\b(scored|score of|marks|out of)\b|\bgot \d+|\d+\s*/\s*\d+", re.IGNORECASE)
_ASKED = re.compile(r"\b(remind me|add (this|that|a|an|it)\b|note (this|that|it)|put (this|that|it) (in|on)|"
                    r"to my (schedule|calendar|tasks|list))", re.IGNORECASE)


def looks_like_a_report(text: str) -> bool:
    """True when the user seems to be telling him something to record (not asking about what is recorded)."""
    if "?" in text or _QUESTION.search(text):
        return False
    return bool((_THING.search(text) and _DATED.search(text)) or _SCORED.search(text) or _ASKED.search(text))
_SENTENCE = re.compile(r".*?[.!?\u2026]+[\"')\]]*\s+", re.DOTALL)


def _complete_sentences(text: str) -> tuple[list[str], str]:
    """Split off the sentences that are certainly finished (followed by whitespace); return them and the rest."""
    out = []
    pos = 0
    for m in _SENTENCE.finditer(text):
        out.append(m.group(0))
        pos = m.end()
    return out, text[pos:]


_DONE = (r"(noted|recorded|saved|filed|logged|added|marked|undone|removed|deleted|placed|put|updated|ticked|"
         r"crossed|wiped|etched|scrubbed|shelved|struck|jotted|pencill?ed|registered|entered|tucked|scheduled)")
_DO = (r"(note|record|save|file|log|add|mark|undo|remove|delete|place|put|update|tick|cross|wipe|shelve|"
       r"strike|jot|pencil|register|enter|schedule)")
_PASSIVE = r"(noted|recorded|saved|filed|logged|added|marked|removed|deleted|updated)"
_CLAIM = re.compile(
    r"\bI(?:'ve| have| just)?\s+(?:\w+\s+){0,2}" + _DONE + r"\b"                       # I've noted / I have duly filed
    r"|\bI(?:'ll| will| shall)\s+(?:\w+\s+){0,2}(?:" + _DO + r"|have\s+\w+\s+" + _DONE + r")\b"  # I'll mark / I shall have it filed
    r"|\b(?:is|are)\s+(?:now\s+|duly\s+|firmly\s+|officially\s+){0,2}" + _PASSIVE + r"\b"   # is now noted
    r"|(?<!not )\b(?:has|have) been\s+(?:\w+ly\s+)?" + _PASSIVE + r"\b",                   # has been recorded
    re.IGNORECASE)
_GENTLE = ("\n[Nothing was changed: no tool was called. Simply answer, without saying anything was saved, "
           "added, marked or removed.]")
_NOT_SAVED = ("[Nothing was saved this turn: the tool reported an error or only looked things up. "
              "Do not say anything was saved. If something was asked to be recorded, call the right tool with "
              "what is missing filled in, or ask the user for it.]")
_ASKING = re.compile(r"^\s*(what|what's|whats|when|when's|which|who|how|where|why|do|does|did|is|are|am|was|were|"
                     r"have i|has|tell me|show me|list|explain)\b", re.IGNORECASE)
_CHANGE = re.compile(r"\b(remove|delete|undo|cancel|scrap|drop|mark|tick|cross off|done|finished|completed|"
                     r"submitted|on hold|resume|wrong|not a task|change|move|postpone|reschedule)\b", re.IGNORECASE)


def wants_change(text: str) -> bool:
    """True when the user's words ask for something to be recorded or changed.

    A question about what is recorded ("did I mark it done?") is not a request; a polite request
    ("can you mark it done?") is.
    """
    if _ASKING.search(text):
        return False
    return looks_like_a_report(text) or bool(_CHANGE.search(text))


_FORCE = ("\n[Record or change this with the matching tool now. "
          "Do not answer in words until the tool has run.]")


def _spoken(text: str) -> str:
    return re.sub(r"^\s*<mood:[^>]*>", "", text)


def _claims_a_save(text: str) -> bool:
    return bool(_CLAIM.search(_spoken(text)))
