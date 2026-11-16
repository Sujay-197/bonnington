"""Record 5 short benchmark clips of your voice into data/bench/ (16 kHz mono)."""
import sys
import time
from pathlib import Path

import sounddevice as sd
import soundfile as sf

SENTENCES = [
    "Hey Britney, what's left for this week?",
    "I have a database exam on Thursday at nine.",
    "Remind me to finish the medrag project tonight.",
    "Honestly, I'd rather play games than study right now.",
    "Bonnington, tell me something useful for once.",
]
DEVICE = sys.argv[1] if len(sys.argv) > 1 else None
OUT = Path(__file__).resolve().parents[2] / "data" / "bench"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(SENTENCES, 1):
        print(f"\n[{i}/5] Get ready to say:\n    {s}")
        for n in (3, 2, 1):
            print(f"  {n}...", flush=True)
            time.sleep(1)
        print("  >>> SPEAK NOW (5 seconds)", flush=True)
        audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="int16", device=DEVICE)
        sd.wait()
        sf.write(OUT / f"{i:02d}.wav", audio, 16000)
        (OUT / f"{i:02d}.txt").write_text(s, encoding="utf-8")
        print("  saved.")
    print(f"\nDone. Clips in {OUT}")


if __name__ == "__main__":
    main()
