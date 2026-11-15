"""Strip the leading <mood:NAME> tag from a streamed reply and remember the mood."""

from __future__ import annotations

from ..events import MOODS, Mood

_PREFIX = "<mood:"
_MAX_PENDING = 24


class MoodParser:
    def __init__(self, current: Mood) -> None:
        self.mood: Mood = current
        self.reset()

    def reset(self) -> None:
        self._buf = ""
        self._resolved = False

    def feed(self, chunk: str) -> str:
        if self._resolved:
            return chunk
        self._buf += chunk
        s = self._buf.lstrip()
        if not s:
            return ""
        if s.startswith(_PREFIX) and ">" in s:
            end = s.index(">")
            name = s[len(_PREFIX):end].strip().lower()
            if name in MOODS:
                self.mood = name  # type: ignore[assignment]
            self._resolved = True
            return s[end + 1:].lstrip()
        maybe_tag = _PREFIX.startswith(s) or s.startswith(_PREFIX)
        if maybe_tag and len(s) <= _MAX_PENDING:
            return ""
        return self.flush()

    def flush(self) -> str:
        out = "" if self._resolved else self._buf
        self._resolved = True
        self._buf = ""
        return out
