import time
from faster_qwen3_tts import FasterQwen3TTS
LINE = open("data/voice/reference.txt", encoding="utf-8").read().strip()
t = time.perf_counter()
m = FasterQwen3TTS.from_pretrained("data/models/tts/Qwen3-TTS-12Hz-1.7B-Base", local_files_only=True)
print(f"load {time.perf_counter()-t:.1f}s", flush=True)
kw = dict(language="English", ref_audio="data/voice/reference.wav", ref_text=LINE)
m.generate_voice_clone(text="Warm up, please.", **kw)
for text in ["Britney. Again.", "No exams this week, which means you have absolutely no excuse tonight."]:
    t = time.perf_counter(); first = None; n = 0; sr = 24000
    for chunk, sr, timing in m.generate_voice_clone_streaming(text=text, chunk_size=8, **kw):
        if first is None: first = time.perf_counter() - t
        n += len(chunk)
    dt = time.perf_counter() - t
    print(f"stream: first audio {first*1000:.0f} ms, {dt:.2f}s for {n/sr:.1f}s audio, speed {n/sr/dt:.2f}x realtime", flush=True)
import subprocess; print(subprocess.run(["nvidia-smi","--query-gpu=memory.used","--format=csv,noheader"],capture_output=True,text=True).stdout)
