"""Wake phrases: "Hey Britney" and "Hey Bonnington", via openWakeWord on the CPU."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np

WakeName = Literal["britney", "bonnington"]
FRAME_S = 0.08


class WakeDetector:
    def __init__(self, models: dict[str, str], threshold: float, cooldown_s: float = 2.0,
                 oww=None) -> None:
        self.threshold = threshold
        self._cooldown_frames = int(round(cooldown_s / FRAME_S))
        self._quiet = 0
        # openWakeWord reports scores keyed by model file stem; map back to our names.
        self._keys = {name: {name, Path(path).stem} for name, path in models.items()}
        if oww is None:
            from openwakeword.model import Model
            oww = Model(wakeword_models=list(models.values()), inference_framework="onnx")
        self._oww = oww

    def reset(self) -> None:
        self._quiet = 0
        self._oww.reset()

    def feed(self, frame: np.ndarray) -> WakeName | None:
        scores = self._oww.predict(frame)
        if self._quiet > 0:
            self._quiet -= 1
            return None
        best: tuple[float, str] | None = None
        for name, keys in self._keys.items():
            score = max((float(scores.get(k, 0.0)) for k in keys), default=0.0)
            if score >= self.threshold and (best is None or score > best[0]):
                best = (score, name)
        if best is None:
            return None
        self._quiet = self._cooldown_frames - 1
        return best[1]  # type: ignore[return-value]
