"""Speech-to-text via sherpa-onnx. Streaming models (Nemotron) give live partials; offline ones (Parakeet) decode at turn end."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from .config import Settings


class STTEngine(Protocol):
    is_loaded: bool

    def load(self) -> None: ...
    def unload(self) -> None: ...
    def start_turn(self) -> None: ...
    def feed(self, frame: np.ndarray) -> str | None: ...
    def finish(self) -> str: ...


def _pick(d: Path, stem: str) -> str:
    for name in (f"{stem}.int8.onnx", f"{stem}.onnx", f"{stem}.fp16.onnx"):
        if (d / name).exists():
            return str(d / name)
    raise FileNotFoundError(f"no {stem} model in {d}")


class SherpaSTT:
    def __init__(self, settings: Settings, num_threads: int = 4) -> None:
        self.dir = Path(settings.stt_model_dir)
        self.streaming = "parakeet" not in self.dir.name
        self.num_threads = num_threads
        self._rec = None
        self._stream = None
        self._audio: list[np.ndarray] = []
        self._last = ""

    @property
    def is_loaded(self) -> bool:
        return self._rec is not None

    def load(self) -> None:
        if self._rec is not None:
            return
        import sherpa_onnx
        d = self.dir
        kw = dict(tokens=str(d / "tokens.txt"), encoder=_pick(d, "encoder"),
                  decoder=_pick(d, "decoder"), joiner=_pick(d, "joiner"),
                  num_threads=self.num_threads, sample_rate=16000, feature_dim=80,
                  decoding_method="greedy_search")
        if self.streaming:
            self._rec = sherpa_onnx.OnlineRecognizer.from_transducer(**kw)
        else:
            self._rec = sherpa_onnx.OfflineRecognizer.from_transducer(model_type="nemo_transducer", **kw)

    def unload(self) -> None:
        self._rec = None
        self._stream = None

    def start_turn(self) -> None:
        self._audio = []
        self._last = ""
        self._stream = self._rec.create_stream() if self.streaming else None

    def feed(self, frame: np.ndarray) -> str | None:
        samples = frame.astype(np.float32) / 32768.0
        if not self.streaming:
            self._audio.append(samples)
            return None
        if self._stream is None:
            self.start_turn()
        self._stream.accept_waveform(16000, samples)
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        text = self._rec.get_result(self._stream).strip()
        if text and text != self._last:
            self._last = text
            return text
        return None

    def finish(self) -> str:
        if self.streaming:
            if self._stream is None:
                return ""
            self._stream.accept_waveform(16000, np.zeros(int(16000 * 0.8), np.float32))  # flush tail
            self._stream.input_finished()
            while self._rec.is_ready(self._stream):
                self._rec.decode_stream(self._stream)
            text = self._rec.get_result(self._stream).strip()
            self._stream = None
            return text
        if not self._audio:
            return ""
        s = self._rec.create_stream()
        s.accept_waveform(16000, np.concatenate(self._audio))
        self._rec.decode_stream(s)
        self._audio = []
        return s.result.text.strip()
