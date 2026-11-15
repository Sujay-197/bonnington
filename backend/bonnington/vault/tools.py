"""What the brain can see and do with the vault: a status snapshot for every turn, and tools for changes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from .dates import MONTHS, WEEKDAYS, resolve_date, resolve_time, spoken_date
from .projects import ProjectStatus, set_project_status
from .store import Ambiguous, NotFound, Vault, _num

KINDS = ("exam", "assignment", "task", "score")
_CHANGES = {"add_exam", "add_assignment", "add_task", "add_score", "mark_done", "remove_item", "undo_last",
            "set_project_status"}
PROJECT_STATES = ("on hold", "done", "active")


def _fn(name: str, description: str, props: dict[str, str], required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "required": required,
                       "properties": {k: {"type": "string", "description": v} for k, v in props.items()}}}}


_DATE_HELP = 'the date as the user said it, e.g. "next Thursday", "the 24th", "24 Nov", "tomorrow"'

_SPECS = [
    _fn("add_exam", "Record an upcoming exam or test.",
        {"subject": "subject name, e.g. DBMS", "date": _DATE_HELP, "time": 'optional start time, e.g. "9am"',
         "title": 'optional name, e.g. "Midterm 2"', "note": "optional note, e.g. units covered"},
        ["subject", "date"]),
    _fn("add_assignment", "Record an assignment, lab or submission with a deadline.",
        {"subject": "subject name", "title": "what is due", "due": _DATE_HELP}, ["subject", "title", "due"]),
    _fn("add_task", "Record a personal task or reminder.",
        {"title": "the task", "due": "optional: " + _DATE_HELP}, ["title"]),
    _fn("add_score", "Record a score the user got in an exam, quiz or assignment.",
        {"subject": "subject name", "exam": 'which exam, e.g. "Midterm 1"', "score": "marks obtained",
         "out_of": "maximum marks", "date": "optional: when it happened; default today"},
        ["subject", "exam", "score", "out_of"]),
    _fn("mark_done", "Tick off an exam, assignment or task as finished.",
        {"kind": "exam, assignment or task", "which": "words identifying it, e.g. subject or title"},
        ["kind", "which"]),
    _fn("remove_item", "Delete an exam, assignment, task or score that was recorded wrongly or cancelled.",
        {"kind": "exam, assignment, task or score", "which": "words identifying it"}, ["kind", "which"]),
    _fn("undo_last", "Take back the most recent change (use when the user says it was saved wrong).", {}, []),
    _fn("list_items", "List everything recorded of one kind, when the snapshot is not enough.",
        {"kind": "exams, assignments, tasks, scores or all"}, ["kind"]),
    _fn("subject_summary", "Upcoming items, scores and average for one subject.",
        {"subject": "subject name"}, ["subject"]),
    _fn("project_status", "The state of every coding project, from the user's local coding history.", {}, []),
    _fn("project_detail", "What the user was last doing in one coding project: recent sessions and "
        "the last things they asked for there.", {"project": "project name"}, ["project"]),
    _fn("set_project_status", "Record that the user put a project on hold, finished it, or resumed it.",
        {"project": "project name", "status": "on hold, done or active", "note": "optional reason"},
        ["project", "status"]),
]


def _label(item) -> str:
    if item.kind == "task":
        return item.title
    if item.kind == "score":
        return f"{item.subject} {item.exam}"
    return f"{item.subject} {item.title}"


def _long_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1].capitalize()}"


def _relative(d: date, today: date) -> str:
    n = (d - today).days
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    if n == -1:
        return "yesterday"
    return f"in {n} days" if n > 0 else f"{-n} days ago"


def _project_line(p: ProjectStatus) -> str:
    line = f"{p.name} ({p.area}): {p.state}, idle {p.days_idle} days"
    if p.title:
        line += f', last worked on "{p.title}"'
    if p.note:
        line += f", note: {p.note}"
    return line


class Tracker:
    def __init__(self, vault: Vault, projects: Callable[[], list[ProjectStatus]],
                 now: Callable[[], datetime] = datetime.now, detail: Callable[[str], Any] | None = None) -> None:
        self.vault = vault
        self._projects = projects
        self._now = now
        self._detail = detail
        self.on_change: Callable[[str], None] | None = None   # told about every successful change
        self.on_tool: Callable[[str, dict, str], None] | None = None   # told about every tool call

    def tool_specs(self) -> list[dict]:
        return _SPECS

    # --- snapshot ---------------------------------------------------------------------
    def snapshot(self) -> str:
        now = self._now()
        today = now.date()
        out = ["TRACKER DATA (the only facts you have about the user's schedule, scores and projects).",
               f"Today is {_long_date(today)} {today.year}, {now:%H:%M}."]
        dated = self.vault.dated()
        undated = [t.title for t in self.vault.tasks() if not t.done and not t.due]
        scores = sorted(self.vault.scores(), key=lambda s: s.on, reverse=True)[:5]

        def row(on, at, label, text):
            return f"- {_long_date(on)} ({_relative(on, today)}){f' {at:%H:%M}' if at else ''}: {label}, {text}"

        week = [r for r in dated if today <= r[0] <= today + timedelta(days=7)]
        overdue = [r for r in dated if r[0] < today]
        later = [r for r in dated if r[0] > today + timedelta(days=7)]
        if not dated and not undated and not scores:
            out.append("Nothing recorded yet: no exams, assignments, tasks or scores.")
        else:
            if week:
                out.append("Next 7 days:")
                out += [row(*r) for r in week]
                if not any(r[2] == "Exam" for r in week):
                    out.append("No exams this week.")
            else:
                out.append("Next 7 days: nothing dated. No exams this week.")
            if overdue:
                out.append("Overdue:")
                out += [row(*r) for r in overdue]
            if later:
                out.append("Later:")
                out += [row(*r) for r in later[:8]]
                if len(later) > 8:
                    out.append(f"- and {len(later) - 8} more")
            if undated:
                out.append("Tasks with no date: " + "; ".join(undated[:10]))
            if scores:
                out.append("Recent scores: " + "; ".join(
                    f"{s.subject} {s.exam} {_num(s.score)}/{_num(s.out_of)} ({s.percent}%)" for s in scores))
        projects = self._safe_projects()
        if projects:
            out.append("Projects:")
            out += [f"- {_project_line(p)}" for p in projects[:12]]
        return "\n".join(out)

    def _safe_projects(self) -> list[ProjectStatus]:
        try:
            return self._projects()
        except Exception:  # a broken log file must not stop a conversation
            return []

    # --- tools ------------------------------------------------------------------------
    def call(self, name: str, args: dict[str, Any] | None) -> str:
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            return f"ERROR: unknown tool {name}"
        args = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        try:
            result = handler(args)
        except KeyError as e:
            result = f"ERROR: missing {e.args[0]}; ask the user for it"
        except (ValueError, NotFound, Ambiguous) as e:
            result = f"ERROR: {e}"
        if not result.startswith("ERROR"):
            if name in _CHANGES and result != "Nothing to undo." and self.on_change is not None:
                self.on_change(result)
        if self.on_tool is not None:
            self.on_tool(name, args, result)
        return result

    def _today(self) -> date:
        return self._now().date()

    def _when(self, d: date) -> str:
        return spoken_date(d, self._today())

    @staticmethod
    def _kind(args: dict) -> str:
        kind = str(args["kind"]).strip().lower()
        kind = kind[:-1] if kind.endswith("s") else kind
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        return kind

    def _t_add_exam(self, a: dict) -> str:
        on = resolve_date(str(a["date"]), self._today())
        at = resolve_time(str(a["time"])) if "time" in a else None
        e = self.vault.add_exam(str(a["subject"]), on, at, str(a.get("title", "Exam")), str(a.get("note", "")))
        return f"Saved exam: {e.subject} {e.title} on {self._when(on)}" + (f" at {at:%H:%M}." if at else ".")

    def _t_add_assignment(self, a: dict) -> str:
        due = resolve_date(str(a["due"]), self._today())
        x = self.vault.add_assignment(str(a["subject"]), str(a["title"]), due)
        return f"Saved assignment: {x.subject} {x.title}, due {self._when(due)}."

    def _t_add_task(self, a: dict) -> str:
        due = resolve_date(str(a["due"]), self._today()) if "due" in a else None
        t = self.vault.add_task(str(a["title"]), due)
        return f"Saved task: {t.title}, " + (f"due {self._when(due)}." if due else "no due date.")

    def _t_add_score(self, a: dict) -> str:
        score, out_of = float(a["score"]), float(a["out_of"])
        if out_of <= 0 or score < 0:
            raise ValueError("score and out_of must be positive numbers")
        on = resolve_date(str(a["date"]), self._today()) if "date" in a else self._today()
        s = self.vault.add_score(str(a["subject"]), str(a["exam"]), score, out_of, on)
        return f"Saved score: {s.subject} {s.exam}, {_num(score)} out of {_num(out_of)} ({s.percent}%)."

    def _t_mark_done(self, a: dict) -> str:
        kind = self._kind(a)
        if kind == "score":
            raise ValueError("a score cannot be marked done")
        return f"Marked done: {_label(self.vault.mark_done(kind, str(a['which'])))}."

    def _t_remove_item(self, a: dict) -> str:
        kind = self._kind(a)
        return f"Removed {kind}: {_label(self.vault.remove(kind, str(a['which'])))}."

    def _t_undo_last(self, a: dict) -> str:
        undone = self.vault.undo()
        return f"Undone: {undone}." if undone else "Nothing to undo."

    def _t_list_items(self, a: dict) -> str:
        kind = str(a.get("kind", "all")).strip().lower()
        kinds = KINDS if kind == "all" else (self._kind({"kind": kind}),)
        getters = {"exam": self.vault.exams, "assignment": self.vault.assignments,
                   "task": self.vault.tasks, "score": self.vault.scores}
        lines = [f"{k.capitalize()}: {it.describe()}" for k in kinds for it in getters[k]() if not it.done]
        return "\n".join(lines) or "Nothing recorded."

    def _t_subject_summary(self, a: dict) -> str:
        wanted = str(a["subject"]).strip()
        subject = next((s for s in self.vault.subjects() if s.lower() == wanted.lower()), None)
        if subject is None:
            return f"Nothing recorded for {wanted}."
        return "\n".join(l for l in self.vault.subject_gist(subject).splitlines() if l and not l.startswith("_"))

    def _t_project_status(self, a: dict) -> str:
        projects = self._safe_projects()
        return "\n".join(_project_line(p) for p in projects) or "No coding projects found."

    def _t_set_project_status(self, a: dict) -> str:
        status = str(a["status"]).strip().lower()
        if status not in PROJECT_STATES:
            raise ValueError(f"status must be one of {', '.join(PROJECT_STATES)}")
        name = self._match_project(str(a["project"]))
        set_project_status(self.vault.root, name, status, str(a.get("note", "")))
        getattr(self, "invalidate_projects", lambda: None)()
        return f"{name} is now marked {status}."

    def _match_project(self, wanted_raw: str) -> str:
        wanted = wanted_raw.strip().lower()
        names = [p.name for p in self._safe_projects()]
        hits = [n for n in names if n.lower() == wanted] or \
               [n for n in names if n.lower().split("/")[-1] == wanted] or \
               [n for n in names if wanted in n.lower()]
        if not hits:
            raise NotFound(f"no project matching {wanted_raw!r}; known: {', '.join(names) or 'none'}")
        if len(hits) > 1:
            raise Ambiguous(f"several projects match {wanted_raw!r}: {', '.join(hits)}")
        return hits[0]

    def _t_project_detail(self, a: dict) -> str:
        name = self._match_project(str(a["project"]))
        status = next(p for p in self._safe_projects() if p.name == name)
        lines = [_project_line(status) + (f", branch {status.branch}" if status.branch else "")]
        detail = self._detail(name) if self._detail is not None else None
        if detail is not None:
            def ago(n: int) -> str:
                return "today" if n == 0 else "yesterday" if n == 1 else f"{n} days ago"
            if detail.sessions:
                lines.append("Recent sessions: " + "; ".join(f'"{t}" ({ago(n)})' for t, n in detail.sessions))
            if detail.requests:
                lines.append("Last things the user asked for there: " + "; ".join(f'"{r}"' for r in detail.requests))
        return "\n".join(lines)


def build_tracker(settings, default_projects_root, now: Callable[[], datetime] = datetime.now,
                  cache_seconds: float = 60.0) -> Tracker:
    """The tracker for the real app: vault from settings, project scan cached for a minute."""
    import time
    from pathlib import Path

    from .projects import project_statuses

    vault = Vault(Path(settings.vault_dir))
    claude_dir = Path(settings.claude_projects_dir) if settings.claude_projects_dir \
        else Path.home() / ".claude" / "projects"
    root = Path(settings.projects_root) if settings.projects_root else Path(default_projects_root)
    cache: dict = {"at": 0.0, "value": []}

    def projects() -> list[ProjectStatus]:
        if time.monotonic() - cache["at"] > cache_seconds or not cache["at"]:
            cache["value"] = project_statuses(vault.root, claude_dir, root, settings.academic_folders, now())
            cache["at"] = time.monotonic()
        else:  # the user's on-hold/done notes change more often than the scan
            from .projects import read_project_notes
            notes = read_project_notes(vault.root)
            for p in cache["value"]:
                if p.name in notes:
                    p.state, p.note = notes[p.name]
        return cache["value"]

    from .projects import project_detail
    tracker = Tracker(vault, projects, now,
                      detail=lambda name: project_detail(claude_dir, root, name, now()))
    tracker.invalidate_projects = lambda: cache.update(at=0.0)
    return tracker
