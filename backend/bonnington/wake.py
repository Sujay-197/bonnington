"""Wake phrases ("Hey Britney", "Hey Bonnington") via sherpa-onnx's open-vocabulary keyword spotter on the CPU."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

import numpy as np

WakeName = Literal["britney", "bonnington"]
FRAME_S = 0.08


def keyword_line(tokens: list[str], label: str, boost: float, threshold: float) -> str:
    return f"{' '.join(tokens)} :{boost} #{threshold} @{label}"


class _SherpaSpotter:
    def __init__(self, phrases: dict[str, str], model_dir: str, boost: float, threshold: float) -> None:
        import sentencepiece as spm
        import sherpa_onnx

        d = Path(model_dir)
        sp = spm.SentencePieceProcessor(model_file=str(d / "bpe.model"))
        lines = [keyword_line(sp.encode(p.upper(), out_type=str), name, boost, threshold)
                 for name, p in phrases.items()]
        kw_file = Path(tempfile.gettempdir()) / "bonnington_keywords.txt"
        kw_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def pick(stem: str) -> str:
            return str(next(d.glob(f"{stem}-*.int8.onnx")))

        self._kws = sherpa_onnx.KeywordSpotter(
            tokens=str(d / "tokens.txt"), encoder=pick("encoder"), decoder=pick("decoder"),
            joiner=pick("joiner"), keywords_file=str(kw_file), num_threads=1)
        self._stream = self._kws.create_stream()

    def feed(self, frame: np.ndarray) -> str:
        self._stream.accept_waveform(16000, frame.astype(np.float32) / 32768.0)
        hit = ""
        while self._kws.is_ready(self._stream):
            self._kws.decode_stream(self._stream)
            r = self._kws.get_result(self._stream)
            if r:
                hit = r
                self._kws.reset_stream(self._stream)
        return hit

    def reset(self) -> None:
        self._stream = self._kws.create_stream()


class KeywordWake:
    def __init__(self, phrases: dict[str, str], model_dir: str = "", *, boost: float = 1.5,
                 threshold: float = 0.25, cooldown_s: float = 2.0, spotter=None) -> None:
        self._names = set(phrases)
        self._cooldown_frames = int(round(cooldown_s / FRAME_S))
        self._quiet = 0
        self._spotter = spotter or _SherpaSpotter(phrases, model_dir, boost, threshold)

    def reset(self) -> None:
        self._quiet = 0
        self._spotter.reset()

    def feed(self, frame: np.ndarray) -> WakeName | None:
        hit = self._spotter.feed(frame)
        if self._quiet > 0:
            self._quiet -= 1
            return None
        if hit not in self._names:
            return None
        self._quiet = self._cooldown_frames - 1
        return hit  # type: ignore[return-value]
