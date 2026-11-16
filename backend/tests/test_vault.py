from datetime import date, time

import pytest

from bonnington.vault.store import Ambiguous, NotFound, Vault

TODAY = date(2026, 11, 15)


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "vault")


def test_add_exam_writes_a_readable_line(vault):
    vault.add_exam("DBMS", date(2026, 11, 24), time(9, 0), title="Midterm 2", note="units 3-5")
    text = (vault.root / "Academic" / "Exams.md").read_text(encoding="utf-8")
    assert "- [ ] 2026-11-24 09:00 | DBMS | Midterm 2 | units 3-5" in text
    (exam,) = vault.exams()
    assert (exam.subject, exam.on, exam.at, exam.title, exam.note, exam.done) == \
        ("DBMS", date(2026, 11, 24), time(9, 0), "Midterm 2", "units 3-5", False)


def test_exam_without_time(vault):
    vault.add_exam("CN", date(2026, 12, 1))
    assert "- [ ] 2026-12-01 | CN | Exam" in (vault.root / "Academic" / "Exams.md").read_text(encoding="utf-8")
    assert vault.exams()[0].at is None


def test_assignment_task_and_score_round_trip(vault):
    vault.add_assignment("CN", "Lab report 3", date(2026, 11, 20))
    vault.add_task("Renew passport", date(2026, 12, 1))
    vault.add_task("Call the bank")
    vault.add_score("DBMS", "Midterm 1", 38, 50, date(2026, 11, 10))
    assert vault.assignments()[0].title == "Lab report 3" and vault.assignments()[0].due == date(2026, 11, 20)
    assert [(t.title, t.due) for t in vault.tasks()] == [("Renew passport", date(2026, 12, 1)), ("Call the bank", None)]
    s = vault.scores()[0]
    assert (s.subject, s.exam, s.score, s.out_of) == ("DBMS", "Midterm 1", 38, 50)
    assert "- 2026-11-10 | DBMS | Midterm 1 | 38/50" in (vault.root / "Academic" / "Scores.md").read_text(encoding="utf-8")
    assert "- [ ] Renew passport | due 2026-12-01" in (vault.root / "Personal" / "Tasks.md").read_text(encoding="utf-8")


def test_subject_names_are_matched_to_existing_spelling(vault):
    vault.add_exam("DBMS", date(2026, 11, 24))
    vault.add_score("dbms", "Quiz", 8, 10, TODAY)
    assert vault.scores()[0].subject == "DBMS"


def test_mark_done_ticks_the_line(vault):
    vault.add_task("Renew passport")
    done = vault.mark_done("task", "passport")
    assert done.title == "Renew passport"
    assert "- [x] Renew passport" in (vault.root / "Personal" / "Tasks.md").read_text(encoding="utf-8")
    assert vault.tasks()[0].done


def test_mark_done_not_found_and_ambiguous(vault):
    vault.add_task("Email the professor")
    vault.add_task("Email the landlord")
    with pytest.raises(NotFound):
        vault.mark_done("task", "passport")
    with pytest.raises(Ambiguous) as e:
        vault.mark_done("task", "email")
    assert "professor" in str(e.value) and "landlord" in str(e.value)


def test_remove_deletes_the_line(vault):
    vault.add_exam("DBMS", date(2026, 11, 24))
    vault.add_exam("CN", date(2026, 12, 1))
    vault.remove("exam", "dbms")
    assert [e.subject for e in vault.exams()] == ["CN"]


def test_undo_restores_the_previous_state(vault):
    vault.add_task("Keep me")
    vault.add_task("Oops")
    assert "Oops" in vault.undo()
    assert [t.title for t in vault.tasks()] == ["Keep me"]
    assert vault.undo() is None            # one level only


def test_undo_of_mark_done(vault):
    vault.add_task("Renew passport")
    vault.mark_done("task", "passport")
    vault.undo()
    assert not vault.tasks()[0].done


def test_hand_edited_and_unparseable_lines_are_kept(vault):
    vault.add_task("First")
    p = vault.root / "Personal" / "Tasks.md"
    p.write_text(p.read_text(encoding="utf-8") + "some note I typed myself\n- [ ] Added by hand | due 2026-11-30\n",
                 encoding="utf-8")
    vault.add_task("Second")
    text = p.read_text(encoding="utf-8")
    assert "some note I typed myself" in text
    assert [t.title for t in vault.tasks()] == ["First", "Added by hand", "Second"]


