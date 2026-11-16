# Bonnington phase 1: whole-branch review

**Verdict:** The design holds up and the tests are green (backend 391 passed with 2 hw tests deselected, UI 42 passed). But the error paths are weak: there is one data-loss bug in the vault's undo, the claimed-save guard has a hole, and he can get stuck in a state he never leaves.
**Before daily use:** fix Critical 1 and Important 1–5. Each is a small, local change.
**Not blocking:** the Minor items. Most are tidy-ups or defence in depth.

Scope: `git diff main...bonnington-phase1` (121 files), with the backend, UI, Tauri config, scripts and tests read in full. Rulings are taken from `.superpowers/sdd/2026-11-15-bonnington-voice/progress.md`. Throwaway checks were run from the scratchpad against the real modules, using fakes, with no models and no mic. Each finding is marked CONFIRMED (seen happen in a check, or certain from the code) or PLAUSIBLE (the code path is real; the trigger depends on timing or on what the model does).

---

## Critical

### C1. Undo can delete the user's hand-written lines, or the whole file (CONFIRMED)
`backend/bonnington/vault/store.py:205-210, 276-288`

`_begin` takes a snapshot of the whole file before every change. `undo()` writes that snapshot back, or **unlinks the file** if it did not exist before the change. Nothing checks that the file is still the one Bonnington wrote, and the snapshot never expires.
- **Trigger 1 (checked):** with no `Personal/Tasks.md` yet, he adds a task, creating the file. The user then opens it in Obsidian and types three tasks of their own. Hours later they say "that's wrong", and the persona prompt tells him to call `undo_last`. Result: `Tasks.md` is deleted along with the user's lines. A scratch check reproduced the deletion exactly.
- **Trigger 2:** the same sequence with an existing file. The file goes back to its old snapshot, and every edit made since then is lost silently.
- **Fix:** with the snapshot, store the text Bonnington wrote. Undo only when the file still matches that text; otherwise apply the inverse of the one line changed (remove, re-add or un-tick it) or refuse with an ERROR. Never unlink a file holding lines Bonnington didn't write. It is also worth limiting undo to the current session.

---

## Important

### I1. The claimed-save guard turns off after *any* tool call, even a failed or read-only one (CONFIRMED)
`backend/bonnington/brain/llm.py:112`: `guard = self.tracker is not None and not tools_ran`
- **Trigger (checked with the fake Ollama):** "add my DBMS exam soonish". The model calls `add_exam(date="soonish")`, which returns `ERROR: ...`. The model's next round says "I've noted your DBMS exam." That line is spoken, and no exam exists. The same thing happens after `list_items` followed by "I've added the physics lab to your list."
- **Fix:** keep the guard on until a *changing* tool (`_CHANGES`) has returned a non-ERROR result this turn. Track `changed_ok` instead of `tools_ran`.

### I2. The redo prompts can change data the user never asked to change (prompt CONFIRMED, model reaction PLAUSIBLE)
`backend/bonnington/brain/llm.py:94-106, 252-254`
- `wants_change()` treats questions as change requests: "did I mark the bank call done?" matches `_CHANGE` (`mark`, `done`). If the model answers "Yes, I marked it done yesterday", that counts as a claim, so the redo appends `_FORCE`: "Record or change this with the matching tool now. Do not answer in words until the tool has run." A check confirmed exactly that prompt was sent. The likely result is an unrequested `mark_done` (or `undo_last`, since "wrong" is also a change word).
- The gentle redo for small talk only removes the `add_*` tools. It still offers `mark_done`, `remove_item`, `undo_last` and `set_project_status` (checked). So "you're hilarious" followed by a false "I've struck that from the record" leaves a deletion one model step away. Combined with C1, that is how data gets lost.
- **Fix:** have `wants_change` return False for questions (reuse the `?` and `_QUESTION` test from `looks_like_a_report`). In the gentle redo, offer no changing tools at all; read-only tools are enough to answer.

