# Bonnington Phase 1 (Voice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local, zero-cost voice companion ("Bonnington", woken by "Hey Britney") that listens, thinks with Ollama, answers in a designed voice, and shows a mood-tinted particle globe with synced subtitles. It sits near-dormant whenever it isn't needed.

**Architecture:**
- A Python backend runs in the tray from login.
  - It owns the mic, the wake word, the hotkey, the model lifecycle and the conversation loop.
  - It pushes UI events over a WebSocket on `127.0.0.1`.
- A Tauri window renders the globe and subtitles.
  - The backend launches the window when Bonnington wakes and kills it when he goes back to sleep.
- **Plan decision (allowed by spec §9):** the pipeline is **thin glue written directly over component libraries** (openWakeWord, Silero VAD, sherpa-onnx, the Ollama client, qwen-tts), not a pipeline framework.
  - Reason: the tray lifecycle, unloading models, per-line subtitle timing and the amplitude feed, all on Windows, would fight a framework's own process and audio model.

**Tech Stack:**
- **Backend:** Python 3.12 managed with `uv`. Libraries: `sounddevice`, `numpy`, `openwakeword`, `silero-vad` (ONNX), `sherpa-onnx`, `ollama`, `qwen-tts`, `websockets`, `pystray`, `pynput`, `pytest`, `pytest-asyncio`.
- **UI:** Tauri 2 (Rust and MSVC Build Tools), vanilla JS front-end, `vitest` for UI logic.

**Spec:** `docs/superpowers/specs/2026-11-15-bonnington-voice-design.md` (+ UI reference `docs/superpowers/specs/2026-11-15-bonnington-ui-mock.html`)

## Global Constraints

