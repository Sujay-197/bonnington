from datetime import date, datetime, time
from pathlib import Path

import pytest

from bonnington.dashboard import build_dashboard, when_label
from bonnington.vault.projects import ProjectDetail, ProjectStatus
from bonnington.vault.store import Vault
from bonnington.vault.tools import Tracker

NOW = datetime(2026, 11, 15, 23, 40)     # Sunday
TODAY = NOW.date()


def _projects():
    return [
        ProjectStatus("das_v0", Path("a"), NOW, 0, "active", "Personal", "Init thought process", "main"),
        ProjectStatus("tensor/campusai", Path("b"), NOW, 0, "active", "Personal", "LAN port", "feat/map"),
        ProjectStatus("medrag", Path("c"), NOW, 5, "active", "Personal", "Stitch MCP integration", "feat/x"),
        ProjectStatus("truco", Path("d"), NOW, 12, "stalled", "Personal", "Planning", "main"),
        ProjectStatus("old", Path("e"), NOW, 60, "cold", "Personal", "", ""),
        ProjectStatus("clg/bio", Path("f"), NOW, 9, "done", "Academic", "PPI", "master"),
        ProjectStatus("clg/x", Path("g"), NOW, 2, "on hold", "Academic", "", "", "after exams"),
    ]


@pytest.fixture
def tracker(tmp_path):
    def detail(name):
        return ProjectDetail(name, [("Stitch MCP integration", 5), ("v0 and v1", 6)], ["should we rly need containers>"])
    return Tracker(Vault(tmp_path / "vault"), projects=_projects, now=lambda: NOW, detail=detail)


@pytest.mark.parametrize("d,expected", [
    (date(2026, 11, 15), "TODAY"),
    (date(2026, 11, 16), "TOMORROW"),
    (date(2026, 11, 20), "FRI · 5D"),
    (date(2026, 11, 24), "TUE 24 · 9D"),
    (date(2026, 11, 12), "3D LATE"),
    (date(2026, 11, 14), "1D LATE"),
])
def test_when_label(d, expected):
    assert when_label(d, TODAY) == expected


def test_empty_vault(tracker):
    d = build_dashboard(tracker, britney_count=3)
    assert d["date"] == "SUN 15 NOV" and d["time"] == "23:40" and d["britney"] == 3
    assert d["week"] == [] and d["next"] is None
    assert d["counts"] == {"exams": 0, "tasks": 0, "late": 0}
    assert d["scores"] == []


def test_week_counts_next_and_scores(tracker):
    v = tracker.vault
    v.add_exam("DBMS", date(2026, 11, 24), time(9, 0), title="Midterm 2")
    v.add_assignment("CN", "Lab report 3", date(2026, 11, 20))
    v.add_assignment("Bio", "Assignment 2", date(2026, 11, 12))
    v.add_task("Renew passport", date(2026, 12, 1))
    v.add_task("Call the bank")
    v.add_score("DBMS", "Midterm 1", 38, 50, date(2026, 11, 10))
    v.add_score("DBMS", "Quiz", 6, 10, date(2026, 11, 2))
    v.add_score("CN", "Quiz", 16, 25, date(2026, 11, 5))
    d = build_dashboard(tracker)
    assert d["week"] == [
        {"text": "Bio: Assignment 2", "when": "3D LATE", "tone": "late"},
        {"text": "CN: Lab report 3", "when": "FRI · 5D", "tone": "soon"},
    ]
    assert d["later"] == [
        {"text": "DBMS: Midterm 2 09:00", "when": "TUE 24 · 9D", "tone": "normal"},
        {"text": "Renew passport", "when": "TUE 1 · 16D", "tone": "normal"},
    ]
    assert d["counts"] == {"exams": 1, "tasks": 2, "late": 1}
    assert d["next"] == {"text": "CN: Lab report 3", "when": "IN 5 DAYS"}
    assert d["scores"] == [{"subject": "DBMS", "percent": 73, "count": 2}, {"subject": "CN", "percent": 64, "count": 1}]
    assert d["status"]["left"] == "VAULT 4 DATED · 2 TASKS · 3 SCORES"


