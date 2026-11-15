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
