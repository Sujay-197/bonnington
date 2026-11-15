# Bonnington — Phase 1: Voice Companion Design

Date: 2026-11-15
Status: draft, awaiting approval
Scope: phase 1 (voice). Phase 2 (planning: calendar, tasks, project status) is out of scope here but shapes a few interfaces below.

## 1. Intent

A personal, Jarvis-like companion the user talks to out loud and who answers out loud, with movie-style subtitles. He has a strong personality: **Bonnington**, summoned by the wake word **"Hey Britney"**, which he resents. Eventually (phase 2) he will know the user's exams, tasks and which coding projects are in progress, and nag/roast them into action. Phase 1 builds the voice, the face and the personality so that phase 2 only has to add knowledge and tools.

Why: motivation. The user wants a witty, uncensored companion whose teasing gets them moving. It handles personal data, so it must be fully local and cost nothing.

## 2. Goals

- Speak to him hands-free ("Hey Britney…") or via a global hotkey, hear him answer in a distinctive designed voice, and see synced subtitles.
- A personality that is consistent and genuinely funny, not generic-assistant polite.
- A screen that looks like the agreed mock: a slow, dense white particle globe on black, tinted by mood, subtitles under the globe.
- Responsive enough to feel like conversation.

## 3. Non-goals (phase 1)

- Calendar, tasks, exams, Claude project status — phase 2.
- ESP32 / room microphone — later; only the seam for it is built now.
- Languages other than English.
- Talking-over / full-duplex conversation.
- Mobile, multi-user, any network access beyond localhost.

## 4. Anti-goals (failure even if it "works")

- Anything leaves the machine at runtime (cloud APIs, telemetry, remote model calls). Network use is limited to one-off setup downloads (toolchains, packages, models), each approved by the user as described in §5.
- Using resources when not needed. Dormant, he must be close to invisible: games and calls must not notice him (see §7.7).
- Any recurring or one-off cost.
- Bonnington sounding like a corporate assistant: hedging, apologising, refusing to swear, breaking character.
- A busy, gadget-y UI. The screen is black, the globe and the subtitles. No visible buttons or menus in normal use.
- Jittery or fast motion. The movement has to match his unhurried personality.
- Cloning a real person's voice. His voice is original, designed from a text description.

## 5. Constraints

- **Hardware:** Windows 11, NVIDIA RTX 5060 Ti **16 GB VRAM**, 31 GB RAM, 16 threads.
- **Already installed:** Ollama 0.34.4 (an update to 0.40.x is available) with `qwen3:14b` (9.3 GB), `gemma4:12b`, `qwen3:4b`, `nomic-embed-text`.
- **VRAM budget:** STT + LLM + TTS resident together, target ≤ 15 GB.
- **Downloads:**
  - **Models:** ask the user before downloading **any** model weights, one at a time. This includes libraries that auto-fetch weights on first run. Say what it is, where it comes from and roughly how big it is.
  - **Toolchains and packages** (Python packages incl. CUDA PyTorch, Rust + MSVC Build Tools for Tauri, Node/npm, the Ollama update): put them together as **one list with sizes and get a single approval** for the batch. Anything added later goes in a new list.
- **Licences:** open weights usable for personal, non-commercial use.
- **Project folder:** `C:\Users\work\work\das_v0` (empty today, not yet a git repo).

## 6. Approaches considered

1. **Cascaded pipeline (wake word → VAD → streaming STT → LLM → streaming TTS) built on an existing open-source voice-pipeline framework, with our own UI on top.** ← **chosen**
   Subtitles and mood come for free because every stage is text. The LLM can call tools normally in phase 2. Personality and voice are fully controllable.
2. **The same cascade, all glue code hand-written.** Full control, but weeks spent on echo handling, interruption and audio/subtitle sync before any personality shows. Rejected as the starting point. It is the fallback if no framework fits (see §9).
3. **Single full-duplex speech-to-speech model** (e.g. NemotronLabs VoiceChat, Alba / LFM-Audio). Most natural turn-taking, but research-grade: weak persona control, immature tool calling, needs a separate pass for subtitles, competes with the planner for VRAM. Rejected for now; worth revisiting later.

