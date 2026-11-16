"""Lock the picked candidate as Bonnington's voice and render the warm-up 'hm'.

Usage: uv run python scripts/lock_voice.py 03
"""
import shutil
import sys
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design_voice import LINE  # noqa: E402

VOICE = Path("../data/voice")


def main() -> None:
    pick = sys.argv[1]
    shutil.copy(VOICE / "candidates" / f"{pick}.wav", VOICE / "reference.wav")
    (VOICE / "reference.txt").write_text(LINE, encoding="utf-8")
    model = Qwen3TTSModel.from_pretrained("../data/models/tts/Qwen3-TTS-12Hz-1.7B-Base",
                                          device_map="cuda:0", dtype=torch.bfloat16)
    prompt = model.create_voice_clone_prompt(ref_audio=str(VOICE / "reference.wav"), ref_text=LINE)
    wavs, sr = model.generate_voice_clone(text="Hmm.", language="English", voice_clone_prompt=prompt)
    hm = wavs[0][: int(sr * 1.0)]
    sf.write(VOICE / "hm.wav", hm, sr)
    wavs, sr = model.generate_voice_clone(text="Britney. Again. I'm keeping receipts.",
                                          language="English", voice_clone_prompt=prompt)
    sf.write(VOICE / "check.wav", wavs[0], sr)
    print(f"locked {pick}; hm.wav {len(hm) / sr:.2f}s; check.wav {len(wavs[0]) / sr:.1f}s")


if __name__ == "__main__":
    main()
