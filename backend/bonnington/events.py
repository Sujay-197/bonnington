"""Events pushed from the backend to the UI over the WebSocket bridge."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import ClassVar, Literal

Mood = Literal["neutral", "amused", "annoyed", "smug", "serious", "disappointed"]
MOODS: tuple[str, ...] = ("neutral", "amused", "annoyed", "smug", "serious", "disappointed")
Phase = Literal["idle", "listening", "thinking", "speaking", "waking"]


class _Event:
    type: ClassVar[str]

    def to_json(self) -> str:
        return json.dumps({"type": self.type, **asdict(self)})


@dataclass(frozen=True)
class StateEvent(_Event):
    type: ClassVar[str] = "state"
    value: Phase


@dataclass(frozen=True)
class MoodEvent(_Event):
    type: ClassVar[str] = "mood"
    value: Mood


@dataclass(frozen=True)
class UserPartialEvent(_Event):
    type: ClassVar[str] = "user_partial"
    text: str


@dataclass(frozen=True)
class UserFinalEvent(_Event):
    type: ClassVar[str] = "user_final"
    text: str


@dataclass(frozen=True)
class SubtitleLineEvent(_Event):
    type: ClassVar[str] = "subtitle_line"
    id: int
    text: str
    duration_ms: int
    word_offsets_ms: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ClearSubtitlesEvent(_Event):
    type: ClassVar[str] = "clear_subtitles"


@dataclass(frozen=True)
class MemoryEvent(_Event):
    """He changed something in the vault; the UI shows a brief "memory updated" note."""

    type: ClassVar[str] = "memory"
    text: str


@dataclass(frozen=True)
class AmplitudeEvent(_Event):
    type: ClassVar[str] = "amplitude"
    value: float

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "value": round(float(self.value), 3)})


UIEvent = (StateEvent | MoodEvent | UserPartialEvent | UserFinalEvent | SubtitleLineEvent
           | ClearSubtitlesEvent | AmplitudeEvent | MemoryEvent)