## 7. The design

### 7.1 Pipeline

```
[audio source] → [wake word | hotkey] → [VAD: end of turn] → [streaming STT]
     → [LLM (Ollama) + persona + mood tag] → [sentence chunker] → [TTS (designed voice)]
     → [speaker out] + [events → UI: state, partial transcript, subtitle words, amplitude, mood]
```

- **Audio source** is a pluggable interface (`AudioSource`). Phase 1 implements the PC default mic. An ESP32 network mic is a later implementation of the same interface; nothing else may depend on the source being local.
- **Activation:**
  - Wake word **"Hey Britney"**, trained with openWakeWord (runs on CPU).
  - A second wake phrase, **"Hey Bonnington"**, wakes him too and is reported to the brain as such (he's pleased).
  - A **global hotkey** as backup (tap to start a turn). The key is the builder's choice; it must be configurable.
- **Follow-up window** (my call): after he finishes speaking, listen for ~8 s without needing the wake word again, so a back-and-forth flows. Outside the window he needs the wake word or hotkey.
- **Turn end:** Silero VAD.
- **STT:** English-only streaming model. Candidates: NVIDIA Nemotron Speech Streaming (0.6B) or Parakeet TDT 0.6B. Partial transcripts stream to the UI while the user speaks.
- **LLM:** Ollama, starting with `qwen3:14b` (already installed). Streamed output. Thinking/reasoning mode off for conversational turns (latency).
- **TTS:** Qwen3-TTS.
  - **Voice creation, a one-off:** use the VoiceDesign model (`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`) to generate several candidate voices from a description along the lines of *"low, unhurried male baritone, slightly breathy, articulate, amused, as if he knows something you don't; long deliberate pauses; crisp consonants."* The user listens and picks one.
  - **Locking the voice:** save the picked clip as the reference voice. At runtime, use the Base model (`Qwen/Qwen3-TTS-12Hz-1.7B-Base`) to speak in that exact voice every time.
  - LLM output is split at sentence boundaries and each sentence is synthesised as soon as it completes, so he starts speaking before the whole reply is written.
- **Interruptions** (my call): while he is speaking, the hotkey or the wake word stops him immediately and starts a new turn. Talking over him without a trigger does nothing in phase 1.
- **Echo** (my call): default **half-duplex**. The mic is ignored for wake word/STT while he is speaking, apart from the wake-word interrupt above. That interrupt may false-trigger on speaker playback, so it is only enabled when a "headphones" setting is on, or once echo cancellation is added later.

### 7.2 Personality (system prompt content)

- **Identity:** an original character named **Bonnington**. His style takes inspiration from a James Spader-type delivery: unhurried, eloquent, theatrical vocabulary, amused, always three steps ahead. He never claims to be an actor or an existing fictional character.
- **Relationship:** he teases the user relentlessly. **Uncensored: profanity allowed, nothing off-limits in tone.** The point of the roasting is motivation, so it is grounded in facts wherever facts exist (phase 2 will supply many more).
- **Drops the act when it matters:** urgent matters get a straight, crisp answer that is still witty but leads with the facts.
- **The Britney gag:**
  - A persisted **grudge counter** of how many times he's been called Britney. He brings up the number at well-chosen moments.
  - His reaction to being summoned varies with context the app passes in: the count, time of day, time since the last summons, and summons frequency (e.g. five times in ten minutes). There is no canned line.
  - Being called "Bonnington" makes him visibly pleased.
- **Brevity:** spoken replies are short by default (a few sentences). He only goes long when asked.
- **Tool honesty:** in phase 1 he has no calendar or project data. If asked, he says so in character instead of inventing anything.
- **Model behaviour:** if the default models soften the language despite the prompt, the fallback is a community "uncensored/abliterated" variant of the same family on Ollama. That needs a download, so ask first.

### 7.3 Mood

- Each LLM reply begins with a machine-readable tag, e.g. `<mood:annoyed>`. The backend strips it before TTS and before the subtitles, and sends it to the UI. If the tag is missing or invalid, the mood stays at its previous value.
- **Moods and colours** (as agreed in the mock):

  | Mood | Colour (RGB) | Typical trigger |
  |---|---|---|
  | neutral | 255,255,255 | default |
  | amused | 250,199,117 (amber) | user being dumb in a fun way |
  | annoyed | 240,90,80 (red) | "Britney", ignored reminders |
  | smug | 175,169,236 (violet) | "Bonnington", being right |
  | serious | 133,183,235 (blue) | urgent matters, the act dropped |
  | disappointed | 150,150,145 (grey) | neglected things |

- **Stretch, optional:** if Qwen3-TTS supports tone/emotion instructions on a cloned/locked voice, pass the mood to adjust delivery. If it doesn't, the mood is colour only.

### 7.4 Screen (UI)

- **Shell:** Tauri desktop app (my call: much lighter than Electron), rendering a web front-end. Borderless window, black background, resizable, with fullscreen and small-corner sizes. No visible controls in normal use. A minimal settings surface may exist behind a keyboard shortcut.
- **Reference mock:** `docs/superpowers/specs/2026-11-15-bonnington-ui-mock.html` (agreed v3). Its globe code can be ported directly; its buttons and state label are mock-only.
- **Globe:**
  - Roughly 9,000 1-px white particles on a sphere, tilted, deformed by slow noise, with a brighter, denser band around the lower half (the reference: a Pinterest particle-ring video).
  - **Motion must be slow and smooth.** The agreed mock (v2/v3) sets the pace: idle rotation ~0.05 rad/s, surface noise at ~¼ real time, about 2 s eased transitions between states.
- **States:**
  - **idle:** slow drift.
  - **listening:** the globe contracts slightly; the user's partial transcript shows faint grey under the globe and fades out after the turn.
  - **thinking:** the globe turns a little faster, still calm.
  - **speaking:** the globe "breathes" slowly, driven by the real TTS output amplitude (smoothed), not a fake oscillator.
- **Mood tint:** the particles (mostly the bright band) are tinted toward the mood colour, plus a very faint radial glow behind the globe. Colours cross-fade slowly.
- **Subtitles:**
  - Serif, ~15 px at default window size, scaling with the window, centred under the globe.
  - Words appear in sync with his audio: per-word timing if the TTS provides it, otherwise estimated per sentence from the audio duration.
  - Only the current sentence or two are shown; older lines fade out.
- **Backend ↔ UI:** a WebSocket bound to `127.0.0.1` only. Events: `state`, `mood`, `user_partial`, `user_final`, `subtitle_word`/`subtitle_line`, `amplitude`.

### 7.5 Backend

- Python (the speech-model ecosystem is Python-first), managed with a single env/lockfile.
- Runs as a tray-hosted local process that opens the Tauri window on demand (see §7.7).
- **Persisted local state** (a small file or SQLite in the project): the grudge counter, summons timestamps, chosen voice reference, settings (hotkey, headphones mode, model names).
- **Conversation memory:** the current session's history only, trimmed to fit context. Long-term memory belongs to phase 2.
- **Phase 2 seam:** the brain module accepts a list of tools, empty in phase 1, so phase 2 can register calendar, task and project-status tools without restructuring.

### 7.6 Performance targets

- **Response time:** first audible word within ~1.5 s of the end of the user's speech, measured on this machine. **This is best-effort.** The user chose to keep the designed voice and the 14B brain even if replies take 2–3 s, so tune latency (streaming, chunking, warm models) rather than swapping models to hit the number. The warm-up after a cold start is covered in §7.7.
- **VRAM:** STT + LLM + TTS resident at once, ≤ 15 GB.
- **Fallback if the VRAM budget doesn't fit**, in order:
  1. A smaller TTS variant, if one exists.
  2. An ~8B LLM instead of 14B.
  3. STT on CPU.

### 7.7 Lifecycle and resource use (proposed, pending user approval)

The user wants him dormant (near-zero resources) unless needed, especially during games and calls. They asked for an analysis of what an always-on wake word costs. Proposed design:

- **Levels:**

  | Level | What runs | Estimated cost |
  |---|---|---|
  | **Off** | nothing | 0 |
  | **Asleep** | tray icon plus a check every few seconds for a game or call; mic closed | ~0% CPU, ~30–60 MB RAM, 0 VRAM |
  | **Dormant** (default) | tray icon plus mic stream plus openWakeWord on CPU; no window, no models loaded | ~1–2% of one CPU core, ~150–250 MB RAM, 0 VRAM |
  | **Awake** | STT + LLM + TTS loaded on the GPU, window shown | ~12–15 GB VRAM, GPU busy only while thinking or speaking |

  The figures are estimates. The builder measures them in the first milestone and reports back.
- **Startup:** a lightweight tray process starts at Windows login, in Dormant. The Tauri window/WebView is **created only when he wakes and destroyed when he goes back to sleep**, not merely hidden, so it holds no memory while dormant.
- **Auto-sleep (Dormant → Asleep):** stop listening entirely and close the mic when either is true:
  - **a full-screen app/game is in the foreground**;
  - **another app is actively using the microphone** (a call: Discord, Meet, Teams…).

  He returns to Dormant automatically when neither is true. The hotkey still works while Asleep.
- **Manual sleep:** a tray toggle and the hotkey, e.g. "do not disturb".
- **Unloading:** after **~10 min with no interaction**, unload all models from VRAM and destroy the window, returning to Dormant.
- **Cold start:**
  - The first reply after an unload will take several extra seconds while the models load from disk. Model loading starts the instant the wake word fires, in parallel with the user still talking.
  - While warming up, the globe appears immediately so the user knows he heard.
  - If the warm-up runs long, a **pre-rendered sigh/"hm"** in his voice can play. A short sound, not a line, so it doesn't break the no-canned-lines rule.
- **Backend process shape:** one tray-hosted backend process that owns the mic, the wake word and the model lifecycle. The Tauri UI is a child window it opens on demand. This replaces the "sidecar of Tauri" idea in §7.5.

## 8. Model download list (each needs explicit user approval before download)

| Purpose | Candidate | Approx size |
|---|---|---|
| Wake word | openWakeWord base models + custom "hey britney"/"hey bonnington" | small (MBs). Training a custom word may itself pull TTS/data, so ask |
| VAD | Silero VAD | ~2 MB |
| STT | Nemotron Speech Streaming 0.6B **or** Parakeet TDT 0.6B | ~1–2.5 GB |
| TTS (one-off) | Qwen3-TTS 1.7B VoiceDesign | several GB |
| TTS (runtime) | Qwen3-TTS 1.7B Base | several GB |
| LLM | `qwen3:14b` — **already installed** | — |
| LLM fallback | uncensored variant / ~8B model | ~5–9 GB, only if needed |

Sizes are estimates; the builder confirms exact figures when asking.

## 9. Left to the builder

- **Which pipeline framework**, if any: HF `speech-to-speech`, Pipecat, or similar. It must allow a custom TTS (Qwen3-TTS with the locked voice), streaming partial transcripts, and exposing word timings and audio amplitude to our UI. If none fits cleanly on Windows, write the glue directly (approach 2), reusing their components.
- **Nemotron streaming vs Parakeet,** and how to run it on Windows (NeMo, ONNX/sherpa-onnx, etc.). Pick by measured latency and accuracy on this machine.
- How exactly openWakeWord is trained for the custom phrases.
- The default hotkey, the WebSocket message schema details, file layout, and the persistence format.
- Particle rendering technique (Canvas 2D vs WebGL) — whichever keeps it smooth at ~9,000+ particles.
- Exact persona prompt wording, within §7.2.
