"""Measure STT, TTS and LLM latency plus total VRAM on this machine. Results go into docs/superpowers/benchmarks.md by hand."""
import asyncio
import difflib
import subprocess
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from bonnington.brain.llm import Brain
from bonnington.config import Settings
from bonnington.stt import SherpaSTT
from bonnington.tts import TTSEngine

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data" / "bench"
STT_DIRS = sorted(p for p in (ROOT / "data" / "models" / "stt").glob("sherpa-onnx-*") if p.is_dir())


def vram_mb() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    return int(out.strip().splitlines()[0])


def bench_stt(model_dir: Path) -> SherpaSTT:
    s = Settings()
    s.stt_model_dir = str(model_dir)
    stt = SherpaSTT(s)
    t0 = time.perf_counter()
    stt.load()
    print(f"\n== STT {model_dir.name} (load {time.perf_counter() - t0:.1f}s)")
    for wav in sorted(BENCH.glob("*.wav")):
        audio, _ = sf.read(wav, dtype="int16")
        ref = wav.with_suffix(".txt").read_text(encoding="utf-8")
        stt.start_turn()
        t_proc = 0.0
        for i in range(0, len(audio) - 1279, 1280):
            t = time.perf_counter()
            stt.feed(audio[i:i + 1280])
            t_proc += time.perf_counter() - t
        t = time.perf_counter()
        text = stt.finish()
        final_ms = (time.perf_counter() - t) * 1000
        sim = difflib.SequenceMatcher(None, text.lower(), ref.lower()).ratio()
        print(f"  {wav.name}: final {final_ms:.0f} ms, RTF {t_proc / (len(audio) / 16000):.3f}, "
              f"sim {sim:.2f} | {text}")
    return stt


def bench_tts(ref_wav: Path, ref_text: str) -> TTSEngine:
    s = Settings()
    s.voice_ref_wav, s.voice_ref_text = str(ref_wav), str(ref_wav.with_suffix(".reftxt"))
    Path(s.voice_ref_text).write_text(ref_text, encoding="utf-8")
    tts = TTSEngine(s)
    t0 = time.perf_counter()
    tts.load()
    print(f"\n== TTS (load {time.perf_counter() - t0:.1f}s)")
    tts.synth("Warm up.")
    for line in ["Britney. Again.",
                 "No exams this week, which means you have absolutely no excuse tonight.",
                 "Medrag has been gathering dust for forty one days, and frankly I am starting to "
                 "think you enjoy disappointing me more than you enjoy finishing anything at all."]:
        t = time.perf_counter()
        u = tts.synth(line)
        dt = time.perf_counter() - t
        print(f"  {len(line.split()):2d} words: synth {dt * 1000:.0f} ms for {u.duration_ms / 1000:.1f}s audio "
              f"(RTF {dt / (u.duration_ms / 1000):.2f})")
    return tts


async def bench_llm(model: str) -> Brain:
    b = Brain(model)
    await b.warm()
    times = []
    for _ in range(3):
        b.reset_session()
        t = time.perf_counter()
        async for _c in b.stream_reply("Hey. Say something short."):
            times.append(time.perf_counter() - t)
            break
    print(f"\n== LLM {model}: first token {min(times) * 1000:.0f}-{max(times) * 1000:.0f} ms (warm)")
    return b


def main() -> None:
    base = vram_mb()
    print(f"VRAM baseline {base} MB")
    for d in STT_DIRS:
        bench_stt(d)
    ref = ROOT / "data" / "voice" / "reference.wav"
    if not ref.exists():
        ref = ROOT / "data" / "voice" / "candidates" / "01.wav"
    from design_voice import LINE  # noqa: E402
    bench_tts(ref, LINE)
    print(f"VRAM after TTS: {vram_mb() - base} MB")
    asyncio.run(bench_llm(Settings().llm_model))
    print(f"VRAM with STT(cpu) + TTS + LLM: {vram_mb() - base} MB above baseline, {vram_mb()} MB total")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
