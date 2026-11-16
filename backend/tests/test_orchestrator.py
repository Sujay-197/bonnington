from bonnington.brain.llm import BrainUnavailable


async def test_full_turn_emits_expected_events(rig):
    rig.wake_on_frame(0, "britney")
    rig.speech(frames=range(2, 10))
    rig.stt_final("what's left")
    rig.brain_says("<mood:annoyed>Britney. Again.")
    await rig.run_until_idle()
    types = rig.event_types()
    assert types.index("state:listening") < types.index("user_final") < types.index("state:thinking")
    assert "mood:annoyed" in types and rig.subtitles() == ["Britney.", "Again."]
    assert rig.spoken() == ["Britney.", "Again."] and "<mood" not in "".join(rig.spoken())
    assert types[-1] == "state:idle"


async def test_first_message_carries_summons_note_only_once(rig):
    rig.two_turns_in_followup()
    await rig.run_until_idle()
    assert rig.brain_inputs[0].startswith("[Summoned via") and rig.brain_inputs[0].endswith("first")
    assert rig.brain_inputs[1] == "second"


async def test_double_hotkey_is_one_turn(rig):
    rig.orch.trigger("hotkey")
    rig.orch.trigger("hotkey")
    await rig.run_until_idle()
    assert rig.store.summons_count() == 1 and rig.brain_calls == 1


async def test_own_speech_britney_ignored_without_headphones(rig):
    rig.settings.headphones_mode = False
    rig.wake_on_frame(0, "britney")
    rig.during_speaking_wake("britney")
    await rig.run_until_idle()
    assert rig.store.britney_count() == 1 and rig.player.stops == 0


async def test_wake_interrupts_with_headphones(rig):
    rig.settings.headphones_mode = True
    rig.brain_says("<mood:smug>One. Two. Three. Four.")
    rig.wake_on_frame(0, "britney")
    rig.during_speaking_wake("bonnington")
    await rig.run_until_idle()
    assert rig.player.stops == 1 and "clear_subtitles" in rig.event_types()
    assert rig.brain_calls == 2


async def test_hotkey_interrupts_without_headphones(rig):
    rig.brain_says("<mood:smug>One. Two. Three. Four.")
    rig.wake_on_frame(0, "britney")

    def fire_when_speaking(orig=rig.player.play):
        async def play(u):
            if u.text == "Two.":
                rig.orch.trigger("hotkey")
            return await orig(u)
        return play
    rig.player.play = fire_when_speaking()
    await rig.run_until_idle()
    assert rig.player.stops == 1 and "Four." not in rig.spoken()


async def test_followup_window_allows_reply_without_wake(rig):
    rig.reply_then_speech_after(seconds=5.0)
    await rig.run_until_idle()
    assert rig.brain_calls == 2


async def test_followup_expires(rig):
    rig.reply_then_speech_after(seconds=9.0)
    await rig.run_until_idle()
    assert rig.brain_calls == 1


async def test_brain_offline_shows_message(rig):
    rig.brain_raises(BrainUnavailable("down"))
    rig.wake_on_frame(0, "britney")
    rig.speech(frames=range(2, 6))
    rig.stt_final("hi")
    await rig.run_until_idle()
    assert "My brain is offline. Start Ollama." in rig.subtitles()
    assert "mood:serious" in rig.event_types() and rig.spoken() == []
    assert rig.orch.state == "idle"


async def test_partials_streamed_to_ui(rig):
    rig.wake_on_frame(0, "britney")
    rig.speech(frames=range(2, 6))
    rig.stt_partials(["what", "what's left"])
    rig.stt_final("what's left")
    await rig.run_until_idle()
    assert rig.user_partials() == ["what", "what's left"]


async def test_slow_cold_start_plays_hm_once(rig):
    rig.load_takes(seconds=5.0)
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    assert rig.played_files() == ["data/voice/hm.wav"]
    assert "state:waking" in rig.event_types() and rig.brain_calls == 1


async def test_fast_cold_start_plays_no_hm(rig):
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    assert rig.played_files() == []


async def test_empty_transcript_skips_brain(rig):
    rig.wake_on_frame(0, "britney")
    rig.speech(frames=range(2, 6))
    rig.turn.turns.append((500, 4))   # nothing else is said
    rig.stt_final("  ")
    await rig.run_until_idle()
    assert rig.brain_calls == 0 and rig.orch.state == "idle"


async def test_silence_after_wake_returns_to_idle(rig):
    rig.wake_on_frame(0, "britney")
    rig.turn.turns.append((500, 4))   # never speaks within the window
    await rig.run_until_idle()
    assert rig.brain_calls == 0 and rig.orch.state == "idle"


async def test_go_dormant_unloads_everything(rig):
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    await rig.orch.go_dormant()
    assert not rig.stt.is_loaded and not rig.tts.is_loaded and rig.brain.unloaded


async def test_session_end_hook_fires(rig):
    ended = []
    rig.orch.on_session_end = lambda: ended.append(True)
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    assert ended == [True]


async def test_active_while_trigger_pending(rig):
    assert rig.orch.active is False
    rig.orch.trigger("hotkey")
    assert rig.orch.active is True


async def test_logs_states_and_transcript(rig, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="bonnington.orchestrator")
    rig.wake_on_frame(0, "britney")
    rig.stt_final("what's left")
    await rig.run_until_idle()
    text = caplog.text
    assert "state -> listening" in text and "heard: what's left" in text


async def test_noise_turn_keeps_listening_for_real_speech(rig):
    rig.wake_on_frame(0, "britney")
    rig.turn.turns.extend([(0, 3), (5, 4)])     # a noise blip, then you actually speak
    rig.stt_final("")
    rig.stt_final("how are you doing")
    await rig.run_until_idle()
    assert rig.brain_calls == 1 and rig.brain_inputs[0].endswith("how are you doing")


