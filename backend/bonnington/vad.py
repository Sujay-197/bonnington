"""Turn detection: when did the user start talking, and when did they stop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import numpy as np

TurnEvent = Literal["speech_start", "turn_end"]
FRAME_MS = 80


class SileroVad:
    """Silero VAD via sherpa-onnx. Returns True when the frame contains speech."""

    def __init__(self, model_path: str = "data/models/vad/silero_vad.onnx") -> None:
        import sherpa_onnx
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = model_path
        cfg.silero_vad.min_silence_duration = 0.1
        cfg.silero_vad.window_size = 512
        cfg.sample_rate = 16000
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=10)

    def __call__(self, frame: np.ndarray) -> bool:
        self._vad.accept_waveform(frame.astype(np.float32) / 32768.0)
        speaking = self._vad.is_speech_detected()
        while not self._vad.empty():
            self._vad.pop()
        return speaking


class TurnDetector:
    def __init__(self, silence_ms: int = 1000, max_turn_s: float = 30.0,
                 vad: Callable[[np.ndarray], bool] | None = None) -> None:
        self.silence_ms = silence_ms
        self.max_turn_ms = max_turn_s * 1000
        self.vad = vad if vad is not None else SileroVad()
        self.reset()

    def reset(self) -> None:
        self._in_speech = False
        self._silence = 0
        self._elapsed = 0

    def feed(self, frame: np.ndarray) -> TurnEvent | None:
        speech = self.vad(frame)
        if not self._in_speech:
            if speech:
                self._in_speech, self._silence, self._elapsed = True, 0, 0
                return "speech_start"
            return None
        self._elapsed += FRAME_MS
        self._silence = 0 if speech else self._silence + FRAME_MS
        if self._silence >= self.silence_ms or self._elapsed >= self.max_turn_ms:
            self.reset()
            return "turn_end"
        return None
