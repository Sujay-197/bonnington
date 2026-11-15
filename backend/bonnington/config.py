"""User settings, persisted as JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def _default_wake_phrases() -> dict[str, str]:
    return {"britney": "HEY BRITNEY", "bonnington": "HEY BONNINGTON"}


@dataclass
class Settings:
    hotkey: str = "<ctrl>+<alt>+b"
    mic_source: str = "device"  # "device" = a PC input; "phone" = your phone over Wi-Fi
    phone_port: int = 8766
    phone_token: str = ""  # secret in the phone link; generated on first use
    mic_device: str | None = None  # substring of the input device name; None = Windows default
    headphones_mode: bool = False
    always_listening: bool = False  # False = hotkey first: mic closed while dormant
    llm_model: str = "gemma4:12b"
    stt_model_dir: str = "data/models/stt/sherpa-onnx-nemotron-speech-streaming-en-0.6b-160ms-int8-2026-04-25"
    stt_final_model_dir: str = "data/models/stt/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
    turn_silence_ms: int = 1000  # how long a pause ends your turn
    tts_model: str = "data/models/tts/Qwen3-TTS-12Hz-1.7B-Base"
    voice_ref_wav: str = "data/voice/reference.wav"
    voice_ref_text: str = "data/voice/reference.txt"
    hm_wav: str = "data/voice/hm.wav"
    wake_phrases: dict[str, str] = field(default_factory=_default_wake_phrases)
    wake_similarity: float = 0.6
    followup_seconds: float = 8.0
    idle_unload_seconds: float = 600.0
    ws_port: int = 8765
    keep_window_open: bool = True       # the dashboard stays up while he is dormant
    vault_dir: str = "data/vault"       # his notes on your exams, tasks, scores and projects
    claude_projects_dir: str = ""       # "" = ~/.claude/projects
    projects_root: str = ""             # "" = the folder that contains this project
    academic_folders: list[str] = field(default_factory=lambda: ["clg"])


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


def ensure_phone_token(s: Settings, path: Path) -> str:
    if not (len(s.phone_token) == 6 and s.phone_token.isdigit()):
        import secrets
        s.phone_token = f"{secrets.randbelow(10 ** 6):06d}"  # short enough to type on a phone
        save_settings(s, path)
    return s.phone_token