async def test_load_buffer_is_capped_to_two_seconds(rig):
    from bonnington.orchestrator import MAX_BUFFER_FRAMES
    assert MAX_BUFFER_FRAMES == 25


async def test_followup_replays_preroll_into_stt(rig):
    fed = []
    orig_start = rig.stt.start_turn
    rig.stt.start_turn = lambda: (fed.append("start"), orig_start())[1]
    orig_feed = rig.stt.feed
    rig.stt.feed = lambda f: (fed.append("f"), orig_feed(f))[1]
    rig.reply_then_speech_after(seconds=2.0)
    await rig.run_until_idle()
    second = fed[len(fed) - 1 - fed[::-1].index("start"):]
    # 4 speech frames + the 6 frames (0.5 s) heard just before speech was detected
    assert second.count("f") >= 4 + 6


async def test_followup_window_shows_listening_phase(rig):
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    types = rig.event_types()
    last_speaking = len(types) - 1 - types[::-1].index("state:speaking")
    assert types[last_speaking + 1:].count("state:listening") == 1 and types[-1] == "state:idle"


async def test_names_normalised_in_what_he_hears(rig):
    rig.wake_on_frame(0, "britney")
    rig.stt_final("Hello Mornington how are you")
    await rig.run_until_idle()
    assert rig.brain_inputs[0].endswith("Hello Bonnington how are you")


async def test_summon_shows_hint_when_mic_source_has_a_problem(rig):
    rig.orch.d.source.status_hint = lambda: "Phone mic not connected. Open https://x on your phone."
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    assert "Phone mic not connected. Open https://x on your phone." in rig.subtitles()


async def test_no_hint_when_mic_source_is_fine(rig):
    rig.orch.d.source.status_hint = lambda: None
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    assert not any("not connected" in s for s in rig.subtitles())


async def test_goodbye_ends_the_conversation_without_a_followup_window(rig):
    rig.wake_on_frame(0, "britney")
    rig.turn.turns.extend([(0, 4), (20, 4)])            # says goodbye, then keeps talking to someone else
    rig.stt.finals.extend(["Alright then, that's it for today. Bye-bye.", "why are you still lingering"])
    await rig.run_until_idle()
    assert rig.brain_calls == 1
    assert "parting line" in rig.brain_inputs[0]
    types = rig.event_types()
    last_speaking = len(types) - 1 - types[::-1].index("state:speaking")
    assert [t for t in types[last_speaking + 1:] if t.startswith("state:")] == ["state:idle"]


async def test_ordinary_turn_still_gets_a_followup_window(rig):
    rig.wake_on_frame(0, "britney")
    rig.turn.turns.extend([(0, 4), (20, 4)])
    rig.stt.finals.extend(["that's it, the exam is on the 24th", "and one more thing"])
    await rig.run_until_idle()
    assert rig.brain_calls == 2


async def test_presenter_hooks_fire_with_user_text_and_full_reply(rig):
    heard, replies = [], []
    rig.orch.on_user_text = heard.append
    rig.orch.on_reply_done = replies.append
    rig.wake_on_frame(0, "britney")
    rig.stt_final("what's left this week")
    rig.brain_says("<mood:smug>One exam. Nine days.")
    await rig.run_until_idle()
    assert heard == ["what's left this week"]
    assert replies == ["One exam. Nine days."]


async def test_britney_said_in_conversation_is_counted_and_he_is_told(rig):
    rig.orch.trigger("hotkey")
    rig.stt_final("Okay so Brittany, this is what it's about")
    await rig.run_until_idle()
    assert rig.store.britney_count() == 1
    assert "[They just called you Britney. Britney count is now 1.]" in rig.brain_inputs[0]


async def test_hey_britney_summons_is_not_double_counted(rig):
    rig.wake_on_frame(0, "britney")
    rig.stt_final("hey Britney what's left")
    await rig.run_until_idle()
    assert rig.store.britney_count() == 2      # once for the summons, once for saying it again


async def test_models_changed_hook_fires_on_load_and_unload(rig):
    seen = []
    rig.orch.on_models_changed = lambda: seen.append(rig.orch.models_loaded())
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    await rig.orch.go_dormant()
    assert seen == [True, False]


# --- errors end the turn instead of leaving him stuck ------------------------------------------

async def test_an_unexpected_brain_error_ends_the_session_with_a_line(rig):
    rig.brain_raises(RuntimeError("model runner has unexpectedly stopped"))
    rig.wake_on_frame(0, "britney")
    rig.speech(frames=range(2, 6))
    rig.stt_final("hi")
    await rig.run_until_idle()
    from bonnington.orchestrator import ERROR_TEXT
    assert ERROR_TEXT in rig.subtitles()
    assert rig.orch.state == "idle" and not rig.orch.active


async def test_a_failed_speech_model_load_ends_the_session_and_keeps_running(rig):
    def broken():
        raise FileNotFoundError("no encoder model")
    rig.stt.load = broken
    rig.wake_on_frame(0, "britney")
    await rig.run_until_idle()
    from bonnington.orchestrator import LOAD_FAILED_TEXT
    assert LOAD_FAILED_TEXT in rig.subtitles()
    assert rig.orch.state == "idle" and rig.brain_calls == 0


async def test_an_error_while_handling_a_frame_does_not_stop_the_loop(rig):
    feed = rig.wake.feed

    def flaky(frame):
        if rig.frames == 0:
            raise RuntimeError("wake model hiccup")
        return feed(frame)
    rig.wake.feed = flaky
    rig.wake_on_frame(3, "britney")
    rig.speech(frames=range(5, 9))
    rig.stt_final("hi")
    await rig.run_until_idle()
    assert rig.brain_calls == 1