### I3. Any error other than `BrainUnavailable` leaves him stuck in "thinking" or "speaking" (CONFIRMED)
`backend/bonnington/orchestrator.py:295-335`; `backend/bonnington/brain/llm.py:68-75, 189`
`_reply` only catches `BrainUnavailable`. Three common errors are not converted to it:
- `ollama.ResponseError` raised *while streaming*. `ollama/_client.py:197` raises it for an error chunk, for example "model runner has unexpectedly stopped" after a VRAM out-of-memory. `_call` only wraps the initial call, and line 189 only catches httpx errors.
- `RuntimeError` from `TTSEngine.synth` when the TTS load failed. `_load` only logs that failure (line 269).
- `OSError` or `PermissionError` from a vault write inside `tracker.call`, which only catches KeyError, ValueError, NotFound and Ambiguous (`vault/tools.py:163-167`).

**Checked:** a brain that yields one sentence and then raises leaves `state == "speaking"` and `active == True`, and the task's exception is never seen. Consequences: the UI shows THINKING or RESPONDING forever. `LifecycleController` treats him as mid-conversation, so the game or call sleep (`lifecycle.py:341`) and the 10-minute unload never happen. In hotkey-first mode the mic stays open, so the Bluetooth buds stay in call quality. Only a hotkey press recovers him.
- **Fix:** in `_reply`, add an `except Exception` branch that logs, shows a short in-character error line and calls `_end_session()`. Also catch `ollama.ResponseError` around the stream loop in `stream_reply`, and catch `OSError` in `Tracker.call` as `ERROR: could not write ...`.

### I4. One exception in the frame handler kills the whole backend, without a word in the log (CONFIRMED by reading)
`backend/bonnington/orchestrator.py:115-118, 275-276`; `backend/bonnington/__main__.py:129, 147-150`
- `run()` has no `try` around `_on_frame`. Trigger: the STT load fails (a missing model folder, say). `_load` logs it, then calls `d.stt.start_turn()` on an unloaded engine. That raises inside the load task, where nothing sees it, and the state stays "listening". On the next frame, `_listen`, then `SherpaSTT.feed`, then `start_turn`, calls `None.create_stream()` and raises `AttributeError`. That ends `orch.run()`, and with it the `asyncio.gather` in `_amain`, so the backend thread is gone. The `_NemotronStream` wake model also loads lazily inside `_on_frame` (`wake.py:185-189`), so a broken wake model has the same effect.
- `main()` makes it worse. The worker is a daemon thread running `asyncio.run(...)`, and its exception goes to `threading.excepthook`, which writes to stderr. Under `pythonw` stderr goes nowhere, and `bonnington.log` gets nothing. Worse still, if `_amain` fails *before* `state["ready"].set()` (bad settings JSON, openssl missing, phone port in use), `state["ready"].wait()` blocks forever. The process hangs with no tray icon and no log.
- **Fix:** wrap each `_on_frame` call (log, then go back to idle), and skip `start_turn` in `_load` when `models_loaded()` is False. In `main()`, run the worker with a try/except that calls `log.exception` and always sets `ready`; then `ready.wait(timeout)`, and show a tray error or exit when startup failed.

### I5. Any web page in the user's browser can read the bridge: transcripts, subtitles and the whole dashboard (CONFIRMED by reading)
`backend/bonnington/bridge.py:29`: `serve(self._handle, HOST, self.port)` sets no `origins`.
Browsers let any site open `ws://127.0.0.1:8765`; WebSockets have no same-origin rule. On connect, the bridge replays its snapshot (dashboard: exams, scores, project names, the last Claude Code request shown in the focus card) and then streams every `user_partial`, `user_final` and subtitle event. A malicious or compromised page or ad script needs one line, `new WebSocket("ws://127.0.0.1:8765")`. That breaks the spec's rule that nothing leaves the machine. It is read-only, but it is a real leak.
- **Fix:** pass `origins=["http://tauri.localhost", "tauri://localhost"]` (check the exact Origin the Tauri 2 webview sends on Windows) and reject everything else. Better still, also require a per-run random token in the WS URL, handed to the UI process as a launch argument. Add a test showing that a foreign Origin is refused.

### I6. The secret filter misses common secret shapes, and the dashboard shows the latest request permanently (CONFIRMED)
`backend/bonnington/vault/projects.py:47-63`; `backend/bonnington/dashboard.py:252-261`; `backend/bonnington/vault/tools.py:84-86, 270-278`
Checked against `_clean_request`:

| Request | Result |
|---|---|
| `use AKIAIOSFODNN7EXAMPLE …` (AWS access key ID, 20 chars, under the 24 minimum) | SHOWN |
| `postgres://admin:S3cr3tPass99@db.local/app` (`:` and `@` split the token, and "pass" is not a keyword) | SHOWN |
| `… pw is Hunter2024!` | SHOWN |
| `set OPENAI=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` (`/` and `+` split base64 secrets into short pieces) | SHOWN |
| keyword cases (`secret`, `token`, …) and long `ghp_…` | hidden |

These strings then reach the screen and the voice. `_focus()` puts the newest request of the focused project on the always-open dashboard. With no project picked, the focus is the most recently active one, which is usually the session the user is in right now. The `project_detail` tool sends requests to the LLM, which may read them aloud and into subtitles; "says:" lines go to `data/bonnington.log`. Session titles (`customTitle`/`aiTitle`) and `gitBranch` skip the filter completely and go into every turn's snapshot and into the focus card.
- **Fix:** also hide URLs that carry credentials (`\w+://[^/\s:@]+:[^@\s]+@`), `AKIA[0-9A-Z]{16}`, known prefixes (`sk-`, `ghp_`, `xox`, `AIza`, `eyJ` JWTs), tokens of 20+ chars including `/+=`, and the keywords `pw`, `pwd`, `pass`, `creds`, `credential`, `passphrase`. Run titles and branches through the same filter. Consider leaving raw requests off the dashboard entirely; the session title is enough there.

### I7. Barge-in starts a stale sentence that then runs to the end (CONFIRMED by reading)
`backend/bonnington/tts.py:96-112`
The producer runs ahead of playback, so while sentence 1 plays, a worker thread waits in `synth()` for `_gen_lock` to generate sentence 2. On interrupt, `cancel()` sets `_cancel` and sentence 1 stops and releases the lock. The waiting thread then takes the lock, **clears `_cancel`** (line 105) and generates the whole of sentence 2 for nobody: cancelling the asyncio task does not stop that thread. The next reply's first `synth` waits behind it, so first audio is late by up to one sentence of synthesis, and the GPU is busy. `unload()` (line 90) has the same race: it can lose the lock to that stale synth and wait for it.
- **Fix:** give each call a generation id, or a cancel token per call. Capture the token at the time of the call (before taking the lock) and check it inside `_generate`. Or have `cancel()` bump a counter that `synth` compares after acquiring the lock, and return an empty utterance if it changed.

### I8. Closing the mic while a stream is opening leaves the mic running and buffering forever (PLAUSIBLE: timing)
`backend/bonnington/audio/source.py:268-271, 311-313, 339-340`
`close()` clears `_want_open` and drops `_stream`. If `frames()` is waiting in `await asyncio.to_thread(self._make_stream)` at that moment, it then stores the new, *started* stream. The loop sees `_want_open` cleared and goes back to `await self._want_open.wait()`, but the PortAudio callback keeps pushing 32 KB/s into the unbounded `_queue`. Triggers: the session ends or DnD is toggled during a Bluetooth profile switch (`open_grace` is 6 s), or during a stall reopen. Effects: the mic and the Windows mic-in-use indicator stay on, the buds stay in call mode, memory grows by about 115 MB an hour, and on the next `open()` the whole backlog is replayed into the wake and STT pipeline.
- **Fix:** after `_make_stream` returns, check `_want_open`; if it is clear, kill the new stream at once. Also bound the queue, for example drop anything older than 2 s.

### I9. The phone mic can be taken over from the same Wi-Fi in weeks, then used to inject commands (CONFIRMED by reading)
`backend/bonnington/audio/phone.py:104, 180-203`; `backend/bonnington/config.py:60-65`
- The 6-digit code is permanent (saved in settings, never rotated). The lockout allows 8 tries a minute, about 11,500 a day, so an attacker on the same network finds the code in about 43 days on average, or within about 87 days at worst, with a simple loop. The lockout is also global, so the same attacker can keep the real phone locked out indefinitely.
- After a correct code, `_handle` **replaces** the user's live phone connection without asking ("a newer connection replaces the old one"). The attacker can then stream audio into the conversation loop, for example "Hey Britney, remove my DBMS exam", reaching the vault tools (and, via C1, undo). Each `{"capture": …}` message also tells them when the user is talking.
- The server binds `0.0.0.0` (every interface, including VPN and any public Wi-Fi the laptop joins), and it runs even while he is asleep.
- **Fix:** bind to `lan_ip()` only. After the first correct code, issue a long random session cookie and stop accepting the bare code over WS. Rotate the code after any lockout. Don't let a new connection replace a live one without a tray or dashboard prompt. This changes the ruling at progress.md:51 (see below).

