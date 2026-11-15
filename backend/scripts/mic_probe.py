"""Probe input paths with a callback stream and a hard time limit; report audio received and peak level."""
import queue
import sys
import time

import numpy as np
import sounddevice as sd

for q in sys.argv[1:]:
    try:
        info = sd.query_devices(q, "input")
        sr = 16000 if "MME" in q else int(info["default_samplerate"])
        got: queue.Queue = queue.Queue()

        def cb(indata, frames, t, status, got=got):
            got.put((len(indata), int(np.abs(indata.astype(np.int32)).max()), str(status)))

        s = sd.InputStream(device=q, samplerate=sr, channels=1, dtype="int16", blocksize=sr // 12, callback=cb)
        s.start()
        t0 = time.time()
        n = pk = 0
        statuses = set()
        while time.time() - t0 < 3:
            try:
                k, p, st = got.get(timeout=0.5)
                n += k
                pk = max(pk, p)
                statuses.add(st)
            except queue.Empty:
                pass
        s.abort()
        s.close()
        print(f"{q}: sr={sr} got {n / sr:.2f}s of audio in 3s, peak {pk}, status {statuses}", flush=True)
    except Exception as e:
        print(f"{q}: FAIL {e}", flush=True)
