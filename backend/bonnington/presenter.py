"""Decides what the dashboard shows: keeps the cards' data fresh and lights up the cards he is talking about."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from .dashboard import build_dashboard
from .events import DashboardEvent, FocusEvent, MemoryEvent
from .vault.tools import Tracker

log = logging.getLogger(__name__)

_WEEK = re.compile(r"\b(week|today|tonight|tomorrow|left|pending|due|deadline|deadlines|exam|exams|test|"
                   r"assignment|assignments|upcoming|schedule|calendar|overdue|late)\b")
_MONTH = re.compile(r"(month|calendar)")
_COUNTS = re.compile(r"\b(task|tasks|overdue|todo|to-do|reminder|reminders)\b")
_SCORES = re.compile(r"\b(score|scores|scored|marks|percent|grade|grades|average)\b|\d\s*(?:out of|/)\s*\d")
_PROJECTS = re.compile(r"\b(project|projects|dying|repo|repos|codebase|coding)\b")

_TOOL_CARDS = {
    "add_exam": {"week", "next", "month"}, "add_assignment": {"week", "next", "month"},
    "add_task": {"counts", "tasks", "week"}, "add_score": {"scores"},
    "mark_done": {"week", "counts", "tasks", "next"}, "remove_item": {"week", "counts", "tasks", "next"},
    "list_items": {"week", "counts", "tasks"}, "subject_summary": {"scores"}, "project_status": {"projects"},
    "project_detail": {"projects", "focus"}, "set_project_status": {"projects", "focus"},
}


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def pick_cards(text: str, subjects: list[str], projects: list[str]) -> tuple[set[str], str | None]:
    """Which cards a piece of conversation is about, and the single project it names (if exactly one)."""
    low = text.lower()
    cards: set[str] = set()
    if _WEEK.search(low):
        cards |= {"week", "next"}
    if _COUNTS.search(low):
        cards |= {"counts", "tasks"}
    if _MONTH.search(low):
        cards |= {"month"}
    if _SCORES.search(low) or any(re.search(rf"\b{re.escape(s.lower())}\b", low) for s in subjects):
        cards |= {"scores"}
    squashed = _squash(text)
    named = [p for p in projects if len(_squash(p.split("/")[-1])) >= 3 and _squash(p.split("/")[-1]) in squashed]
    if _PROJECTS.search(low) or named:
        cards |= {"projects"}
    project = named[0] if len(named) == 1 else None
    if project:
        cards |= {"focus"}
    return cards, project


class Presenter:
    def __init__(self, tracker: Tracker, bridge: Any, *, britney_count: Callable[[], int] = lambda: 0,
                 mic: Any = "device", models_loaded: Callable[[], bool] = lambda: False,
                 defer: Callable[[Callable[[], None]], Any] | None = None,
                 mic_hint: Callable[[], dict | None] = lambda: None) -> None:
        self.tracker, self.bridge = tracker, bridge
        self._britney, self._mic, self._models = britney_count, mic, models_loaded
        self._defer = defer or (lambda fn: fn())     # the app passes a thread pool: scans must not block audio
        self._mic_hint = mic_hint      # how to connect the phone mic, while it is not connected
        self._cards: set[str] = set()
        self._project: str | None = None

    # --- data -----------------------------------------------------------------------
    def refresh(self) -> None:
        self._defer(self._refresh_now)

    def _refresh_now(self) -> None:
        try:
            mic = self._mic() if callable(self._mic) else self._mic
            data = build_dashboard(self.tracker, britney_count=self._britney(), focus_project=self._project,
                                   mic=mic, models_loaded=self._models(), mic_hint=self._mic_hint())
        except Exception:  # the dashboard is a view; it must never take the assistant down
            log.exception("dashboard refresh failed")
            return
        self.bridge.broadcast(DashboardEvent(data))

    # --- conversation hooks -----------------------------------------------------------
    def _names(self) -> tuple[list[str], list[str]]:
        return self.tracker.vault.subjects(), [p.name for p in self.tracker._safe_projects()]

    def _show(self, cards: set[str], project: str | None, replace: bool = False) -> None:
        self._cards = set(cards) if replace else self._cards | cards
        if project and project != self._project:
            self._project = project
            self.refresh()
        self.bridge.broadcast(FocusEvent(sorted(self._cards)))

    def user_said(self, text: str) -> None:
        cards, project = pick_cards(text, *self._names())
        self._show(cards, project, replace=True)
        self.refresh()        # counters (Britney, tasks) stay live with the conversation

    def reply_done(self, text: str) -> None:
        cards, project = pick_cards(text, *self._names())
        if cards:
            self._show(cards, project)

    def tool_ran(self, name: str, args: dict, result: str) -> None:
        if result.startswith("ERROR") or name not in _TOOL_CARDS:
            return
        project = None
        if "project" in (args or {}):
            try:
                project = self.tracker._match_project(str(args["project"]))
            except Exception:
                project = None
        self._show(_TOOL_CARDS[name], project)

    def changed(self, text: str) -> None:
        self.bridge.broadcast(MemoryEvent(text))
        self.refresh()

    def session_ended(self) -> None:
        self._cards = set()
        had_project, self._project = self._project, None
        self.bridge.broadcast(FocusEvent([]))
        if had_project:
            self.refresh()