### I10. No timeout on Ollama: a hung server freezes "waking" for good (PLAUSIBLE)
`backend/bonnington/brain/llm.py:41, 68-81`; `backend/bonnington/orchestrator.py:260-264`
`ollama.AsyncClient()` has no timeout. If Ollama accepts the connection but never answers (stuck model load, GPU taken by a game), `warm()` never returns. `_load` waits on `gather` forever, so `loading` stays True and the UI shows "waking up…". While the state is "listening", a hotkey press is swallowed (`orchestrator.py:150-154`). The wake word isn't fed, and the lifecycle never sleeps him because `active` is True. Only toggling DnD or a restart recovers. This is the hung-server variant of Review Focus 1, and it isn't covered.
- **Fix:** `ollama.AsyncClient(timeout=httpx.Timeout(connect=2, read=60))`, plus `asyncio.wait_for` around `warm()` in `_load` (for example 45 s, then treat it as `BrainUnavailable`).

---

## Minor

1. **The bridge drops events while a window connects** (`bridge.py:54-58`, CONFIRMED by reading). The snapshot is sent with `await ws.send` *before* the client's queue is registered, so events broadcast during those awaits are lost: a phase change or a dashboard update, and then the UI shows a stale state. Fix: register the queue first and put the snapshot messages into it.
2. **Dashboard refreshes can land out of order** (`presenter.py:71-82`, `__main__.py:53`, PLAUSIBLE). Refreshes run in parallel threads. A slow one that started before a tool write (a project scan after the 60 s cache expires) can broadcast after the fast one, so for up to 60 s the dashboard can hide a task he has just read back. Fix: number each refresh and drop results older than the last one sent, or run refreshes one at a time.
3. **Vault writes are not atomic** (`vault/store.py:212-215, 286, 304, 312`). `write_text` truncates and then writes, so a dashboard read on a pool thread can see an empty file, and a Quit mid-write (the daemon thread is killed) can truncate it. Fix: write to a temp file and `os.replace`.
4. **`regenerate()` deletes any `.md` in `Academic/Subjects/` it didn't generate** (`vault/store.py:313-315`, CONFIRMED). A file the user writes there themselves ("My physics notes.md") goes on the next write. Fix: only delete files that contain the `GENERATED` marker.
5. **Matching items is loose** (`vault/store.py:245-247`). The query words are substrings of the item's text ("math" matches "Aftermath"), and a whitespace-only `which` matches every item, so a vault with one item has it removed (CONFIRMED). Fix: match whole words and reject an empty word list.
6. **Blocking work on the event loop** (`brain/llm.py:62, 180`; `vault/tools.py:144, 255-260`; `presenter.py:86`). `tracker.snapshot()` (every round), `tracker.call()` and `Presenter._names()` run on the loop, and a cold project cache means a scan of every `~/.claude/projects/*/*.jsonl` (up to 320 KB each). `project_detail` has no cache and re-parses every log on *every* dashboard refresh (`dashboard.py:256`). Frames queue up and UI events stall while this runs. Fix: call the tools and the snapshot through `asyncio.to_thread`, and cache `project_detail` together with the scan.
7. **Unloading while a load runs** (`orchestrator.py:134-146`, PLAUSIBLE). `go_dormant()` doesn't cancel or await `_load_task`. DnD or a game during a cold load can run `stt.unload`/`tts.unload` alongside `load`, after which the models end up loaded while he is dormant and are never unloaded, because only leaving AWAKE unloads. Fix: in `go_dormant`, await or cancel `_load_task` first.
8. **No clean shutdown on Quit** (`__main__.py:161-164`). Ollama keeps gemma loaded for `KEEP_ALIVE = "30m"` after Quit, about 8 GB of VRAM taken from the game the user is probably quitting to play. Fix: on Quit, schedule `brain.unload()` on the loop with a short timeout before the process exits.
9. **The phone certificate isn't renewed when the LAN IP changes** (`audio/phone.py:56-57`). The SAN fixes the IP at creation; after a DHCP change the phone shows a hostname mismatch warning again. The user has learned to click through that warning, which also makes a man-in-the-middle with a forged certificate easy. Fix: regenerate when the SAN IP differs, and show the certificate fingerprint on the dashboard.
10. **`local_files_only=True` is silently dropped** (`tts.py:79`). The torch path of `faster_qwen3_tts` (model.py:192) doesn't pass it on to `Qwen3TTSModel.from_pretrained`, so the flag protects nothing. No network call happens today, because the paths are local directories and transformers 4.57 skips `model_info()` for local tokenizers. Defence in depth: set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `HF_HUB_DISABLE_TELEMETRY=1` in `main()` before any import.
11. **The CSP allows inline styles, but the code assumes it blocks them** (`ui/src-tauri/tauri.conf.json`: `style-src 'self' 'unsafe-inline'`). Tauri's injected hashes may neutralise `'unsafe-inline'` (I could not verify without running the UI), but the config contradicts the comments in `cards.js` and `subtitles.js`. Drop `'unsafe-inline'`; `el.style.x = …` from JS is allowed either way.
12. **`is_farewell` false positives** (`orchestrator.py:44-56`). With five words or fewer, any listed phrase *anywhere* ends the session: "the case was dismissed", "the pain will go away", "don't say bye yet". Fix: for short sentences, require the phrase at the start or end too.
13. **The wake recogniser loads on the event loop** (`wake.py:185-189`), on the first idle frame, and is never unloaded in `go_dormant`. Load it in `_load` or in a thread.
14. **Tool calls aren't de-duplicated** (`brain/llm.py:121-123, 179`, PLAUSIBLE). If the model emits the same `add_*` call twice in one round, or again in the next round, the item is saved twice.
15. **Leftovers and dead code:**
    - `backend/scripts/live_wake.py` no longer runs: it imports `KeywordWake` and reads `kws_model_dir`, `wake_boost` and `wake_threshold`, all gone with the sherpa keyword spotter (checked by AST and import).
    - `Orchestrator.ensure_awake` (`orchestrator.py:127-132`) and `AudioPlayer.is_playing` are never used.
    - `dashboard.py:213` rebuilds `scores` for nothing.
    - `cards.js:68` returns `{…}.html` from an object literal.
    - `orchestrator.py:46` re-imports `re`.
    - The plan's file map still says `wake.py (openWakeWord)`.
    - The other scripts' `bonnington.*` imports all resolve.

