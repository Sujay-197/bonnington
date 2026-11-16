"""Round 2: variants of candidate 06 with slightly more pace, plus 06 time-stretched at constant pitch."""
from pathlib import Path

import librosa
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from design_voice import BASE, LINE

OUT = Path("../data/voice/candidates")
DESC = (BASE.replace("Long deliberate pauses", "Measured pauses")
        + " Raspier, older, world-weary, but with a touch more pace: brief pauses before key words, "
          "never rushed, never dragging.")

model = Qwen3TTSModel.from_pretrained("../data/models/tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                                      device_map="cuda:0", dtype=torch.bfloat16)
for tag in ("06a", "06b", "06c"):
    wavs, sr = model.generate_voice_design(text=LINE, instruct=DESC, language="English")
    sf.write(OUT / f"{tag}.wav", wavs[0], sr)
    (OUT / f"{tag}.txt").write_text(DESC, encoding="utf-8")
    print(f"{tag}.wav {len(wavs[0]) / sr:.1f}s")

y, sr = librosa.load(OUT / "06.wav", sr=None)
fast = librosa.effects.time_stretch(y, rate=1.08)
sf.write(OUT / "06s.wav", fast, sr)
(OUT / "06s.txt").write_text("06 time-stretched x1.08, same pitch", encoding="utf-8")
print(f"06s.wav {len(fast) / sr:.1f}s (06 was {len(y) / sr:.1f}s)")