def test_calendar_is_generated_soonest_first_and_skips_done(vault):
    vault.add_task("Renew passport", date(2026, 12, 1))
    vault.add_exam("DBMS", date(2026, 11, 24), time(9, 0))
    vault.add_assignment("CN", "Lab report 3", date(2026, 11, 20))
    vault.add_task("Old thing", date(2026, 11, 1))
    vault.mark_done("task", "old thing")
    lines = [l for l in (vault.root / "Calendar.md").read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    assert lines == [
        "- 2026-11-20 | Assignment | CN: Lab report 3",
        "- 2026-11-24 09:00 | Exam | DBMS: Exam",
        "- 2026-12-01 | Task | Renew passport",
    ]


def test_subject_gist_lists_upcoming_and_scores_with_average(vault):
    vault.add_exam("DBMS", date(2026, 11, 24), time(9, 0), title="Midterm 2")
    vault.add_score("DBMS", "Midterm 1", 38, 50, date(2026, 11, 10))
    vault.add_score("DBMS", "Quiz 1", 6, 10, date(2026, 11, 2))
    gist = (vault.root / "Academic" / "Subjects" / "DBMS.md").read_text(encoding="utf-8")
    assert "generated" in gist.lower()
    assert "Midterm 2" in gist and "2026-11-24" in gist
    assert "Midterm 1: 38/50 (76%)" in gist and "Quiz 1: 6/10 (60%)" in gist
    assert "Average: 73%" in gist           # (38+6)/(50+10)


def test_gist_file_removed_when_subject_has_nothing_left(vault):
    vault.add_exam("DBMS", date(2026, 11, 24))
    vault.remove("exam", "dbms")
    assert not (vault.root / "Academic" / "Subjects" / "DBMS.md").exists()


# --- undo never loses what the user wrote by hand ---------------------------------------------

def _tasks_file(vault):
    return vault.root / "Personal" / "Tasks.md"


def test_undo_of_the_first_add_keeps_lines_written_by_hand_since(vault):
    vault.add_task("Call the bank")                    # creates Tasks.md
    p = _tasks_file(vault)
    p.write_text(p.read_text(encoding="utf-8") + "- [ ] Hand-written task\nmy own notes\n", encoding="utf-8")
    assert "Call the bank" in vault.undo()
    text = p.read_text(encoding="utf-8")
    assert "Hand-written task" in text and "my own notes" in text and "Call the bank" not in text


def test_undo_after_a_hand_edit_takes_back_only_his_line(vault):
    vault.add_task("Old")
    vault.add_task("Oops")
    p = _tasks_file(vault)
    p.write_text(p.read_text(encoding="utf-8") + "- [ ] Typed in Obsidian\n", encoding="utf-8")
    vault.undo()
    assert [t.title for t in vault.tasks()] == ["Old", "Typed in Obsidian"]


def test_undo_of_mark_done_after_a_hand_edit(vault):
    vault.add_task("Renew passport")
    vault.mark_done("task", "passport")
    p = _tasks_file(vault)
    p.write_text("# My own heading\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    vault.undo()
    assert not vault.tasks()[0].done
    assert p.read_text(encoding="utf-8").startswith("# My own heading\n")


def test_undo_of_remove_after_a_hand_edit_puts_the_line_back(vault):
    vault.add_task("Keep")
    vault.add_task("Gone")
    vault.remove("task", "gone")
    p = _tasks_file(vault)
    p.write_text(p.read_text(encoding="utf-8") + "- [ ] New by hand\n", encoding="utf-8")
    vault.undo()
    assert sorted(t.title for t in vault.tasks()) == ["Gone", "Keep", "New by hand"]


def test_undo_refuses_when_his_line_was_already_changed_by_hand(vault):
    from bonnington.vault.store import UndoConflict
    vault.add_task("Call the bank")
    p = _tasks_file(vault)
    edited = p.read_text(encoding="utf-8").replace("Call the bank", "Call the bank at 9")
    p.write_text(edited, encoding="utf-8")
    with pytest.raises(UndoConflict):
        vault.undo()
    assert p.read_text(encoding="utf-8") == edited     # nothing touched