---

## Test quality

- **Review Focus, checked one by one:**
  1. *Ollama offline:* covered (`test_brain_offline_shows_message`). A missing model maps `ResponseError` to `BrainUnavailable` in `_call`. **Not covered:** a mid-stream `ResponseError` (I3) and a hung server (I10).
  2. *Mood tag split across chunks:* covered (`test_mood.py`), including stripping a second tag in the brain.
  3. *Own "Britney" without headphones:* covered (`test_own_speech_britney_ignored_without_headphones`), and it holds in the code: wake isn't fed while thinking or speaking.
  4. *Double hotkey / hotkey during a cold load:* covered (`test_double_hotkey_is_one_turn`). The code consumes and drops `_pending` while listening. The hung-load case (I10) turns this protection into a trap.
  5. *Mic unplugged or changed while dormant:* **the pin is gone.** When `MicSource` was rewritten, the retry path (`source.py:332-338`, every `retry_seconds`) was left without a test: `StallingFactory` never raises on open. Add a factory that raises N times and then succeeds.
- **Important behaviour with no test:** a reply that raises anything else (I3); a claim after a failed or read-only tool (I1); undo after a hand edit, or undo of a newly created file (C1); bridge Origin checks (I5); TTS cancel while the next `synth` waits for the lock (I7); `MicSource.close()` during `_make_stream` (I8); `__main__` wiring (that `on_session_end` chains to both lifecycle and presenter, startup failure). Also no integration test drives `LifecycleController` and `Orchestrator` together (auto-sleep and unload are the untested live behaviours already listed as accepted).
- **Tests that assert on the fakes:** `test_orchestrator.py` drives time through `FakeTurn` and `FakeWake` scripts tied to frame numbers, so most of the conversation tests check the rig's script as much as the orchestrator. That is acceptable, but it is why I3 and I4 slipped through: the fakes never raise. `test_tts_stream.py` checks the lock with a fake model and never interleaves `cancel()` with a queued `synth` call.
- The secret-filter test (`test_project_detail_hides_secrets_and_trims_long_requests`) only uses keyword and long-token examples; add the shapes from the I6 table.

