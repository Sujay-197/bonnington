"""User settings, persisted as JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def _default_wake_models() -> dict[str, str]:
    return {
        "britney": "data/wake/hey_britney.onnx",
        "bonnington": "data/wake/hey_bonnington.onnx",
    }


@dataclass
class Settings:
    hotkey: str = "<ctrl>+<alt>+b"
    headphones_mode: bool = False
    llm_model: str = "gemma4:12b"
    stt_model_dir: str = "data/models/stt"
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    voice_ref_wav: str = "data/voice/reference.wav"
    voice_ref_text: str = "data/voice/reference.txt"
    wake_models: dict[str, str] = field(default_factory=_default_wake_models)
    wake_threshold: float = 0.5
    followup_seconds: float = 8.0
    idle_unload_seconds: float = 600.0
    ws_port: int = 8765


def save_settings(s: Settings, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")


def load_settings(path: Path) -> Settings:
    path = Path(path)
    if not path.exists():
        s = Settings()
        save_settings(s, path)
        return s
    raw = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})
