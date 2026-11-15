import asyncio, subprocess, time
from bonnington.config import Settings
from bonnington.tts import TTSEngine
from bonnington.stt import SherpaSTT
from bonnington.brain.llm import Brain
def v(): return int(subprocess.run(["nvidia-smi","--query-gpu=memory.used","--format=csv,noheader,nounits"],capture_output=True,text=True).stdout.split()[0])
async def main():
    s = Settings(); base = v(); print("baseline", base)
    stt = SherpaSTT(s); stt.load(); print("+stt", v()-base)
    tts = TTSEngine(s); t=time.perf_counter(); tts.load(); print(f"+tts {v()-base} (load {time.perf_counter()-t:.1f}s)")
    b = Brain(s.llm_model); t=time.perf_counter(); await b.warm(); print(f"+llm {v()-base} (load {time.perf_counter()-t:.1f}s) total {v()}")
    t=time.perf_counter(); first=None
    async for c in b.stream_reply("Hey. One short sentence."):
        first = first or time.perf_counter()-t
    u = tts.synth("Britney. Again. I am keeping receipts.")
    print(f"llm first token {first*1000:.0f} ms; tts ok {u.duration_ms} ms")
    tts.unload(); stt.unload(); await b.unload(); time.sleep(2); print("after unload", v()-base)
asyncio.run(main())