- Nothing leaves the machine at runtime. No cloud APIs, no telemetry. The WebSocket binds to `127.0.0.1` only.
- Zero cost.
- **Models:** ask the user before downloading **any** model weights, one at a time, including libraries that auto-fetch weights on first run. Say what it is, where it comes from and roughly how big it is.
- **Toolchains and packages:** one list with sizes and a single approval for the batch. Anything added later goes in a new list.
- English only.
- VRAM budget: STT + LLM + TTS resident together, target ≤ 15 GB.
- Response time: first audible word within ~1.5 s of the end of the user's speech is **best-effort**. Keep the designed voice and the 14B model; tune rather than swap.
- LLM: Ollama `qwen3:14b`, streamed, thinking mode off.
- TTS: Qwen3-TTS. VoiceDesign `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` is used once to create the voice. Base `Qwen/Qwen3-TTS-12Hz-1.7B-Base` speaks with the locked reference at runtime.
- Wake phrases: "Hey Britney" (increments the grudge counter) and "Hey Bonnington" (he's pleased). The global hotkey is configurable.
- Follow-up window: ~8 s after he finishes speaking. Unload models after ~10 min with no interaction.
- Half-duplex by default. The wake-word interrupt while he's speaking is enabled only with `headphones_mode=True`.
- Mood tag format `<mood:NAME>` at the start of each reply, where NAME is one of `neutral, amused, annoyed, smug, serious, disappointed`. A missing or invalid tag keeps the previous mood.
- Mood colours (RGB):

  | Mood | RGB |
  |---|---|
  | neutral | 255,255,255 |
  | amused | 250,199,117 |
  | annoyed | 240,90,80 |
  | smug | 175,169,236 |
  | serious | 133,183,235 |
  | disappointed | 150,150,145 |

- **UI:**
  - Borderless black window, no visible controls.
  - About 9,000 1-px particles.
  - Idle rotation ~0.05 rad/s, surface noise at ~¼ speed, about 2 s eased transitions.
  - Subtitles in a serif font, ~15 px at the default window size, under the globe; only the current 1–2 lines are shown.
- **Persona:**
  - The character is named Bonnington. Spader-ish delivery, but never claims to be an actor or an existing character.
  - Uncensored; profanity allowed.
  - Roasts the user with facts.
  - Drops the act for urgent matters.
  - Short replies by default.
  - In phase 1 he has no calendar or project data and says so in character.
- Process levels: `OFF`, `ASLEEP` (game in full screen or mic used by another app: mic closed), `DORMANT` (mic plus wake word on the CPU, no models, no window), `AWAKE`.

## Review Focus

1. **Ollama isn't running, or `qwen3:14b` is missing, when he wakes.** Expected: he doesn't hang in "thinking". The UI shows a short serious-mood subtitle ("My brain is offline. Start Ollama.") and goes back to idle. Pinned in Task 5.
2. **The mood tag is split across streamed chunks** (`<mo` + `od:annoyed>Hi`), missing, or unknown. Expected: the tag is never spoken or subtitled, and the mood stays unchanged if the tag is invalid. Pinned in Task 4.
3. **His own speech through the speakers says "Britney" while `headphones_mode` is off.** Expected: it's ignored, not treated as an interrupt and not counted. Pinned in Task 11.
4. **The hotkey is pressed twice quickly, or during a cold model load.** Expected: one turn, not two, and no double count. Pinned in Task 11.
5. **The default mic is unplugged or changed while dormant.** Expected: no crash. The backend retries opening the default device every 5 s and logs it. Pinned in Task 9.

---

## File Structure

```
das_v0/
  .gitignore                         data/, .venv/, node_modules/, target/
  backend/
    pyproject.toml
    bonnington/
      __init__.py
      __main__.py                    entry: tray + lifecycle + orchestrator
      config.py                      Settings (JSON at data/settings.json)
      store.py                       GrudgeStore + SummonsContext (SQLite at data/bonnington.db)
      events.py                      UI event dataclasses -> JSON
      bridge.py                      UIBridge: WebSocket server 127.0.0.1
      audio/source.py                AudioSource protocol, MicSource
      audio/player.py                AudioPlayer (playback + amplitude + stop)
      wake.py                        WakeDetector (openWakeWord)
      hotkey.py                      HotkeyListener (pynput)
      vad.py                         TurnDetector (Silero)
      stt.py                         STTEngine protocol + SherpaSTT
      brain/mood.py                  MoodParser (streaming tag strip)
      brain/chunker.py               SentenceChunker
      brain/persona.py               build_system_prompt, build_summons_note
      brain/llm.py                   Brain (Ollama streaming, keep_alive, unload, tools)
      tts.py                         TTSEngine (Qwen3-TTS Base + reference), estimate_word_offsets
      orchestrator.py                Conversation loop
      lifecycle.py                   Level, next_level, LifecycleController
      sysprobe.py                    is_fullscreen_app(), mic_in_use_by_other()
      ui_process.py                  launch/kill the Tauri window
      tray.py                        pystray icon + menu
    scripts/
      design_voice.py                one-off VoiceDesign candidate generation
      bench.py                       STT/TTS/LLM latency + VRAM measurement
      train_wakeword.md              exact steps used to train custom phrases
    tests/                           pytest; hardware tests marked @pytest.mark.hw
  ui/
    package.json
    src/index.html  src/globe.js  src/subtitles.js  src/store.js  src/bridge.js  src/main.js
    tests/store.test.js  tests/subtitles.test.js
    src-tauri/                       Tauri 2 app (window config only)
  data/                              gitignored runtime state, voice reference, wake models
  docs/superpowers/benchmarks.md     results from Task 6 and Task 14
```

---

### Task 1: Repo, toolchain approval, backend skeleton

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/bonnington/__init__.py`, `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: a `uv` project at `backend/` and the `pytest` marker `hw` (excluded by default via `addopts = "-m 'not hw'"`).

- [ ] **Step 1: Present the toolchain list for one approval.**
  - Collect: Python 3.12 (via uv), uv, the Python packages from the Tech Stack incl. CUDA PyTorch (~3 GB), Rust (rustup), MSVC Build Tools (~2–6 GB), Node LTS, and optionally the Ollama 0.40.x update.
  - Give each item its approximate size, and get **one** yes. **Stop if declined.**
  - Check what's already installed first (`uv --version`, `rustc --version`, `node --version`) and leave those off the list.
- [ ] **Step 2: Install the approved items.** Run `git init`, then add a `.gitignore` containing `data/ .venv/ node_modules/ ui/src-tauri/target/ __pycache__/`.
- [ ] **Step 3: Write `tests/test_smoke.py`.** It asserts `import bonnington` works and `bonnington.__version__ == "0.1.0"`.
- [ ] **Step 4: Run `cd backend; uv run pytest`.** Expected: FAIL (no module).
- [ ] **Step 5: Create `pyproject.toml` and `__init__.py`.**
  - `pyproject.toml`: Python `>=3.12,<3.13`, the deps above; the PyTorch CUDA index matches the installed CUDA driver (621.x supports CUDA 12.8+).
  - `__init__.py` sets `__version__ = "0.1.0"`.
- [ ] **Step 6: Run `uv run pytest`.** Expected: 1 passed.
- [ ] **Step 7: Commit.**

```bash
git add -A
git commit -m "chore: scaffold bonnington backend"
```

### Task 2: Settings and grudge store

**Files:**
- Create: `backend/bonnington/config.py`, `backend/bonnington/store.py`
- Test: `backend/tests/test_config.py`, `backend/tests/test_store.py`

**Interfaces:**
- Produces:
  - `Settings` (dataclass) with these fields and defaults:

    | Field | Type | Default |
    |---|---|---|
    | `hotkey` | str | `"<ctrl>+<alt>+b"` |
    | `headphones_mode` | bool | `False` |
    | `llm_model` | str | `"qwen3:14b"` |
    | `stt_model_dir` | str | `"data/models/stt"` |
    | `tts_model` | str | `"Qwen/Qwen3-TTS-12Hz-1.7B-Base"` |
    | `voice_ref_wav` | str | `"data/voice/reference.wav"` |
    | `voice_ref_text` | str | `"data/voice/reference.txt"` |
    | `wake_models` | dict[str,str] | `{"britney": "data/wake/hey_britney.onnx", "bonnington": "data/wake/hey_bonnington.onnx"}` |
    | `wake_threshold` | float | `0.5` |
    | `followup_seconds` | float | `8.0` |
    | `idle_unload_seconds` | float | `600.0` |
    | `ws_port` | int | `8765` |

  - `load_settings(path: Path) -> Settings` (missing file → defaults written to disk; unknown keys ignored) and `save_settings(s: Settings, path: Path) -> None`.
  - `SummonKind = Literal["britney", "bonnington", "hotkey"]`.
  - `SummonsContext` (frozen dataclass):
    - `kind: SummonKind`
    - `britney_count: int`
    - `seconds_since_last: float | None`
    - `summons_last_10min: int`
    - `local_time: datetime`
  - `GrudgeStore(db_path: Path)` with:
    - `record_summons(kind: SummonKind, now: datetime) -> SummonsContext`
    - `britney_count() -> int`

- [ ] **Step 1: Write the failing tests.**

```python
def test_load_settings_creates_defaults(tmp_path):
    s = load_settings(tmp_path / "settings.json")
    assert s.followup_seconds == 8.0 and s.idle_unload_seconds == 600.0
    assert (tmp_path / "settings.json").exists()

def test_load_settings_ignores_unknown_keys(tmp_path):
    p = tmp_path / "s.json"; p.write_text('{"ws_port": 9000, "bogus": 1}')
    assert load_settings(p).ws_port == 9000

def test_britney_increments_and_bonnington_does_not(tmp_path):
    st = GrudgeStore(tmp_path / "b.db"); t0 = datetime(2026, 11, 15, 22, 0)
    assert st.record_summons("britney", t0).britney_count == 1
    ctx = st.record_summons("bonnington", t0 + timedelta(seconds=30))
    assert ctx.britney_count == 1 and ctx.seconds_since_last == 30.0

def test_summons_last_10min_counts_window(tmp_path):
    st = GrudgeStore(tmp_path / "b.db"); t0 = datetime(2026, 11, 15, 22, 0)
    for i in range(5): st.record_summons("britney", t0 + timedelta(minutes=i))
    ctx = st.record_summons("hotkey", t0 + timedelta(minutes=12))
    assert ctx.summons_last_10min == 4 and ctx.britney_count == 5   # minutes 2,3,4 + this one

def test_count_persists_across_instances(tmp_path):
    GrudgeStore(tmp_path / "b.db").record_summons("britney", datetime.now())
    assert GrudgeStore(tmp_path / "b.db").britney_count() == 1
```

  `summons_last_10min` includes the summons being recorded. A summons counts if it's within 600 s inclusive.
- [ ] **Step 2: Run `uv run pytest tests/test_config.py tests/test_store.py -v`.** Expected: FAIL (import errors).
- [ ] **Step 3: Implement `config.py` and `store.py`.** Use `sqlite3`, with one table `summons(ts REAL, kind TEXT)`. The count is a `COUNT(*) WHERE kind='britney'`.
- [ ] **Step 4: Run the tests.** Expected: all pass.
- [ ] **Step 5: Commit** `feat: settings and grudge store`.

### Task 3: UI events and WebSocket bridge

**Files:**
- Create: `backend/bonnington/events.py`, `backend/bonnington/bridge.py`
- Test: `backend/tests/test_events.py`, `backend/tests/test_bridge.py`

**Interfaces:**
- Produces:
  - Event dataclasses, each with a `to_json() -> str`. The `type` field equals the snake_case event name.
    - `StateEvent(value: Literal["idle","listening","thinking","speaking","waking"])`
      - `waking` = models are loading (a cold start).
    - `MoodEvent(value: Mood)`
      - `Mood = Literal["neutral","amused","annoyed","smug","serious","disappointed"]` lives in `events.py`.
    - `UserPartialEvent(text: str)`
    - `UserFinalEvent(text: str)`
    - `SubtitleLineEvent(id: int, text: str, duration_ms: int, word_offsets_ms: list[int])`
    - `ClearSubtitlesEvent()`
    - `AmplitudeEvent(value: float)`
      - Range 0..1, rounded to 3 decimals.
  - `UIBridge(port: int)` with:
    - `async start()`, binding **only** to `127.0.0.1`
    - `async stop()`
    - `broadcast(event) -> None` (non-blocking; drops if no clients)
    - `last_state_snapshot() -> list[str]`, the latest `state` and `mood` JSON, sent to each newly connected client.

- [ ] **Step 1: Write the failing tests.**

```python
def test_subtitle_event_json():
    e = SubtitleLineEvent(id=3, text="Hello.", duration_ms=900, word_offsets_ms=[0])
    assert json.loads(e.to_json()) == {"type": "subtitle_line", "id": 3, "text": "Hello.",
                                        "duration_ms": 900, "word_offsets_ms": [0]}

def test_amplitude_rounded():
    assert json.loads(AmplitudeEvent(0.123456).to_json())["value"] == 0.123

async def test_bridge_binds_localhost_and_replays_state(unused_tcp_port):
    b = UIBridge(unused_tcp_port); await b.start()
    b.broadcast(StateEvent("thinking")); b.broadcast(MoodEvent("annoyed"))
    async with websockets.connect(f"ws://127.0.0.1:{unused_tcp_port}") as ws:
        got = {json.loads(await ws.recv())["type"] for _ in range(2)}
    assert got == {"state", "mood"}
    assert all(s.getsockname()[0] == "127.0.0.1" for s in b.server.sockets)
    await b.stop()
```

- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use the `websockets` asyncio server with host `"127.0.0.1"`.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** `feat: ui event bridge`.

### Task 4: Mood parser, sentence chunker, persona prompt

**Files:**
- Create: `backend/bonnington/brain/__init__.py`, `brain/mood.py`, `brain/chunker.py`, `brain/persona.py`
- Test: `backend/tests/test_mood.py`, `test_chunker.py`, `test_persona.py`

**Interfaces:**
- Consumes: `Mood` (Task 3), `SummonsContext` (Task 2).
- Produces:
  - `MoodParser(current: Mood)` with `feed(chunk: str) -> str`, which returns the text with the tag removed.
    - Buffers up to 24 chars at the start of the reply until the tag resolves.
    - `.mood: Mood` is the result after the tag resolves.
    - `.reset()` is called per reply and keeps the current mood.
  - `SentenceChunker()` with:
    - `feed(text: str) -> list[str]`, returning completed sentences;
    - `flush() -> list[str]`.
    - It splits on `.`, `!`, `?`, `…` followed by whitespace, and on newlines.
    - It does not split on common abbreviations (`Mr.`, `Dr.`, `e.g.`, `i.e.`, `vs.`), or on decimals (`3.5`).
  - `build_system_prompt() -> str`.
  - `build_summons_note(ctx: SummonsContext) -> str`, a short bracketed note prepended to the user's first message of a session. Example: `[Summoned via "Hey Britney". Britney count: 215. Last summoned 4 min ago. 5 summons in the last 10 min. Local time 23:40.]`

- [ ] **Step 1: Write the failing tests.**

```python
def test_mood_tag_split_across_chunks():
    p = MoodParser("neutral")
    out = p.feed("<mo") + p.feed("od:annoyed>Britney") + p.feed(". Again.")
    assert out == "Britney. Again." and p.mood == "annoyed"

def test_missing_tag_keeps_previous_mood():
    p = MoodParser("smug"); assert p.feed("Well then.") == "Well then." and p.mood == "smug"

def test_invalid_tag_stripped_and_mood_unchanged():
    p = MoodParser("neutral"); assert p.feed("<mood:furious>Hm.") == "Hm." and p.mood == "neutral"

def test_tag_not_at_start_is_left_alone():          # only a leading tag counts
    p = MoodParser("neutral"); assert p.feed("Hm <mood:smug>") == "Hm <mood:smug>"

def test_chunker_streams_sentences():
    c = SentenceChunker()
    assert c.feed("Ah. Brit") == ["Ah."]
    assert c.feed("ney, Mr. Smith owes me 3.5 quid! Fine") == ["Britney, Mr. Smith owes me 3.5 quid!"]
    assert c.flush() == ["Fine"]

def test_system_prompt_pins_persona():
    p = build_system_prompt()
    for must in ["Bonnington", "<mood:", "neutral", "disappointed", "profanity", "short"]:
        assert must in p
    assert "James Spader" not in p        # style described, never named

def test_summons_note_britney():
    ctx = SummonsContext("britney", 215, 240.0, 5, datetime(2026, 11, 15, 23, 40))
    n = build_summons_note(ctx)
    assert '"Hey Britney"' in n and "215" in n and "4 min" in n and "23:40" in n

def test_summons_note_first_ever():
    ctx = SummonsContext("bonnington", 0, None, 1, datetime(2026, 11, 15, 9, 5))
    assert "first time" in build_summons_note(ctx).lower()
```

- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The system prompt content is fixed by spec §7.2 and §7.3:
    - an original character named Bonnington;
    - unhurried, eloquent, theatrical vocabulary, amused, three steps ahead;
    - never claims to be an actor or a fictional character;
    - teases relentlessly, uncensored, profanity allowed;
    - grounds roasts in facts;
    - drops the act for urgent matters;
    - 1–3 sentences unless asked for more;
    - no calendar or project data yet (say so in character, never invent);
    - the Britney grudge (use the count from the note, react to the context, no stock lines; pleased when called Bonnington);
    - spoken output only (no markdown, lists or emoji);
    - every reply MUST start with exactly one `<mood:NAME>` from the six names, with one line describing when to use each.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** `feat: mood parser, chunker, persona`.

### Task 5: Brain (Ollama client)

**Files:**
- Create: `backend/bonnington/brain/llm.py`
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `build_system_prompt` (Task 4).
- Produces: `Brain(model: str, client: ollama.AsyncClient | None = None, tools: list | None = None)` with:
  - `async warm() -> None`: loads the model with `keep_alive="30m"`.
  - `async unload() -> None`: a request with `keep_alive=0`.
  - `async stream_reply(user_text: str) -> AsyncIterator[str]`:
    - appends to the session history;
    - streams content chunks with `think=False` and `keep_alive="30m"`;
    - appends the full reply to the history when done.
  - `reset_session() -> None`.
  - `class BrainUnavailable(Exception)`: raised when the Ollama connection fails or the model is not found.
  - History trimming: keep the system prompt plus the last 20 messages.

- [ ] **Step 1: Write the failing tests using a fake client.**

```python
async def test_stream_reply_streams_and_records_history(fake_ollama):
    fake_ollama.script = ["<mood:smug>Oh, ", "Bonnington. ", "Finally."]
    b = Brain("qwen3:14b", client=fake_ollama)
    out = [c async for c in b.stream_reply("hey")]
    assert "".join(out) == "<mood:smug>Oh, Bonnington. Finally."
    call = fake_ollama.calls[-1]
    assert call["think"] is False and call["stream"] is True and call["keep_alive"] == "30m"
    assert call["messages"][0]["role"] == "system"
    assert b.history[-1] == {"role": "assistant", "content": "<mood:smug>Oh, Bonnington. Finally."}

async def test_connection_error_raises_brain_unavailable(fake_ollama):
    fake_ollama.raise_on_chat = httpx.ConnectError("refused")
    with pytest.raises(BrainUnavailable):
        [c async for c in Brain("qwen3:14b", client=fake_ollama).stream_reply("hey")]

async def test_unload_sends_keep_alive_zero(fake_ollama):
    await Brain("qwen3:14b", client=fake_ollama).unload()
    assert fake_ollama.calls[-1]["keep_alive"] == 0

def test_history_trimmed_to_20(fake_ollama):
    b = Brain("qwen3:14b", client=fake_ollama)
    for i in range(30): b._append("user", str(i))
    assert len(b._messages()) == 21 and b._messages()[0]["role"] == "system"

@pytest.mark.hw
async def test_real_ollama_replies_with_mood_tag():
    out = "".join([c async for c in Brain("qwen3:14b").stream_reply("Hey. Say hi.")])
    assert re.match(r"\s*<mood:(neutral|amused|annoyed|smug|serious|disappointed)>", out)
```

  `fake_ollama` is a conftest fixture: an object with `chat(**kw)` returning an async iterator of `{"message": {"content": s}}` from `script`, and recording `kw` in `calls`.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.** Map `httpx.ConnectError` and `ollama.ResponseError` (status 404) to `BrainUnavailable`.
- [ ] **Step 4: Run `uv run pytest tests/test_llm.py -v`.** Expected: pass. Then run `uv run pytest -m hw tests/test_llm.py` with Ollama running.
  - If replies lack the tag, or come back softened or refusing, note it in `docs/superpowers/benchmarks.md`.
  - Do **not** pull an uncensored variant without asking the user.
- [ ] **Step 5: Commit** `feat: ollama brain`.

### Task 6: Model approvals and benchmark spike (STT pick, TTS VRAM/latency)

**Files:**
- Create: `backend/scripts/bench.py`, `docs/superpowers/benchmarks.md`

**Interfaces:**
- Produces: a decision recorded in `benchmarks.md`. It sets the STT model (Nemotron streaming or Parakeet TDT 0.6B, via sherpa-onnx), sets its files under `data/models/stt/`, and gives measured VRAM per component.

- [ ] **Step 1: Ask the user, one model at a time, before each download.** For each, give the name, source and approximate size:
  - Silero VAD ONNX (~2 MB);
  - the sherpa-onnx export of the Nemotron streaming English model (~1–2 GB), **if one exists**; otherwise skip it;
  - the sherpa-onnx export of Parakeet TDT 0.6B (~1–2.5 GB);
  - Qwen3-TTS 1.7B Base (several GB).

  Download only what's approved.
- [ ] **Step 2: Write `bench.py`. It measures and prints:**
  - **STT:** real-time factor and time from the last audio frame to the final transcript, over 5 recorded WAV clips in `data/bench/` (the user records 5 short sentences; 3–6 s each).
  - **WER:** checked by eye against the typed reference text.
  - **TTS:** time to the first audio sample and real-time factor for 3 sentences of 5, 15 and 30 words, using any short reference clip (Task 7 replaces it).
  - **LLM:** time to the first token for `qwen3:14b` when warm.
  - **VRAM:** `nvidia-smi --query-gpu=memory.used`, with all three loaded together.
- [ ] **Step 3: Run `uv run python scripts/bench.py`.** Record the results in `benchmarks.md`.
  - Pick the STT with the lower final-transcript latency, unless its word error rate is visibly worse.
  - If the total VRAM is over 15 GB, apply the fallback order from spec §7.6:
    1. a smaller TTS variant;
    2. an ~8B LLM (**ask before pulling**);
    3. STT on the CPU.

    Record the choice.
- [ ] **Step 4: Commit** `docs: model benchmarks and STT choice`.

### Task 7: Voice design (one-off, user picks)

**Files:**
- Create: `backend/scripts/design_voice.py`

**Interfaces:**
- Produces: `data/voice/reference.wav` and `data/voice/reference.txt`, read by `TTSEngine` (Task 8).

- [ ] **Step 1: Ask the user before downloading** `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` (several GB).
- [ ] **Step 2: Write `design_voice.py --n 6 --out data/voice/candidates/`.**
  - It generates 6 candidates. Each speaks the same ~12 s line, which must include a pause and a mild swear, e.g. "Ah. Britney. You do realise that's not my name… and yet here I am, answering like a damned golden retriever."
  - Vary the base description from spec §7.1 slightly per candidate (pace, breathiness, depth).
  - Write `candidates/NN.wav` plus `candidates/NN.txt` (the description used).
- [ ] **Step 3: Run it. The user listens and picks one.** Copy the pick to `data/voice/reference.wav`, and put the spoken line in `reference.txt`.
- [ ] **Step 3b: Generate the warm-up sound.** With the picked reference and the Base model, generate a short sigh/"hm" clip (≤1 s) to `data/voice/hm.wav`. It is used during long cold starts (Task 11).
- [ ] **Step 4: Free the VoiceDesign weights' VRAM.** The model is not loaded at runtime. Ask the user whether to delete the downloaded VoiceDesign weights to save disk space.
- [ ] **Step 5: Commit** the script only (`data/` is gitignored): `feat: voice design script`.

### Task 8: TTS engine, audio player, subtitle timing

**Files:**
- Create: `backend/bonnington/tts.py`, `backend/bonnington/audio/__init__.py`, `audio/player.py`
- Test: `backend/tests/test_tts_timing.py`, `backend/tests/test_player.py`

**Interfaces:**
- Consumes: `Settings.tts_model`, `voice_ref_wav`, `voice_ref_text` (Task 2).
- Produces:
  - `Utterance` (dataclass): `pcm: np.ndarray[float32]`, `sample_rate: int`, `text: str`, `word_offsets_ms: list[int]`.
  - `TTSEngine(settings)` with:
    - `load() -> None` and `unload() -> None`, the latter also running `torch.cuda.empty_cache()`;
    - `is_loaded: bool`;
    - `synth(sentence: str) -> Utterance`, which uses the model's word timings if it provides them and otherwise falls back to `estimate_word_offsets`.
  - `estimate_word_offsets(text: str, duration_ms: int) -> list[int]`: the offsets are proportional to the cumulative character length of each word plus a weight of 0.3 per space; punctuation (`, . … ! ?`) adds extra weight (comma 2 chars, sentence end 4 chars) to the word that follows; the first offset is 0.
  - `AudioPlayer(on_amplitude: Callable[[float], None])` with:
    - `async play(u: Utterance) -> bool`, which returns False if it was stopped;
    - `stop() -> None`, which halts immediately;
    - `is_playing: bool`.
    - It calls `on_amplitude` at about 30 Hz with an RMS value of the current block normalised to 0..1 (`min(1, rms / 0.25)`), and sends a final 0.0 when it ends.

- [ ] **Step 1: Write the failing tests.**

```python
def test_offsets_start_at_zero_and_increase():
    o = estimate_word_offsets("Ah. Britney. Again.", 1500)
    assert o[0] == 0 and o == sorted(o) and len(o) == 3 and o[-1] < 1500

def test_pause_after_period_is_longer_than_after_word():
    o = estimate_word_offsets("Hm. a b", 1000)
    assert (o[1] - o[0]) > (o[2] - o[1])

async def test_player_stop_returns_false_and_zeroes_amplitude(fake_output_stream):
    amps = []; p = AudioPlayer(amps.append, stream_factory=fake_output_stream)
    u = Utterance(np.ones(48000, np.float32) * 0.1, 24000, "x", [0])
    task = asyncio.create_task(p.play(u)); await asyncio.sleep(0.1); p.stop()
    assert await task is False and amps[-1] == 0.0 and not p.is_playing
```

  `AudioPlayer` takes an optional `stream_factory`. It defaults to the `sounddevice.OutputStream` and is injected in tests.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.** `TTSEngine.synth` uses the qwen-tts voice-clone API with `reference.wav` + `reference.txt`.
- [ ] **Step 4: Run the tests.** Expected: pass. Then the hardware check: add a `@pytest.mark.hw` test, `test_synth_speaks_in_reference_voice`, which synthesises "Britney. Again." and asserts `0.5 s < duration < 4 s`. The user listens once and confirms it sounds like the chosen voice.
- [ ] **Step 5: Commit** `feat: tts engine and player`.

### Task 9: Audio source, VAD turn detection, STT

**Files:**
- Create: `backend/bonnington/audio/source.py`, `backend/bonnington/vad.py`, `backend/bonnington/stt.py`
- Test: `backend/tests/test_source.py`, `test_vad.py`, `test_stt.py`

**Interfaces:**
- Produces:
  - `AudioSource` (Protocol) with:
    - `async open() -> None` and `async close() -> None`;
    - `frames() -> AsyncIterator[np.ndarray[int16]]`, yielding 16 kHz mono frames of 1280 samples (80 ms);
    - `is_open: bool`.
  - `MicSource(device: int | None = None, retry_seconds: float = 5.0, stream_factory=...)`.
    - If the device fails or disappears, it logs, waits `retry_seconds`, reopens the **current default** device, and keeps yielding. The iterator never raises because of device loss.
  - `TurnDetector(silence_ms: int = 700, max_turn_s: float = 30.0)` with:
    - `feed(frame) -> TurnEvent | None`, where `TurnEvent = Literal["speech_start", "turn_end"]`;
    - `reset()`.
    - Uses Silero VAD ONNX. `turn_end` fires after `silence_ms` of non-speech following speech, or at `max_turn_s`.
  - `STTEngine` (Protocol) with:
    - `load()`, `unload()`, `is_loaded`;
    - `start_turn()`;
    - `feed(frame) -> str | None`, returning the new partial text when it changes;
    - `finish() -> str`, returning the final text.
  - `SherpaSTT(settings)` implements `STTEngine` with the model chosen in Task 6.

- [ ] **Step 1: Write the failing tests.**

```python
async def test_mic_source_recovers_from_device_loss(flaky_stream_factory):
    src = MicSource(retry_seconds=0.01, stream_factory=flaky_stream_factory(fail_after=3))
    await src.open(); frames = []
    async for f in src.frames():
        frames.append(f)
        if len(frames) == 6: break
    assert len(frames) == 6 and flaky_stream_factory.opens >= 2 and frames[0].shape == (1280,)

def test_turn_end_after_silence(fake_vad):        # fake_vad: scripted speech probs per frame
    td = TurnDetector(silence_ms=700, vad=fake_vad([1]*5 + [0]*9))
    events = [td.feed(np.zeros(1280, np.int16)) for _ in range(14)]
    assert events[0] == "speech_start" and events[-1] == "turn_end"   # 9 x 80 ms = 720 ms
    assert events.count("turn_end") == 1

def test_turn_capped_at_max(fake_vad):
    td = TurnDetector(max_turn_s=0.8, vad=fake_vad([1]*20))
    assert "turn_end" in [td.feed(np.zeros(1280, np.int16)) for _ in range(11)]

@pytest.mark.hw
def test_sherpa_transcribes_bench_clip():
    stt = SherpaSTT(load_settings(Path("data/settings.json"))); stt.load(); stt.start_turn()
    for f in frames_from_wav("data/bench/01.wav"): stt.feed(f)
    assert similar(stt.finish(), Path("data/bench/01.txt").read_text(), min_ratio=0.85)
```

- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use `sounddevice.InputStream` (16 kHz, int16, blocksize 1280) feeding an `asyncio.Queue`. Silero VAD comes via `onnxruntime` on the CPU.
- [ ] **Step 4: Run the tests.** Expected: pass (the hardware test is run manually).
- [ ] **Step 5: Commit** `feat: audio source, vad, stt`.

### Task 10: Wake words and hotkey

**Files:**
- Create: `backend/bonnington/wake.py`, `backend/bonnington/hotkey.py`, `backend/scripts/train_wakeword.md`
- Test: `backend/tests/test_wake.py`, `backend/tests/test_hotkey.py`

**Interfaces:**
- Produces:
  - `WakeDetector(models: dict[str, str], threshold: float, cooldown_s: float = 2.0, oww=None)` with:
    - `feed(frame) -> Literal["britney", "bonnington"] | None`;
    - `reset()`.
    - Once one phrase fires, both are suppressed for `cooldown_s`.
    - If both phrases score at or above the threshold on the same frame, the higher score wins.
  - `HotkeyListener(combo: str, on_press: Callable[[], None])` with `start()` and `stop()`, using `pynput.keyboard.GlobalHotKeys`.

- [ ] **Step 1: Ask the user before any download.** The download set is the openWakeWord base feature models (a few MB) plus whatever the custom-phrase training pipeline pulls (synthetic-speech TTS and negative datasets can be **multiple GB**). List them and ask.
  - If the user declines the training data, record the alternative in `train_wakeword.md`: record ~50 samples of each phrase by voice and train with the few-shot/verifier path.
- [ ] **Step 2: Train `hey_britney.onnx` and `hey_bonnington.onnx` into `data/wake/`.** Record the exact commands used in `train_wakeword.md`.
- [ ] **Step 3: Write the failing tests.**

```python
def test_fires_once_then_cooldown(fake_oww):
    w = WakeDetector({"britney": "a", "bonnington": "b"}, 0.5, cooldown_s=2.0,
                     oww=fake_oww([{"britney": .9}] * 30))      # 30 x 80 ms = 2.4 s of high score
    hits = [w.feed(np.zeros(1280, np.int16)) for _ in range(30)]
    assert hits.count("britney") == 2 and hits[0] == "britney"   # frame 0 and after 2 s

def test_higher_score_wins(fake_oww):
    w = WakeDetector({"britney": "a", "bonnington": "b"}, 0.5,
                     oww=fake_oww([{"britney": .6, "bonnington": .8}]))
    assert w.feed(np.zeros(1280, np.int16)) == "bonnington"

def test_hotkey_parses_combo():
    HotkeyListener("<ctrl>+<alt>+b", lambda: None)   # must not raise
    with pytest.raises(ValueError): HotkeyListener("not a combo++", lambda: None)
```

- [ ] **Step 4: Run, implement, re-run.** Expected: pass.
- [ ] **Step 5: Run the hardware check `@pytest.mark.hw test_live_wake`.** It runs the mic for 60 s. The user says each phrase 5 times plus 60 s of normal talk.
  - Record hits and false triggers in `benchmarks.md`.
  - Tune `wake_threshold` in settings if needed.
- [ ] **Step 6: Commit** `feat: wake words and hotkey`.

### Task 11: Orchestrator (the conversation loop)

**Files:**
- Create: `backend/bonnington/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes everything above:
  - `AudioSource`, `WakeDetector`, `TurnDetector`, `STTEngine`;
  - `Brain`, `MoodParser`, `SentenceChunker`;
  - `TTSEngine`, `AudioPlayer`;
  - `UIBridge`, the events, `GrudgeStore`, `Settings`.
- Produces: `Orchestrator(deps: Deps, clock: Callable[[], float] = time.monotonic)` with:
  - `async run() -> None`, the main loop over `source.frames()`;
  - `trigger(kind: SummonKind) -> None`, called by the hotkey and thread-safe;
  - `async ensure_awake() -> None`: loads STT, warms the Brain and loads TTS concurrently, and emits `StateEvent("waking")` while doing so;
  - `async go_dormant() -> None`: unloads all three;
  - `last_interaction: float` (clock time);
  - `on_wake_requested: Callable[[], None] | None`, used by lifecycle (Task 12) to show the window.
  - `Deps` is a dataclass holding the components, so tests can inject fakes.

Behaviour, implemented as an explicit state machine (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `FOLLOWUP`):

- **Wake:**
  - On a wake phrase or the hotkey while `IDLE`/`FOLLOWUP`: record the summons with `GrudgeStore.record_summons`.
  - Only for the **first** summons of a session, prepend `build_summons_note` to the user's message.
  - Then call `ensure_awake()` and enter `LISTENING`. Mic frames received during loading are buffered and fed to STT once it's loaded.
- **Cold-start sound:** if `ensure_awake()` takes longer than 3 s, play `data/voice/hm.wav` once through the player (no subtitle).
- **Partial transcript:** while `LISTENING`, emit a `UserPartialEvent` for every non-None result of `STTEngine.feed`.
- **Duplicates:** a second trigger while `LISTENING`/`THINKING`, or while `ensure_awake` is in progress, is ignored. It is not recorded.
- **Turn:** on `turn_end` → `UserFinalEvent`, then `THINKING`.
  - Stream from the Brain through `MoodParser`, then `SentenceChunker`, then `TTSEngine.synth` (the next sentence is synthesised while the current one plays), then `AudioPlayer.play`.
  - Emit `MoodEvent` when the mood resolves, and one `SubtitleLineEvent` per sentence at the moment it starts playing.
- **Empty transcript** (`""` after strip): go back to `IDLE` without calling the Brain.
- **`BrainUnavailable`:** `MoodEvent("serious")`, then a `SubtitleLineEvent` with the text "My brain is offline. Start Ollama." (no TTS), then `IDLE` after 4 s.
- **While `SPEAKING`:**
  - Wake-word frames are processed only if `headphones_mode`. A wake hit then calls `player.stop()`, emits `ClearSubtitlesEvent`, cancels the reply and starts a new `LISTENING` turn.
  - Otherwise the mic frames are discarded, so playback can't trigger him.
  - The hotkey always interrupts.
- **After the reply:** enter `FOLLOWUP` for `followup_seconds`. A VAD `speech_start` there begins a new turn without a wake word. On timeout go to `IDLE` and emit `StateEvent("idle")`.
- Emit `StateEvent` on every state change, and `AmplitudeEvent` through the player callback.

- [ ] **Step 1: Write the failing tests with fakes** (fake source frames, scripted wake/VAD/STT outputs, fake brain chunks, instant TTS, a recording bridge).

```python
async def test_full_turn_emits_expected_events(rig):
    rig.wake_on_frame(0, "britney"); rig.speech(frames=range(2, 10)); rig.stt_final("what's left")
    rig.brain_says("<mood:annoyed>Britney. Again.")
    await rig.run_until_idle()
    types = rig.event_types()
    assert types.index("state:listening") < types.index("user_final") < types.index("state:thinking")
    assert "mood:annoyed" in types and rig.subtitles() == ["Britney.", "Again."]
    assert rig.spoken() == ["Britney.", "Again."] and "<mood" not in "".join(rig.spoken())

async def test_first_message_carries_summons_note_only_once(rig):
    rig.two_turns_in_followup()
    await rig.run_until_idle()
    assert rig.brain_inputs[0].startswith("[Summoned via") and not rig.brain_inputs[1].startswith("[")

async def test_double_hotkey_is_one_turn(rig):
    rig.orch.trigger("hotkey"); rig.orch.trigger("hotkey")
    await rig.run_until_idle()
    assert rig.store.summons_count() == 1 and rig.brain_calls == 1

async def test_own_speech_britney_ignored_without_headphones(rig):
    rig.settings.headphones_mode = False
    rig.wake_on_frame(0, "britney"); rig.during_speaking_wake("britney")
    await rig.run_until_idle()
    assert rig.store.britney_count() == 1 and rig.player.stops == 0

async def test_wake_interrupts_with_headphones(rig):
    rig.settings.headphones_mode = True
    rig.wake_on_frame(0, "britney"); rig.during_speaking_wake("bonnington")
    await rig.run_until_idle()
    assert rig.player.stops == 1 and "clear_subtitles" in rig.event_types()

async def test_followup_window_allows_reply_without_wake(rig):
    rig.reply_then_speech_after(seconds=5.0)          # within 8 s
    await rig.run_until_idle(); assert rig.brain_calls == 2

async def test_followup_expires(rig):
    rig.reply_then_speech_after(seconds=9.0)          # after 8 s -> needs wake word
    await rig.run_until_idle(); assert rig.brain_calls == 1

async def test_brain_offline_shows_message(rig):
    rig.brain_raises(BrainUnavailable())
    rig.wake_on_frame(0, "britney"); rig.speech(frames=range(2, 6)); rig.stt_final("hi")
    await rig.run_until_idle()
    assert "My brain is offline. Start Ollama." in rig.subtitles() and "mood:serious" in rig.event_types()
    assert rig.spoken() == []

async def test_partials_streamed_to_ui(rig):
    rig.wake_on_frame(0, "britney"); rig.speech(frames=range(2, 6))
    rig.stt_partials(["what", "what's left"]); rig.stt_final("what's left")
    await rig.run_until_idle()
    assert rig.user_partials() == ["what", "what's left"]

async def test_slow_cold_start_plays_hm_once(rig):
    rig.load_takes(seconds=5.0); rig.wake_on_frame(0, "britney")
    await rig.run_until_idle(); assert rig.played_files() == ["data/voice/hm.wav"]

async def test_empty_transcript_skips_brain(rig):
    rig.wake_on_frame(0, "britney"); rig.speech(frames=range(2, 6)); rig.stt_final("  ")
    await rig.run_until_idle(); assert rig.brain_calls == 0
```

  `rig` is a conftest fixture that builds an `Orchestrator` with fakes and a fake clock. Its helper names are exactly as used above.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `uv run pytest tests/test_orchestrator.py -v`.** Expected: all pass.
- [ ] **Step 5: Commit** `feat: conversation orchestrator`.

### Task 12: Lifecycle, system probes, tray

**Files:**
- Create: `backend/bonnington/lifecycle.py`, `backend/bonnington/sysprobe.py`, `backend/bonnington/tray.py`, `backend/bonnington/__main__.py`
- Test: `backend/tests/test_lifecycle.py`, `backend/tests/test_sysprobe.py`

**Interfaces:**
- Consumes: `Orchestrator.ensure_awake/go_dormant/last_interaction/on_wake_requested` (Task 11), `MicSource.open/close` (Task 9), and `ui_process.show/hide` (Task 14; stubbed with no-ops until then).
- Produces:
  - `Level` (Enum): `OFF, ASLEEP, DORMANT, AWAKE`.
  - `next_level(current: Level, *, fullscreen: bool, mic_busy: bool, manual_dnd: bool, wake_requested: bool, idle_s: float, idle_unload_s: float) -> Level`.
  - `is_fullscreen_app() -> bool`: calls `SHQueryUserNotificationState` through `ctypes` and returns True for `QUNS_BUSY` (2), `QUNS_RUNNING_D3D_FULL_SCREEN` (3) and `QUNS_PRESENTATION_MODE` (4).
  - `mic_in_use_by_other(own_exe: str) -> bool`: scans `HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone` (packaged subkeys and `NonPackaged\*`) for entries with `LastUsedTimeStop == 0`, excluding keys whose path contains `own_exe`.
  - `LifecycleController(orch, mic, ui, probe_interval_s=3.0)` with `async run()`, `set_dnd(on: bool)` and `level`.
  - `tray.run_tray(controller)`, with these menu items:
    - "Do not disturb" (a toggle);
    - "Headphones mode" (a toggle that writes Settings);
    - "Quit".

Transition rules for `next_level`, checked in this order:

1. `manual_dnd`, `fullscreen` or `mic_busy` → `ASLEEP`. This also overrides `AWAKE`, which unloads.
2. `wake_requested` → `AWAKE`. This covers the hotkey: the hotkey listener stays active even while `ASLEEP`, but the mic-based wake word doesn't run then. When the hotkey wakes him from `ASLEEP`, the probes are bypassed until the next idle.
3. `AWAKE` with `idle_s >= idle_unload_s` → `DORMANT`.
4. Otherwise `ASLEEP` → `DORMANT`, and the current level stays.

- [ ] **Step 1: Write the failing tests.**

```python
@pytest.mark.parametrize("kw,expected", [
    (dict(fullscreen=True), Level.ASLEEP),
    (dict(mic_busy=True), Level.ASLEEP),
    (dict(manual_dnd=True), Level.ASLEEP),
    (dict(wake_requested=True), Level.AWAKE),
])
def test_next_level_from_dormant(kw, expected):
    base = dict(fullscreen=False, mic_busy=False, manual_dnd=False, wake_requested=False,
                idle_s=0, idle_unload_s=600)
    assert next_level(Level.DORMANT, **{**base, **kw}) == expected

def test_awake_unloads_after_10_min():
    assert next_level(Level.AWAKE, fullscreen=False, mic_busy=False, manual_dnd=False,
                      wake_requested=False, idle_s=600, idle_unload_s=600) == Level.DORMANT

def test_asleep_returns_to_dormant_when_clear():
    assert next_level(Level.ASLEEP, fullscreen=False, mic_busy=False, manual_dnd=False,
                      wake_requested=False, idle_s=0, idle_unload_s=600) == Level.DORMANT

async def test_controller_closes_mic_when_asleep_and_unloads_when_dormant(fake_world):
    c = fake_world.controller(); fake_world.wake(); await fake_world.tick()
    assert c.level == Level.AWAKE and fake_world.ui.shown
    fake_world.fullscreen = True; await fake_world.tick()
    assert c.level == Level.ASLEEP and not fake_world.mic.is_open
    assert fake_world.orch.unloaded and not fake_world.ui.shown

def test_mic_probe_excludes_own_exe(fake_registry):
    fake_registry.add("NonPackaged/C:#py#python.exe", last_stop=0)
    assert mic_in_use_by_other("C:#py#python.exe", reg=fake_registry) is False
    fake_registry.add("NonPackaged/C:#Discord#Discord.exe", last_stop=0)
    assert mic_in_use_by_other("C:#py#python.exe", reg=fake_registry) is True
```

  `mic_in_use_by_other` takes an optional `reg` adapter so it can be tested; it defaults to `winreg`.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `__main__.py` does the wiring: load Settings, build the deps, start the bridge, start the hotkey, run the controller and orchestrator on one asyncio loop, and run the tray on the main thread.
  - Add a `--register-startup` flag that creates a shortcut in `shell:startup` to `pythonw -m bonnington`. Do **not** register it automatically; ask the user when it's time.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Run `uv run python -m bonnington` and check by hand:**
  - Launch a full-screen game or video and confirm the tray tooltip shows "Asleep" within ~3 s.
  - Join a Discord or Meet test call and confirm "Asleep".
  - Leave both and confirm "Dormant".
- [ ] **Step 6: Commit** `feat: lifecycle, probes, tray`.

### Task 13: UI (Tauri window, globe, subtitles)

**Files:**
- Create: `ui/package.json`, `ui/src/index.html`, `ui/src/globe.js`, `ui/src/subtitles.js`, `ui/src/store.js`, `ui/src/bridge.js`, `ui/src/main.js`, `ui/src-tauri/` (via `npm create tauri-app`, vanilla template), `ui/tests/store.test.js`, `ui/tests/subtitles.test.js`

**Interfaces:**
- Consumes: the event JSON from Task 3 at `ws://127.0.0.1:8765`.
- Produces:
  - `reduce(state, event) -> state` in `store.js`. The state is `{ phase, mood, userText, lines: [{id, text, startedAt, durationMs, wordOffsetsMs}], amplitude }`.
    - `user_partial` sets `userText`; `user_final` sets it and stamps `userTextAt`.
    - `state:speaking` clears `userText`.
    - `subtitle_line` appends and keeps the last 2 lines.
    - `clear_subtitles` empties the lines.
    - Unknown event types are ignored.
  - `visibleWords(line, nowMs) -> string`: the words whose offset is at or before `nowMs - line.startedAt`.
  - `MOOD_RGB` in `globe.js`: the exact RGB table from Global Constraints.
  - `bridge.js` reconnects every 1 s while disconnected.

- [ ] **Step 1: Write the failing tests.**

```js
test("keeps only last two subtitle lines", () => {
  let s = initialState();
  for (const id of [1, 2, 3]) s = reduce(s, { type: "subtitle_line", id, text: `L${id}`, duration_ms: 500, word_offsets_ms: [0] });
  expect(s.lines.map(l => l.id)).toEqual([2, 3]);
});
test("unknown event ignored", () => {
  const s = initialState(); expect(reduce(s, { type: "bogus" })).toEqual(s);
});
test("speaking clears user text", () => {
  let s = reduce(initialState(), { type: "user_partial", text: "hey" });
  expect(reduce(s, { type: "state", value: "speaking" }).userText).toBe("");
});
test("visibleWords reveals by offset", () => {
  const line = { text: "Britney. Again. Really.", startedAt: 1000, wordOffsetsMs: [0, 400, 900] };
  expect(visibleWords(line, 1500)).toBe("Britney. Again.");
});
test("mood table matches spec", () => {
  expect(MOOD_RGB.annoyed).toEqual([240, 90, 80]); expect(MOOD_RGB.smug).toEqual([175, 169, 236]);
});
```

- [ ] **Step 2: Run `cd ui; npx vitest run`.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Port the globe from `docs/superpowers/specs/2026-11-15-bonnington-ui-mock.html`. Keep its constants: 9000 particles, idle spin 0.05, the ¼-speed noise, the 0.02 ease factors, the band formula, the glow alpha 0.06. Remove the mock's buttons and state label.
  - Drive it from the store:
    - `phase` sets the spin/scale targets as in the mock;
    - `waking` uses the `listening` targets;
    - `amplitude` replaces the mock's fake oscillator (smoothed with factor 0.04);
    - `mood` drives the tint.
  - Keep Canvas 2D if it holds ≥55 fps at 1080p on this machine (check in Step 5). Otherwise switch to WebGL points with the same maths.
  - Subtitles: a serif font at `clamp(13px, 1.1vw, 22px)` (~15 px at the default 1366-wide window), centred under the globe; old lines fade out over 600 ms.
  - The user's text is shown in `#5F5E5A` and fades 1.5 s after `user_final`.
  - Tauri window: `decorations: false`, black background, 900×700 by default, resizable. F11 toggles full screen; Esc hides the window, which only hides it; lifecycle owns its process.
- [ ] **Step 4: Run `npx vitest run`.** Expected: pass.
- [ ] **Step 5: Manual check.** Run `npm run tauri dev` with a small script `ui/dev/fake_backend.py` that cycles through the states and moods. Confirm:
  - the motion matches the mock (slow, no jitter);
  - fps ≥ 55 (from the devtools performance overlay);
  - the subtitles reveal word by word;
  - nothing is visible besides the globe and subtitles.
- [ ] **Step 6: Commit** `feat: tauri ui with globe and subtitles`.

### Task 14: Window on demand, end-to-end run, resource report

**Files:**
- Create: `backend/bonnington/ui_process.py`
- Modify: `backend/bonnington/lifecycle.py` (replace the UI stubs), `docs/superpowers/benchmarks.md`
- Test: `backend/tests/test_ui_process.py`

**Interfaces:**
- Consumes: the built Tauri executable at `ui/src-tauri/target/release/bonnington-ui.exe` (from `npm run tauri build`).
- Produces: `UIProcess(exe: Path, popen=subprocess.Popen)` with:
  - `show()`: starts the process if not running; a no-op if running;
  - `hide()`: terminates it, waits up to 3 s, then kills it;
  - `is_running: bool`.

- [ ] **Step 1: Write the failing tests** with a fake popen. `show()` twice should give exactly one spawn; `hide()` should terminate, then kill if the process is still alive after 3 s; `hide()` when not running should be a no-op.
- [ ] **Step 2: Run, implement, re-run.** Expected: pass. Commit `feat: ui process on demand`.
- [ ] **Step 3: End-to-end manual run** (`uv run python -m bonnington` with the release UI built):
  1. Say "Hey Britney, how are you?" The window appears, the globe shows waking → listening → thinking → speaking, the voice is the chosen one, subtitles sync, the mood tints, and the grudge count is mentioned or reacted to.
  2. Reply within 8 s without the wake word; he answers.
  3. Say "Hey Bonnington"; the mood is smug or pleased.
  4. Press the hotkey mid-reply; he stops.
  5. Stop Ollama and wake him; he shows "My brain is offline. Start Ollama."
  6. Wait 10 min; the window closes and VRAM is freed (`nvidia-smi`).
- [ ] **Step 4: Resource report.** Measure each of DORMANT, ASLEEP and AWAKE (idle and while speaking) for 2 minutes, using `Get-Process` CPU/RAM for python and the UI exe, and `nvidia-smi` for VRAM. Also measure the cold-start time from the wake word to the first audio.
  - Write a table to `benchmarks.md`, compared with the spec §7.7 estimates.
  - If DORMANT is above 3% of one core or 300 MB, flag it to the user.
- [ ] **Step 5: Ask the user** whether to register start-at-login (`python -m bonnington --register-startup`).
- [ ] **Step 6: Commit** `docs: e2e results and resource report`.

### Task 15 (optional stretch): Mood-aware delivery

**Files:**
- Modify: `backend/bonnington/tts.py`, `backend/bonnington/orchestrator.py`
- Test: `backend/tests/test_tts_mood.py`

**Interfaces:**
- Produces: `TTSEngine.synth(sentence: str, mood: Mood = "neutral") -> Utterance`.

- [ ] **Step 1: Check qwen-tts for tone/instruction control on voice-clone generation.**
  - If there is none, record "not supported" in `benchmarks.md` and stop. The mood stays colour-only.
- [ ] **Step 2: If supported:**
  - Write a test that `synth` passes a mood-specific instruction string. Use a fixed map of six short instructions, e.g. annoyed → "clipped, irritated", serious → "flat, direct". Pass `neutral` as no instruction.
  - Implement it, and have the orchestrator pass the parser's mood.
  - The user listens to one line in each of the six moods and confirms the voice identity is preserved.
- [ ] **Step 3: Commit** `feat: mood-aware delivery`.
