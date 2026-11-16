"""Split streamed text into sentences so TTS can start before the reply is complete."""

from __future__ import annotations

_ENDERS = ".!?…"
_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "e.g.", "i.e.", "vs.", "st.", "jr.", "sr."}


class SentenceChunker:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, text: str) -> list[str]:
        self._buf += text
        out: list[str] = []
        start = 0
        i = 0
        buf = self._buf
        while i < len(buf):
            ch = buf[i]
            cut = None
            if ch == "\n":
                cut = i
            elif ch in _ENDERS and i + 1 < len(buf) and buf[i + 1].isspace():
                if not (ch == "." and self._is_abbreviation(buf, start, i)):
                    cut = i + 1
            if cut is not None:
                sentence = buf[start:cut].strip()
                if sentence:
                    out.append(sentence)
                start = i + 1
            i += 1
        self._buf = buf[start:]
        return out

    def flush(self) -> list[str]:
        rest = self._buf.strip()
        self._buf = ""
        return [rest] if rest else []

    @staticmethod
    def _is_abbreviation(buf: str, start: int, dot: int) -> bool:
        word_start = max(buf.rfind(" ", start, dot), buf.rfind("\n", start, dot)) + 1
        return buf[max(word_start, start):dot + 1].lower() in _ABBREVIATIONS