---

## Rulings I disagree with

- **progress.md:49/51, phone mic "token-gated … weaker secret than the long token, LAN-only".** The cost is understated. With a permanent 6-digit code, a global lockout and connection replacement, it becomes audio injection into a tool-calling agent by anyone on the Wi-Fi within weeks (I9). Keep the code for pairing, but swap it for a long cookie after the first visit.
- **progress.md:39, "sleep probes … ignored while a conversation is active".** The ruling is sound in itself, but `active` is only as good as the orchestrator's error handling. Until I3 and I10 are fixed, one failed reply turns game detection and the 10-minute unload off permanently. Add a ceiling, for example ignore `active` if `last_interaction` is more than 2 minutes old.

All other rulings read as reasonable trade-offs, including keeping tool calls in history, choosing highlights in code, the 25-frame load buffer, hotkey-first mic handling and the 1000 ms turn pause.

---

## Checked and fine

- **Bridge broadcast from other threads:** `call_soon_threadsafe` into per-client queues is correct from the PortAudio, player, pool and tray threads. One queue per client keeps order (tested).
- **TTS lock basics:** one generation at a time. The lock is always released in `_generate`'s `finally`. `first.set()` in the `finally` stops `synth()` hanging when generation fails before the first chunk. `unload()` waits for the generation in progress.
- **Player:** stop and interrupt work. The stream is always closed. Amplitude is reset to 0 in the `finally`.
- **`MicSource` stall watchdog:** based on driver time, so a busy loop is not mistaken for a stall. Open grace for Bluetooth.
- **`PhoneMicSource`:**
  - silence frames while no phone is connected, so the timeouts still work and the "not connected" hint appears;
  - audio sent while closed is dropped;
  - frames are aligned;
  - `max_size` is 1 MiB;
  - only an authorised WS can send audio;
  - the token is digits only, so it is safe inside the page's JS.
- **Lifecycle `next_level` table and debounce:** the transitions are correct and tested. DnD and hotkey overrides work. Probe failures are caught.
- **Orchestrator happy paths:** summons note only on new sessions, follow-up window with pre-roll, noise turns, goodbye handling, Britney counting without double counting, load buffer cap.
- **Brain:** history trim never starts mid-exchange; the hint and redo text stay out of history; an empty reply is retried once; the read-back after a silent save works; the tool-round cap holds.
- **Vault parsing:** unparseable or hand-written lines are kept by add, mark_done and remove (tested). Exact match breaks ties between several hits. Generated files carry a header. Project notes are written only under `vault/Projects/`.
- **`projects.py` stays read-only** on `~/.claude` and on project folders. Injected and system text is skipped (`<system-reminder>`, `<command-name>`, interrupted turns). Only head and tail are read, with `errors="replace"`.
- **UI HTML injection:** every backend string reaches the DOM through `esc()` or `escapeHtml()` or `textContent`. Numbers and class names come from backend constants. Subtitles are escaped. There are no `eval` or inline handlers. The capabilities are minimal (window controls plus `core:default`). `connect-src` is limited to `ws://127.0.0.1:*`.
- **Privacy at runtime:**
  - Ollama is on localhost.
  - sherpa-onnx is local.
  - transformers and qwen_tts load from local directories with no hub calls (`_is_local` short-circuits `model_info`).
  - `lan_ip()` only connects a UDP socket, so no packet is sent.
  - There is no telemetry or updater plugin in Tauri (`Cargo.toml` has only `tauri` and `tauri-plugin-log`).
  - The only inbound listener beyond localhost is the user-approved phone server (I9).
- **Dead wake code:** no remaining references to openWakeWord, the sherpa keyword spotter or `wake_models` in `bonnington/`, the tests or `pyproject.toml`; the only one is `scripts/live_wake.py`.
- **Test suites:** backend `391 passed, 2 deselected`; UI `42 passed`.
