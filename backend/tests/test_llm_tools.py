from datetime import date, datetime

import pytest

from bonnington.brain.llm import Brain
from bonnington.brain.persona import build_system_prompt
from bonnington.vault.store import Vault
from bonnington.vault.tools import Tracker

NOW = datetime(2026, 11, 15, 23, 40)


@pytest.fixture
def tracker(tmp_path):
    return Tracker(Vault(tmp_path / "vault"), projects=lambda: [], now=lambda: NOW)


async def _say(brain, text):
    return "".join([c async for c in brain.stream_reply(text)])


async def test_snapshot_and_tools_are_sent_to_the_model(fake_ollama, tracker):
    tracker.call("add_task", {"title": "Call the bank"})
    fake_ollama.turns = [["<mood:neutral>Noted."]]
    await _say(Brain("m", client=fake_ollama, tracker=tracker), "what's left?")
    call = fake_ollama.calls[-1]
    system = call["messages"][0]["content"]
    assert "TRACKER DATA" in system and "Call the bank" in system and "Today is Sunday 15 November 2026" in system
    assert [t["function"]["name"] for t in call["tools"]][:2] == ["add_exam", "add_assignment"]


async def test_tool_call_is_executed_and_result_fed_back(fake_ollama, tracker):
    fake_ollama.turns = [
        [{"tool": "add_exam", "args": {"subject": "DBMS", "date": "the 24th", "time": "9am"}}],
        ["<mood:smug>Filed. ", "DBMS, Tuesday the 24th, nine a.m."],
    ]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "I have a DBMS exam on the 24th at nine")
    assert out == "<mood:smug>Filed. DBMS, Tuesday the 24th, nine a.m."
    assert tracker.vault.exams()[0].on == date(2026, 11, 24)
    second = fake_ollama.calls[-1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["function"]["name"] == "add_exam"
    assert second[-1]["role"] == "tool" and second[-1]["content"].startswith("Saved exam: DBMS Exam on Tuesday 24 November")
    assert "Tuesday 24 November" in fake_ollama.calls[-1]["messages"][0]["content"]   # snapshot refreshed


async def test_history_keeps_the_tool_call_and_its_result(fake_ollama, tracker):
    fake_ollama.turns = [[{"tool": "add_task", "args": {"title": "Call the bank"}}], ["<mood:neutral>Done."]]
    b = Brain("m", client=fake_ollama, tracker=tracker)
    await _say(b, "remind me to call the bank")
    assert [m["role"] for m in b.history] == ["user", "assistant", "tool", "assistant"]
    assert b.history[1]["tool_calls"][0]["function"]["name"] == "add_task"
    assert b.history[2]["content"].startswith("Saved task: Call the bank")
    assert b.history[3] == {"role": "assistant", "content": "<mood:neutral>Done."}


async def test_tool_errors_go_back_to_the_model_not_the_user(fake_ollama, tracker):
    fake_ollama.turns = [[{"tool": "add_exam", "args": {"subject": "DBMS", "date": "soonish"}}],
                         ["<mood:annoyed>Soonish is not a date. When?"]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "exam soonish")
    assert "ERROR" not in out
    assert fake_ollama.calls[-1]["messages"][-1]["content"].startswith("ERROR:")


async def test_second_mood_tag_after_spoken_text_is_dropped(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:neutral>One moment. ", {"tool": "add_task", "args": {"title": "X"}}],
                         ["<mood:smug>", "Filed."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "add x")
    assert out == "<mood:neutral>One moment. Filed."


async def test_runaway_tool_loop_is_stopped(fake_ollama, tracker):
    fake_ollama.turns = [[{"tool": "undo_last"}] for _ in range(10)] + [["never reached"]]
    await _say(Brain("m", client=fake_ollama, tracker=tracker), "loop")
    assert len([c for c in fake_ollama.calls if c.get("stream")]) == 5
    assert "tools" not in fake_ollama.calls[-1]            # last round: must answer in words


async def test_without_tracker_no_tools_are_sent(fake_ollama):
    fake_ollama.script = ["<mood:neutral>Hm."]
    await _say(Brain("m", client=fake_ollama), "hey")
    assert "tools" not in fake_ollama.calls[-1] and "TRACKER DATA" not in fake_ollama.calls[-1]["messages"][0]["content"]


def test_persona_with_tracker_is_a_tracker_not_a_tutor():
    p = build_system_prompt(tracker=True)
    for must in ["TRACKER DATA", "not a study companion", "read back", "undo_last", "Never invent"]:
        assert must in p
    assert "no access to their calendar" not in p
    assert "no access to their calendar" in build_system_prompt()


async def test_claiming_to_save_without_a_tool_call_is_caught_and_redone(fake_ollama, tracker):
    fake_ollama.turns = [
        ["<mood:neutral>I have recorded ", "your CN lab report as due Friday."],          # a lie: no tool call
        [{"tool": "add_assignment", "args": {"subject": "CN", "title": "Lab report 3", "due": "friday"}}],
        ["<mood:neutral>Filed. CN lab report three, Friday the 20th."],
    ]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "CN lab report three is due this Friday")
    assert out == "<mood:neutral>Filed. CN lab report three, Friday the 20th."
    assert tracker.vault.assignments()[0].title == "Lab report 3"
    redo = fake_ollama.calls[1]["messages"]
    assert redo[-1]["role"] == "user" and redo[-1]["content"].startswith("CN lab report three is due this Friday")
    assert "matching tool now" in redo[-1]["content"]
    assert not any("I have recorded" in m["content"] for m in redo)        # the false claim is not fed back
    assert fake_ollama.calls[1]["options"]["num_predict"] == 400


async def test_ordinary_replies_are_not_held_back_or_retried(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:amused>You have no exams this week. ", "Enjoy it while it lasts."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "what's left?")
    assert out == "<mood:amused>You have no exams this week. Enjoy it while it lasts."
    assert len([c for c in fake_ollama.calls if c.get("stream")]) == 1


async def test_claim_followed_by_a_real_tool_call_is_fine(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:neutral>I have noted that. ", {"tool": "add_task", "args": {"title": "X"}}],
                         ["<mood:neutral>Task X, no date."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "add x")
    assert out == "<mood:neutral>Task X, no date."      # the premature claim is dropped; the real read-back stays
    assert len([c for c in fake_ollama.calls if c.get("stream")]) == 2


async def test_a_second_false_claim_is_replaced_by_an_honest_line(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:neutral>I have marked it done."], ["<mood:neutral>I have marked it done, truly."],
                         ["never reached"]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "I renewed the passport")
    assert out == "<mood:serious>I did not manage to save that. Tell me again, plainly."
    assert len([c for c in fake_ollama.calls if c.get("stream")]) == 2


async def test_claim_guard_is_off_without_a_tracker(fake_ollama):
    fake_ollama.script = ["<mood:neutral>I have noted your disdain."]
    await _say(Brain("m", client=fake_ollama), "hey")
    assert len([c for c in fake_ollama.calls if c.get("stream")]) == 1


async def test_witty_opening_then_false_claim_keeps_the_wit_and_redoes_the_save(fake_ollama, tracker):
    fake_ollama.turns = [
        ["<mood:neutral>A bureaucratic necessity, I see. ", "I've noted your quest ", "to renew your passport."],
        [{"tool": "add_task", "args": {"title": "Renew passport", "due": "1 December"}}],
        ["<mood:neutral>Passport, due Tuesday the first of December."],
    ]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "add a task, renew my passport by first of December")
    assert out == "<mood:neutral>A bureaucratic necessity, I see. Passport, due Tuesday the first of December."
    assert tracker.vault.tasks()[0].title == "Renew passport"


async def test_sentences_keep_their_spacing_when_released_one_by_one(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:amused>No ex", "ams. None at all!  ", "Enjoy", " it."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "what's left?")
    assert out == "<mood:amused>No exams. None at all!  Enjoy it."


@pytest.mark.parametrize("text,claim", [
    ("I've noted your quest to renew your passport.", True),
    ("I have marked your passport renewal as completed.", True),
    ("Your passport renewal is noted for the first of December.", True),
    ("I shall have it filed.", True),
    ("I shall mark that task as finished.", True),
    ("I'll note that down.", True),
    ("I've etched that into the record.", True),
    ("I've officially shelved campusai.", True),
    ("The exam has been recorded.", True),
    ("I shall be watching.", False),
    ("I will say this once.", False),
    ("I've wiped that score from the record.", True),
    ("There are no exams scheduled for this week.", False),
    ("You have removed all doubt about your work ethic.", False),
    ("Medrag has not been updated in five days.", False),
    ("You scored 38 out of 50, noted failure that you are.", False),
])
def test_claim_detection(text, claim):
    from bonnington.brain.llm import _claims_a_save
    assert _claims_a_save(text) is claim


async def test_stray_closing_tag_after_a_tool_call_is_not_spoken(fake_ollama, tracker):
    fake_ollama.turns = [[{"tool": "add_task", "args": {"title": "X"}}], ["</", "<mood:smug>Filed."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "add x")
    assert "</" not in out and out.endswith("Filed.")


async def test_history_keeps_the_users_own_words_after_a_redo(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:neutral>I have recorded it."],
                         [{"tool": "add_task", "args": {"title": "X"}}], ["<mood:neutral>Task X."]]
    b = Brain("m", client=fake_ollama, tracker=tracker)
    await _say(b, "add x")
    assert b.history[0] == {"role": "user", "content": "add x"}


async def test_a_redo_that_says_nothing_gets_the_honest_line(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:neutral>I have recorded it."], [], ["never reached"]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "CN lab due friday")
    assert out == "<mood:serious>I did not manage to save that. Tell me again, plainly."


async def test_trailing_stray_tag_is_not_spoken(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:smug>You managed it. ", "Remarkable.", "</"]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "hello")
    assert out == "<mood:smug>You managed it. Remarkable."


def test_history_trim_never_starts_mid_exchange(fake_ollama, tracker):
    b = Brain("m", client=fake_ollama, tracker=tracker)
    for i in range(9):
        b.history += [{"role": "user", "content": f"u{i}"},
                      {"role": "assistant", "content": "", "tool_calls": []},
                      {"role": "tool", "content": "ok"},
                      {"role": "assistant", "content": f"a{i}"}]
    b._trim()
    assert len(b.history) <= 20 and b.history[0]["role"] == "user" and b.history[-1]["content"] == "a8"


@pytest.mark.parametrize("text,expected", [
    ("So tomorrow I have an exam in mathematics for uh", True),
    ("CN lab report three is due this Friday.", True),
    ("I scored 38 out of 50 in the DBMS midterm one.", True),
    ("Remind me to renew my passport by first of December", True),
    ("add this to my schedule, I have a quiz on the 24th", True),
    ("I got 16 marks in the CN quiz", True),
    ("When is my next exam?", False),
    ("What's left for this week?", False),
    ("Do I have any assignment due tomorrow", False),
    ("how did I do in the DBMS exam", False),
    ("How are you doing", False),
    ("Explain what a B plus tree is.", False),
    ("I hate exams", False),
])
def test_looks_like_a_report(text, expected):
    from bonnington.brain.llm import looks_like_a_report
    assert looks_like_a_report(text) is expected


async def test_a_report_gets_a_record_it_hint_that_is_not_kept_in_history(fake_ollama, tracker):
    fake_ollama.turns = [[{"tool": "add_exam", "args": {"subject": "Mathematics", "date": "tomorrow"}}],
                         ["<mood:neutral>Mathematics, tomorrow."]]
    b = Brain("m", client=fake_ollama, tracker=tracker)
    await _say(b, "So tomorrow I have an exam in mathematics for uh")
    first = fake_ollama.calls[0]["messages"][-1]
    assert first["role"] == "user" and first["content"].startswith("So tomorrow I have an exam")
    assert "Record it now" in first["content"]
    assert b.history[0] == {"role": "user", "content": "So tomorrow I have an exam in mathematics for uh"}


async def test_a_question_gets_no_hint(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:neutral>Tuesday."]]
    await _say(Brain("m", client=fake_ollama, tracker=tracker), "When is my next exam?")
    assert fake_ollama.calls[0]["messages"][-1]["content"] == "When is my next exam?"


async def test_an_empty_reply_is_retried_once(fake_ollama, tracker):
    fake_ollama.turns = [[], ["<mood:neutral>Here I am."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "How are you doing")
    assert out == "<mood:neutral>Here I am."


async def test_two_empty_replies_give_a_spoken_fallback(fake_ollama, tracker):
    fake_ollama.turns = [[], [], ["never reached"]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "How are you doing")
    assert out == "<mood:neutral>Say that again."
    assert len([c for c in fake_ollama.calls if c.get("stream")]) == 2


async def test_saving_then_saying_nothing_reads_the_result_back(fake_ollama, tracker):
    fake_ollama.turns = [[{"tool": "add_task", "args": {"title": "Call the bank"}}], []]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "remind me to call the bank")
    assert out == "<mood:neutral>Saved task: Call the bank, no due date."


@pytest.mark.parametrize("text", [
    "Just ensure that when the paper is placed before you tomorrow, your theory translates into something.",
    "Both Calculus and Statistics are scheduled for tomorrow.",
    "Your books are put away, I assume.",
])
def test_descriptions_are_not_save_claims(text):
    from bonnington.brain.llm import _claims_a_save
    assert _claims_a_save(text) is False


@pytest.mark.parametrize("text,expected", [
    ("Britney, that was not a task. Remove that.", True),
    ("I renewed the passport, mark it done", True),
    ("put campusai on hold", True),
    ("that's wrong, undo it", True),
    ("So tomorrow I have an exam in mathematics", True),
    ("I said of course mate theory is what gets you places.", False),
    ("What I think is more important, calculus or statistics.", False),
    ("how are you", False),
])
def test_wants_change(text, expected):
    from bonnington.brain.llm import wants_change
    assert wants_change(text) is expected


async def test_a_false_claim_in_small_talk_is_redone_gently_and_cannot_add_things(fake_ollama, tracker):
    fake_ollama.turns = [["<mood:amused>Theory, is it? ", "I have noted your philosophy."],
                         ["<mood:amused>Theory is a fine thing to hide behind."]]
    out = await _say(Brain("m", client=fake_ollama, tracker=tracker), "theory is what gets you places")
    assert out == "<mood:amused>Theory, is it? Theory is a fine thing to hide behind."
    redo = fake_ollama.calls[1]
    assert "Nothing was changed" in redo["messages"][-1]["content"]
    assert "matching tool now" not in redo["messages"][-1]["content"]
    names = [t["function"]["name"] for t in redo["tools"]]
    assert not any(n.startswith("add_") for n in names) and "mark_done" in names
    assert tracker.vault.tasks() == []
