"""Run the real wake detector over data/wake/{britney,bonnington,negative}.wav and report hits per clip."""
import time

import soundfile as sf

from bonnington.config import load_settings
from bonnington.wake import SttWake

s = load_settings("data/settings.json")
for sim in (0.6, 0.7, 0.8):
    row = []
    for name in ("britney", "bonnington", "negative"):
        audio = sf.read(f"data/wake/{name}.wav", dtype="int16")[0].reshape(-1)
        w = SttWake(s.wake_phrases, s, min_similarity=sim, cooldown_s=1.5)
        t = time.perf_counter()
        hits = [h for i in range(0, len(audio) - 1279, 1280) if (h := w.feed(audio[i:i + 1280]))]
        row.append(f"{name}: {hits.count(name) if name != 'negative' else len(hits)} ({time.perf_counter() - t:.1f}s)")
    print(f"similarity {sim}: " + " | ".join(row), flush=True)
