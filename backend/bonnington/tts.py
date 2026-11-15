"""Text-to-speech in Bonnington's locked voice, plus subtitle word timing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Settings

_SPACE_WEIGHT = 0.3
_COMMA_PAUSE = 2.0
_SENTENCE_PAUSE = 4.0


@dataclass
class Utterance:
    pcm: np.ndarray
    sample_rate: int
    text: str
    word_offsets_ms: list[int] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return int(round(len(self.pcm) / self.sample_rate * 1000))


def estimate_word_offsets(text: str, duration_ms: int) -> list[int]:
    """Spread words over the audio by character length, with extra time after punctuation."""
    words = text.split()
    if not words:
        return []
    starts: list[float] = []
    pos = 0.0
    for w in words:
        starts.append(pos)
        pos += len(w) + _SPACE_WEIGHT
        if w[-1] in ",;:":
            pos += _COMMA_PAUSE
        elif w[-1] in ".!?…":
            pos += _SENTENCE_PAUSE
    return [int(s / pos * duration_ms) for s in starts]


class TTSEngine:
    """Qwen3-TTS Base model cloning the reference voice picked during voice design."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._prompt = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        from qwen_tts import Qwen3TTSModel

        self._model = Qwen3TTSModel.from_pretrained(
            self.settings.tts_model, device_map="cuda:0", dtype=torch.bfloat16)
        ref_text = Path(self.settings.voice_ref_text).read_text(encoding="utf-8").strip()
        self._prompt = self._model.create_voice_clone_prompt(
            ref_audio=self.settings.voice_ref_wav, ref_text=ref_text)

    def unload(self) -> None:
        if self._model is None:
            return
        import torch
        self._model = None
        self._prompt = None
        torch.cuda.empty_cache()

    def synth(self, sentence: str) -> Utterance:
        if self._model is None:
            raise RuntimeError("TTSEngine.synth called before load()")
        wavs, sr = self._model.generate_voice_clone(
            text=sentence, language="English", voice_clone_prompt=self._prompt)
        pcm = np.asarray(wavs[0], dtype=np.float32)
        u = Utterance(pcm, int(sr), sentence)
        u.word_offsets_ms = estimate_word_offsets(sentence, u.duration_ms)
        return u
