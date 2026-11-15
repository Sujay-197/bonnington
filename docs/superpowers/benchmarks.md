# Bonnington benchmarks (RTX 5060 Ti 16 GB, 31 GB RAM, Windows 11)

## Brain (Ollama 0.40.16), persona bake-off, 2026-11-15

| Model | First token (warm) | Notes |
|---|---|---|
| **gemma4:12b** (7.6 GB) — **chosen** | 370–690 ms | Short (1–2 sentences), on-character, mood tag every time, no invented facts |
| qwen3.5:9b (6.6 GB) | ~200 ms | Faster but rambles past 3 sentences, garbles numbers ("twenty-one-four"), invented a failed quiz |

Both emitted a valid `<mood:…>` tag on every reply. No softening/refusals seen with gemma4:12b, so no uncensored variant needed.

## Speech-to-text (sherpa-onnx, CPU, 4 threads)

Mic: OnePlus Nord Buds 4 Pro via MME (`mic_device = "Nord Buds MME"`). The Realtek default input has nothing plugged in.

| Model | Load | Final transcript after end of speech | RTF | Accuracy (5 clips) |
|---|---|---|---|---|
| **Nemotron streaming EN 0.6B int8, 160 ms** — **chosen** | 1.5 s | 192–203 ms | 0.24 | 4/5 ≥0.95 similarity; clip 1 clipped by late start; "Bonnington" → "Mornington" |

Nemotron streams partials and is fast enough; Parakeet (offline, no partials) is not needed.
