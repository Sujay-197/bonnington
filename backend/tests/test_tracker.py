from datetime import date, datetime, time
from pathlib import Path

import pytest

from bonnington.vault.projects import ProjectStatus
from bonnington.vault.store import Vault
from bonnington.vault.tools import Tracker

NOW = datetime(2026, 11, 15, 23, 40)     # Sunday


def _projects():
    return [
        ProjectStatus("medrag", Path("x"), NOW, 5, "active", "Personal", "Stitch MCP integration", "feat/x"),
        ProjectStatus("tensor/campusai", Path("y"), NOW, 41, "cold", "Personal", "Campus map", "main"),
        ProjectStatus("clg/bio", Path("z"), NOW, 9, "stalled", "Academic", "PPI prediction", "master"),
    ]


@pytest.fixture
def tracker(tmp_path):
    return Tracker(Vault(tmp_path / "vault"), projects=_projects, now=lambda: NOW)


def test_tool_specs_are_valid_function_schemas(tracker):
    specs = tracker.tool_specs()
    names = [s["function"]["name"] for s in specs]
    assert names == ["add_exam", "add_assignment", "add_task", "add_score", "mark_done", "remove_item",
                     "undo_last", "list_items", "subject_summary", "project_status", "project_detail",
                     "set_project_status"]
    for s in specs:
        assert s["type"] == "function" and s["function"]["description"]
        assert s["function"]["parameters"]["type"] == "object"


def test_add_exam_resolves_spoken_date_and_reads_it_back(tracker):
    out = tracker.call("add_exam", {"subject": "DBMS", "date": "the 24th", "time": "9am", "title": "Midterm 2"})
    assert out == "Saved exam: DBMS Midterm 2 on Tuesday 24 November at 09:00."
    assert tracker.vault.exams()[0].on == date(2026, 11, 24) and tracker.vault.exams()[0].at == time(9, 0)


def test_add_task_with_and_without_due(tracker):
    assert tracker.call("add_task", {"title": "Renew passport", "due": "1 December"}) == \
        "Saved task: Renew passport, due Tuesday 1 December."
    assert tracker.call("add_task", {"title": "Call the bank"}) == "Saved task: Call the bank, no due date."


def test_add_assignment_and_score(tracker):
    assert tracker.call("add_assignment", {"subject": "CN", "title": "Lab report 3", "due": "friday"}) == \
        "Saved assignment: CN Lab report 3, due Friday 20 November."
    assert tracker.call("add_score", {"subject": "DBMS", "exam": "Midterm 1", "score": 38, "out_of": 50}) == \
        "Saved score: DBMS Midterm 1, 38 out of 50 (76%)."
    assert tracker.vault.scores()[0].on == date(2026, 11, 15)


def test_numbers_given_as_strings_are_accepted(tracker):
    assert "38 out of 50" in tracker.call("add_score", {"subject": "DBMS", "exam": "Quiz", "score": "38", "out_of": "50"})


def test_bad_date_is_an_error_message_not_a_crash(tracker):
    out = tracker.call("add_exam", {"subject": "DBMS", "date": "soonish"})
    assert out.startswith("ERROR:") and "date" in out and tracker.vault.exams() == []


def test_missing_argument_and_unknown_tool(tracker):
    assert tracker.call("add_exam", {"subject": "DBMS"}).startswith("ERROR:")
    assert tracker.call("launch_missiles", {}).startswith("ERROR: unknown tool")


def test_mark_done_remove_and_undo(tracker):
    tracker.call("add_task", {"title": "Renew passport"})
    assert tracker.call("mark_done", {"kind": "task", "which": "passport"}) == "Marked done: Renew passport."
    assert tracker.call("undo_last", {}) == "Undone: marked task done: Renew passport."
    assert tracker.call("remove_item", {"kind": "task", "which": "passport"}) == "Removed task: Renew passport."
    assert tracker.call("mark_done", {"kind": "task", "which": "nothing"}).startswith("ERROR: no task matching")
    tracker.vault._undo = None
    assert tracker.call("undo_last", {}) == "Nothing to undo."


def test_kind_accepts_plurals(tracker):
    tracker.call("add_exam", {"subject": "DBMS", "date": "24 Nov"})
    assert tracker.call("mark_done", {"kind": "exams", "which": "dbms"}).startswith("Marked done")


def test_list_items(tracker):
    assert tracker.call("list_items", {"kind": "all"}) == "Nothing recorded."
    tracker.call("add_exam", {"subject": "DBMS", "date": "24 Nov", "time": "09:00"})
    tracker.call("add_task", {"title": "Call the bank"})
    out = tracker.call("list_items", {"kind": "all"})
    assert "Exam: DBMS Exam on 2026-11-24 09:00" in out and "Task: Call the bank" in out
    assert "Call the bank" not in tracker.call("list_items", {"kind": "exams"})


