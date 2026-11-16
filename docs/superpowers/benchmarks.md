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

## Voice (Qwen3-TTS 1.7B Base, cloning locked voice 06c)

| Engine | First audio | Speed | Notes |
|---|---|---|---|
| qwen-tts 0.1.1 (official, SDPA) | ~1.8 s for a 2-word line | 0.7x real time (RTF 1.35–1.44) | Too slow: pauses before and between sentences |
| **faster-qwen3-tts 0.5.4 (CUDA graphs)** — **chosen** | ~380 ms (streaming) | 1.8–2.1x real time | Same weights, same voice; needs transformers<5 |

## VRAM, everything loaded together (desktop baseline ~1.1 GB)

| Config | Bonnington's share | Total on card |
|---|---|---|
| STT (CPU) + TTS 1.7B + gemma4:12b, default context | 14.8 GB | 15.9 GB — over budget |
| same, **Ollama num_ctx = 4096** — **chosen** | 13.5 GB | 14.6 GB |
| after go_dormant() | 0.3 GB | — |

Warm LLM first token with TTS resident: ~550 ms. TTS load incl. CUDA-graph capture: ~17 s; LLM load: ~3 s.

## Wake phrases (user's voice, Nord Buds mic, 20 s clips: 5x each phrase + 20 s normal talk)

| Detector | "Hey Britney" | "Hey Bonnington" | False triggers | CPU |
|---|---|---|---|---|
| sherpa KWS zipformer 3.3M (best of threshold/boost sweep) | 2/5 | 4/5 | 0 | low |
| **Nemotron streaming transcript + fuzzy match after a greeting, similarity 0.6** — **chosen** | **5/5** | **5/5** | **0** | ~30% of one core while listening |

Nemotron hears "Britney" as "Brittany" and "Bonnington" as "Mornington"/"Boydington"; fuzzy matching absorbs that.
The CPU cost only applies while the mic is open (a conversation, or "Always listening" on).
