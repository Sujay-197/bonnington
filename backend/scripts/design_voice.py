"""One-off: generate candidate voices for Bonnington with Qwen3-TTS VoiceDesign.

Usage: uv run python scripts/design_voice.py --n 6 --out ../data/voice/candidates
"""
import argparse
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

LINE = ("Ah. Britney. You do realise that's not my name... and yet here I am, "
        "answering like a damned golden retriever. Go on, then. Disappoint me.")

BASE = ("A middle-aged American man with a low, unhurried baritone. Slightly breathy, articulate, "
        "amused, as if he knows something you don't. Long deliberate pauses, crisp consonants, "
        "dry and quietly menacing charm.")

VARIANTS = [
    "",
    " Slower pace, more gravel, very relaxed.",
    " Smoother and warmer, a velvet tone, faint smile in the voice.",
    " Deeper and darker, more weight in the chest, clipped delivery.",
    " Lighter and more playful, theatrical, savouring each word.",
    " Raspier, older, world-weary, heavy pauses before key words.",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--out", default="../data/voice/candidates")
    ap.add_argument("--model", default="../data/models/tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = Qwen3TTSModel.from_pretrained(args.model, device_map="cuda:0", dtype=torch.bfloat16)
    for i in range(args.n):
        desc = BASE + VARIANTS[i % len(VARIANTS)]
        wavs, sr = model.generate_voice_design(text=LINE, instruct=desc, language="English")
        sf.write(out / f"{i + 1:02d}.wav", wavs[0], sr)
        (out / f"{i + 1:02d}.txt").write_text(desc, encoding="utf-8")
        print(f"{i + 1:02d}.wav  {len(wavs[0]) / sr:.1f}s  {desc[-60:]}")


if __name__ == "__main__":
    main()