def test_subject_summary(tracker):
    tracker.call("add_score", {"subject": "DBMS", "exam": "Midterm 1", "score": 38, "out_of": 50})
    assert "Average: 76%" in tracker.call("subject_summary", {"subject": "dbms"})
    assert tracker.call("subject_summary", {"subject": "Physics"}) == "Nothing recorded for Physics."


def test_project_status_and_hold(tracker):
    out = tracker.call("project_status", {})
    assert 'medrag (Personal): active, idle 5 days, last worked on "Stitch MCP integration"' in out
    assert tracker.call("set_project_status", {"project": "campusai", "status": "on hold", "note": "after exams"}) == \
        "tensor/campusai is now marked on hold."
    assert (tracker.vault.root / "Projects" / "tensor__campusai.md").exists()
    assert tracker.call("set_project_status", {"project": "nope", "status": "done"}).startswith("ERROR: no project")
    assert tracker.call("set_project_status", {"project": "medrag", "status": "exploded"}).startswith("ERROR:")


def test_snapshot_when_empty(tmp_path):
    t = Tracker(Vault(tmp_path / "v"), projects=lambda: [], now=lambda: NOW)
    snap = t.snapshot()
    assert "Today is Sunday 15 November 2026, 23:40" in snap and "Nothing recorded yet" in snap


def test_snapshot_groups_week_overdue_later_and_projects(tracker):
    tracker.call("add_exam", {"subject": "DBMS", "date": "19 Nov", "time": "09:00", "title": "Midterm 2"})
    tracker.call("add_assignment", {"subject": "CN", "title": "Lab report 3", "due": "2026-11-10"})
    tracker.call("add_task", {"title": "Renew passport", "due": "2026-12-20"})
    tracker.call("add_task", {"title": "Call the bank"})
    tracker.call("add_score", {"subject": "DBMS", "exam": "Midterm 1", "score": 38, "out_of": 50})
    snap = tracker.snapshot()
    week = snap[snap.index("Next 7 days"):snap.index("Overdue")]
    assert "Thursday 19 November (in 4 days) 09:00: Exam, DBMS: Midterm 2" in week
    overdue = snap[snap.index("Overdue"):snap.index("Later")]
    assert "CN: Lab report 3" in overdue and "5 days ago" in overdue
    assert "Renew passport" in snap[snap.index("Later"):]
    assert "Tasks with no date: Call the bank" in snap
    assert "DBMS Midterm 1 38/50 (76%)" in snap
    assert "medrag (Personal): active, idle 5 days" in snap and "tensor/campusai (Personal): cold, idle 41 days" in snap


def test_snapshot_says_no_exams_this_week_explicitly(tracker):
    tracker.call("add_task", {"title": "Call the bank"})
    assert "Next 7 days: nothing dated. No exams this week." in tracker.snapshot()


def test_project_detail_tool(tmp_path):
    from bonnington.vault.projects import ProjectDetail
    seen = []

    def detail(name):
        seen.append(name)
        return ProjectDetail(name, [("Retrieval engine", 2), ("Initial setup", 9)],
                             ["should we rly need containers>", "add the retrieval step"])
    t = Tracker(Vault(tmp_path / "v"), projects=_projects, now=lambda: NOW, detail=detail)
    out = t.call("project_detail", {"project": "campusai"})
    assert seen == ["tensor/campusai"]
    assert 'Recent sessions: "Retrieval engine" (2 days ago); "Initial setup" (9 days ago)' in out
    assert 'Last things the user asked for there: "should we rly need containers>"; "add the retrieval step"' in out
    assert t.call("project_detail", {"project": "nope"}).startswith("ERROR: no project")


def test_changes_are_announced_but_reads_and_errors_are_not(tmp_path):
    notes = []
    t = Tracker(Vault(tmp_path / "v"), projects=_projects, now=lambda: NOW)
    t.on_change = notes.append
    t.call("add_task", {"title": "Call the bank"})
    t.call("list_items", {"kind": "all"})
    t.call("add_exam", {"subject": "DBMS", "date": "soonish"})
    t.call("mark_done", {"kind": "task", "which": "bank"})
    t.call("undo_last", {})
    t.call("undo_last", {})                      # nothing left to undo
    t.call("set_project_status", {"project": "medrag", "status": "on hold"})
    assert notes == ["Saved task: Call the bank, no due date.", "Marked done: Call the bank.",
                     "Undone: marked task done: Call the bank.", "medrag is now marked on hold."]
