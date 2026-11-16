"""Record wake-word tuning clips into data/wake/: 20 s of each phrase (said 5 times) + 20 s of normal talk."""
import time
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from bonnington.config import load_settings

CLIPS = [
    ("britney", 'Say "Hey Britney" 5 times, pausing ~2 s between each'),
    ("bonnington", 'Say "Hey Bonnington" 5 times, pausing ~2 s between each'),
    ("negative", "Talk normally about anything (no wake words) - include words like 'pretty', 'Brittany Spears', 'bonfire'"),
]


def main() -> None:
    s = load_settings("data/settings.json")
    out = Path("data/wake")
    out.mkdir(parents=True, exist_ok=True)
    for name, instruction in CLIPS:
        print(f"\nNext: {instruction}")
        for n in (3, 2, 1):
            print(f"  {n}...", flush=True)
            time.sleep(1)
        print("  >>> GO (20 seconds)", flush=True)
        audio = sd.rec(int(20 * 16000), samplerate=16000, channels=1, dtype="int16", device=s.mic_device)
        sd.wait()
        sf.write(out / f"{name}.wav", audio, 16000)
        print(f"  saved {name}.wav")
    print("\ndone - tell Claude")


if __name__ == "__main__":
    main()
