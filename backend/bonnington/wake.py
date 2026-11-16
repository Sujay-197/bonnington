"""Wake phrases ("Hey Britney", "Hey Bonnington") spotted in the streaming Nemotron transcript.

The STT hears "Britney" as "Brittany" and "Bonnington" as "Mornington"/"Boydington", so the word after a
greeting is fuzzy-matched against each name. Requiring the greeting keeps "Brittany Spears" from waking him.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Literal

import numpy as np

WakeName = Literal["britney", "bonnington"]
FRAME_S = 0.08
GREETINGS = {"hey", "hi", "okay", "ok", "yo", "oi"}
MAX_WORDS = 30  # bound the running transcript


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def match_wake(text: str, phrases: dict[str, str], min_similarity: float = 0.7) -> WakeName | None:
    targets = {name: phrase.split()[-1].lower() for name, phrase in phrases.items()}
    words = _words(text)
    best: tuple[float, str] | None = None
    for greet, cand in zip(words, words[1:]):
        if greet not in GREETINGS:
            continue
        for name, target in targets.items():
            score = SequenceMatcher(None, cand, target).ratio()
            if score >= min_similarity and (best is None or score > best[0]):
                best = (score, name)
    return best[1] if best else None  # type: ignore[return-value]


class _NemotronStream:
    """A dedicated streaming recognizer for wake spotting (CPU, loaded on first use)."""

    def __init__(self, settings) -> None:
        from .stt import SherpaSTT
        self._stt = SherpaSTT(settings, num_threads=2)

    def feed(self, frame: np.ndarray) -> str | None:
        if not self._stt.is_loaded:
            self._stt.load()
            self._stt.start_turn()
        return self._stt.feed(frame)

    def reset(self) -> None:
        if self._stt.is_loaded:
            self._stt.start_turn()


class SttWake:
    def __init__(self, phrases: dict[str, str], settings=None, *, min_similarity: float = 0.7,
                 cooldown_s: float = 2.0, recognizer=None) -> None:
        self.phrases = phrases
        self.min_similarity = min_similarity
        self._cooldown_frames = int(round(cooldown_s / FRAME_S))
        self._quiet = 0
        self._rec = recognizer or _NemotronStream(settings)

    def reset(self) -> None:
        self._quiet = 0
        self._rec.reset()

    def feed(self, frame: np.ndarray) -> WakeName | None:
        text = self._rec.feed(frame)
        if self._quiet > 0:
            self._quiet -= 1
            return None
        if not text:
            return None
        hit = match_wake(text, self.phrases, self.min_similarity)
        if hit:
            self._rec.reset()
            self._quiet = self._cooldown_frames - 1
            return hit
        if len(_words(text)) > MAX_WORDS:
            self._rec.reset()
        return None


_NAMES = {"bonnington": "Bonnington", "britney": "Britney"}


def normalise_names(text: str, min_similarity: float = 0.75) -> str:
    """The recogniser mishears his names ("Mornington", "Brittany"); put the right spelling back."""
    def fix(m: re.Match) -> str:
        word = m.group(0)
        for target, proper in _NAMES.items():
            if SequenceMatcher(None, word.lower(), target).ratio() >= min_similarity:
                return proper
        return word
    return re.sub(r"[A-Za-z']{6,}", fix, text)
