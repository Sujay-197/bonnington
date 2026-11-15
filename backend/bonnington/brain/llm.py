"""Bonnington's brain: a streaming chat session against a local Ollama model."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import ollama

from .persona import build_system_prompt

KEEP_ALIVE = "30m"
MAX_HISTORY = 20


class BrainUnavailable(Exception):
    """Ollama is not reachable or the model is missing."""


class Brain:
    def __init__(self, model: str, client: Any | None = None, tools: list | None = None) -> None:
        self.model = model
        self.client = client if client is not None else ollama.AsyncClient()
        self.tools = list(tools or [])  # phase 2 registers calendar/task/project tools here
        self.history: list[dict[str, str]] = []

    def reset_session(self) -> None:
        self.history = []

    def _append(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        self.history = self.history[-MAX_HISTORY:]

    def _messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": build_system_prompt()}, *self.history]

    async def _call(self, **kw: Any) -> Any:
        try:
            return await self.client.chat(model=self.model, **kw)
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
        kw: dict[str, Any] = dict(messages=self._messages(), stream=True, think=False,
                                  keep_alive=KEEP_ALIVE)
        if self.tools:
            kw["tools"] = self.tools
        stream = await self._call(**kw)
        parts: list[str] = []
        try:
            async for chunk in stream:
                text = chunk["message"]["content"]
                if text:
                    parts.append(text)
                    yield text
        except (httpx.HTTPError, ConnectionError) as e:
            raise BrainUnavailable(f"Ollama stream failed: {e}") from e
        finally:
            if parts:
                self._append("assistant", "".join(parts))
