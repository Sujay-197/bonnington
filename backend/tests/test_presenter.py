from datetime import date, datetime
from pathlib import Path

import pytest

from bonnington.presenter import Presenter, pick_cards
from bonnington.vault.projects import ProjectStatus
from bonnington.vault.store import Vault
from bonnington.vault.tools import Tracker

NOW = datetime(2026, 11, 15, 23, 40)
PROJECTS = ["das_v0", "tensor/campusai", "medrag", "clg/bio"]
SUBJECTS = ["DBMS", "CN"]


@pytest.mark.parametrize("text,cards,project", [
    ("What's left for this week?", {"week", "next"}, None),
    ("when is my next exam", {"week", "next"}, None),
    ("how many tasks are overdue", {"counts", "week", "next"}, None),
    ("How am I doing in DBMS?", {"scores"}, None),
    ("I scored 38 out of 50", {"scores"}, None),
    ("which of my projects are dying", {"projects"}, None),
    ("what was I last doing in medrag", {"projects", "focus"}, "medrag"),
    ("let's focus on Das V0 for now", {"projects", "focus"}, "das_v0"),
    ("put campusai on hold", {"projects", "focus"}, "tensor/campusai"),
    ("compare medrag and campusai", {"projects"}, None),          # two projects: no single focus
    ("how are you doing", set(), None),
    ("explain a B plus tree", set(), None),
])
def test_pick_cards(text, cards, project):
    assert pick_cards(text, SUBJECTS, PROJECTS) == (cards, project)


class FakeBridge:
    def __init__(self):
        self.events = []

    def broadcast(self, ev):
        self.events.append(ev)

    def of(self, type_):
        return [e for e in self.events if e.type == type_]


def _projects():
    return [ProjectStatus(n, Path(n), NOW, i * 3, "active", "Personal", f"title {n}", "main")
            for i, n in enumerate(PROJECTS)]


@pytest.fixture
def world(tmp_path):
    tracker = Tracker(Vault(tmp_path / "v"), projects=_projects, now=lambda: NOW)
    bridge = FakeBridge()
    p = Presenter(tracker, bridge, britney_count=lambda: 214, mic="phone", models_loaded=lambda: True)
    return tracker, bridge, p


def test_refresh_broadcasts_the_dashboard(world):
    tracker, bridge, p = world
    p.refresh()
    (ev,) = bridge.of("dashboard")
    assert ev.data["britney"] == 214 and ev.data["status"]["right"] == "MIC PHONE · MODELS LOADED"
    assert ev.data["focus"]["name"] == "das_v0"


def test_user_question_highlights_cards(world):
    _, bridge, p = world
    p.user_said("What's left for this week?")
    assert sorted(bridge.of("focus")[-1].cards) == ["next", "week"]


def test_asking_about_a_project_puts_it_in_focus(world):
    _, bridge, p = world
    p.user_said("what was I last doing in medrag")
    assert sorted(bridge.of("focus")[-1].cards) == ["focus", "projects"]
    assert bridge.of("dashboard")[-1].data["focus"]["name"] == "medrag"


def test_a_change_shows_the_memory_note_refreshes_and_highlights(world):
    tracker, bridge, p = world
    tracker.on_change = p.changed
    tracker.on_tool = p.tool_ran
    tracker.call("add_exam", {"subject": "DBMS", "date": "24 Nov", "time": "9am"})
    assert bridge.of("memory")[-1].text.startswith("Saved exam: DBMS Exam")
    assert bridge.of("dashboard")[-1].data["later"][0]["text"] == "DBMS: Exam 09:00"
    assert {"week", "next"} <= set(bridge.of("focus")[-1].cards)


def test_tool_reads_highlight_too_and_errors_do_not(world):
    tracker, bridge, p = world
    tracker.on_tool = p.tool_ran
    tracker.call("project_detail", {"project": "campusai"})
    assert sorted(bridge.of("focus")[-1].cards) == ["focus", "projects"]
    assert bridge.of("dashboard")[-1].data["focus"]["name"] == "tensor/campusai"
    n = len(bridge.of("focus"))
    tracker.call("add_exam", {"subject": "DBMS", "date": "soonish"})
    assert len(bridge.of("focus")) == n


def test_his_reply_can_add_highlights_and_cards_accumulate_within_a_turn(world):
    _, bridge, p = world
    p.user_said("anything I should worry about?")
    p.reply_done("Your DBMS average is 73 percent and medrag has been idle five days.")
    assert set(bridge.of("focus")[-1].cards) == {"scores", "projects", "focus"}
    p.user_said("and this week?")                      # a new turn starts clean
    assert set(bridge.of("focus")[-1].cards) == {"week", "next"}


def test_session_end_clears_highlights_and_returns_to_default_focus(world):
    _, bridge, p = world
    p.user_said("what was I last doing in medrag")
    p.session_ended()
    assert bridge.of("focus")[-1].cards == []
    assert bridge.of("dashboard")[-1].data["focus"]["name"] == "das_v0"


def test_events_serialise():
    import json

    from bonnington.events import DashboardEvent, FocusEvent, ShowWindowEvent
    assert json.loads(DashboardEvent({"date": "X"}).to_json()) == {"type": "dashboard", "data": {"date": "X"}}
    assert json.loads(FocusEvent(["week"]).to_json()) == {"type": "focus", "cards": ["week"]}
    assert json.loads(ShowWindowEvent().to_json()) == {"type": "show_window"}