def test_projects_are_grouped_and_idle_ones_listed(tracker):
    p = build_dashboard(tracker)["projects"]
    assert (p["live"], p["idle"], p["done"], p["hold"]) == (2, 3, 1, 1)
    assert p["rows"] == [
        {"name": "medrag", "note": "5D IDLE", "tone": "soon"},
        {"name": "truco", "note": "12D IDLE", "tone": "soon"},
        {"name": "old", "note": "60D IDLE", "tone": "late"},
        {"name": "clg/x", "note": "ON HOLD", "tone": "muted"},
    ]


def test_default_focus_is_the_most_recent_project(tracker):
    f = build_dashboard(tracker)["focus"]
    assert f["name"] == "das_v0"
    assert f["rows"][0] == ["main", "TODAY"]


def test_focus_on_a_named_project_uses_its_detail(tracker):
    f = build_dashboard(tracker, focus_project="medrag")["focus"]
    assert f["name"] == "medrag"
    assert f["rows"] == [["feat/x", "5D IDLE"], ["Stitch MCP integration", "5D AGO"], ["v0 and v1", "6D AGO"],
                         ['"should we rly need containers>"', ""]]


def test_status_line_uses_what_it_is_given(tracker):
    d = build_dashboard(tracker, mic="phone", models_loaded=True)
    assert d["status"]["right"] == "MIC PHONE · MODELS LOADED"
    assert build_dashboard(tracker, mic="device", models_loaded=False)["status"]["right"] == "MIC DEVICE · MODELS ASLEEP"


def test_a_broken_project_scan_does_not_break_the_dashboard(tmp_path):
    def boom():
        raise OSError("log unreadable")
    t = Tracker(Vault(tmp_path / "v"), projects=boom, now=lambda: NOW)
    d = build_dashboard(t)
    assert d["projects"]["rows"] == [] and d["focus"] is None


def test_open_tasks_are_listed_dated_first(tracker):
    v = tracker.vault
    v.add_task("Call the bank")
    v.add_task("Renew passport", date(2026, 12, 1))
    v.add_task("Old chore", date(2026, 11, 10))
    v.add_task("Finished thing")
    v.mark_done("task", "finished thing")
    d = build_dashboard(tracker)
    assert d["tasks"] == [
        {"text": "Old chore", "when": "5D LATE", "tone": "late"},
        {"text": "Renew passport", "when": "TUE 1 · 16D", "tone": "normal"},
        {"text": "Call the bank", "when": "", "tone": "normal"},
    ]


def test_month_grid_marks_today_exams_and_deadlines(tracker):
    v = tracker.vault
    v.add_exam("DBMS", date(2026, 11, 24))
    v.add_assignment("CN", "Lab report 3", date(2026, 11, 20))
    v.add_task("Renew passport", date(2026, 12, 1))          # next month: not on this grid
    v.add_exam("Old", date(2026, 11, 3))
    v.mark_done("exam", "old")                                # done: not marked
    m = build_dashboard(tracker)["month"]
    assert m["label"] == "NOVEMBER" and m["offset"] == 6      # 1 Nov 2026 is a Sunday; weeks start Monday
    assert len(m["days"]) == 30
    kinds = {d["day"]: d["kind"] for d in m["days"] if d["kind"]}
    assert kinds == {15: "today", 20: "due", 24: "exam"}


def test_an_exam_today_shows_as_exam_not_just_today(tracker):
    tracker.vault.add_exam("DBMS", date(2026, 11, 15))
    kinds = {d["day"]: d["kind"] for d in build_dashboard(tracker)["month"]["days"] if d["kind"]}
    assert kinds == {15: "exam"}


def test_mic_hint_is_passed_through(tracker):
    assert build_dashboard(tracker)["mic_hint"] is None
    d = build_dashboard(tracker, mic_hint={"url": "https://192.168.1.3:8766", "code": "274852"})
    assert d["mic_hint"] == {"url": "https://192.168.1.3:8766", "code": "274852"}
