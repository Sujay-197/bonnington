"""The data behind the dashboard cards: one plain dictionary built from the vault and the project scan."""

from __future__ import annotations

from datetime import date
from typing import Any

from .vault.tools import Tracker

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
LIVE_WITHIN_DAYS = 2
MAX_WEEK, MAX_LATER, MAX_PROJECT_ROWS = 6, 4, 5


def when_label(d: date, today: date) -> str:
    n = (d - today).days
    if n < 0:
        return f"{-n}D LATE"
    if n == 0:
        return "TODAY"
    if n == 1:
        return "TOMORROW"
    if n <= 7:
        return f"{DAYS[d.weekday()]} · {n}D"
    return f"{DAYS[d.weekday()]} {d.day} · {n}D"


def _idle_label(days: int) -> str:
    return "TODAY" if days == 0 else f"{days}D IDLE"


def _ago(days: int) -> str:
    return "TODAY" if days == 0 else f"{days}D AGO"


MONTH_NAMES = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER",
               "OCTOBER", "NOVEMBER", "DECEMBER"]
MAX_TASKS = 6


def _month(vault, today: date) -> dict[str, Any]:
    """This month as a grid of days; exam days and deadline days are marked."""
    import calendar
    n_days = calendar.monthrange(today.year, today.month)[1]
    exams = {e.on.day for e in vault.exams() if not e.done and (e.on.year, e.on.month) == (today.year, today.month)}
    due = {r[0].day for r in vault.dated() if r[2] != "Exam" and (r[0].year, r[0].month) == (today.year, today.month)}
    days = []
    for d in range(1, n_days + 1):
        kind = "exam" if d in exams else "due" if d in due else "today" if d == today.day else ""
        days.append({"day": d, "kind": kind, "today": d == today.day})
    return {"label": MONTH_NAMES[today.month - 1], "offset": date(today.year, today.month, 1).weekday(), "days": days}


def build_dashboard(tracker: Tracker, *, britney_count: int = 0, focus_project: str | None = None,
                    mic: str = "device", models_loaded: bool = False,
                    mic_hint: dict[str, str] | None = None) -> dict[str, Any]:
    now = tracker._now()
    today = now.date()
    vault = tracker.vault

    def item(on, at, _label, text):
        n = (on - today).days
        tone = "late" if n < 0 else "soon" if n <= 7 else "normal"
        return {"text": text + (f" {at:%H:%M}" if at else ""), "when": when_label(on, today), "tone": tone}

    dated = vault.dated()
    near = [r for r in dated if (r[0] - today).days <= 7]
    far = [r for r in dated if (r[0] - today).days > 7]
    upcoming = [r for r in dated if r[0] >= today]
    nxt = None
    if upcoming:
        n = (upcoming[0][0] - today).days
        nxt = {"text": upcoming[0][3], "when": "TODAY" if n == 0 else "TOMORROW" if n == 1 else f"IN {n} DAYS"}

    open_tasks = [t for t in vault.tasks() if not t.done]
    dated_tasks = sorted((t for t in open_tasks if t.due), key=lambda t: t.due)
    task_rows = [{"text": t.title, "when": when_label(t.due, today),
                  "tone": "late" if t.due < today else "normal"} for t in dated_tasks]
    task_rows += [{"text": t.title, "when": "", "tone": "normal"} for t in open_tasks if not t.due]
    all_scores = vault.scores()
    by_subject: dict[str, list] = {}
    for s in sorted(all_scores, key=lambda s: s.on, reverse=True):
        by_subject.setdefault(s.subject, []).append(s)
    scores = [{"subject": subj, "count": len(rows),
               "percent": round(100 * sum(r.score for r in rows) / sum(r.out_of for r in rows))}
              for subj, rows in by_subject.items() if sum(r.out_of for r in rows)]
    scores = [{"subject": s["subject"], "percent": s["percent"], "count": s["count"]} for s in scores]

    projects = tracker._safe_projects()
    live = [p for p in projects if p.state == "active" and p.days_idle <= LIVE_WITHIN_DAYS]
    idle = sorted((p for p in projects if p.state in ("active", "stalled", "cold") and p not in live),
                  key=lambda p: p.days_idle)
    hold = [p for p in projects if p.state == "on hold"]
    done = [p for p in projects if p.state == "done"]
    rows = [{"name": p.name, "note": f"{p.days_idle}D IDLE", "tone": "soon" if p.days_idle <= 30 else "late"}
            for p in idle]
    rows += [{"name": p.name, "note": "ON HOLD", "tone": "muted"} for p in hold]

    return {
        "date": f"{DAYS[today.weekday()]} {today.day} {MONTHS[today.month - 1]}",
        "time": f"{now:%H:%M}",
        "britney": britney_count,
        "week": [item(*r) for r in near][:MAX_WEEK],
        "later": [item(*r) for r in far][:MAX_LATER],
        "next": nxt,
        "counts": {"exams": sum(1 for e in vault.exams() if not e.done and e.on >= today),
                   "tasks": len(open_tasks), "late": sum(1 for r in dated if r[0] < today)},
        "scores": scores,
        "tasks": task_rows[:MAX_TASKS],
        "month": _month(vault, today),
        "mic_hint": mic_hint,
        "projects": {"live": len(live), "idle": len(idle), "done": len(done), "hold": len(hold),
                     "rows": rows[:MAX_PROJECT_ROWS]},
        "focus": _focus(tracker, projects, focus_project),
        "status": {"left": f"VAULT {len(dated)} DATED · {len(open_tasks)} TASKS · {len(all_scores)} SCORES",
                   "right": f"MIC {mic.upper()} · MODELS {'LOADED' if models_loaded else 'ASLEEP'}"},
    }


def _focus(tracker: Tracker, projects: list, wanted: str | None) -> dict[str, Any] | None:
    if not projects:
        return None
    chosen = next((p for p in projects if p.name == wanted), None)
    if chosen is None:
        chosen = next((p for p in projects if p.state not in ("done", "on hold")), projects[0])
    rows = [[chosen.branch or "-", _idle_label(chosen.days_idle)]]
    detail = None
    if tracker._detail is not None:
        try:
            detail = tracker._detail(chosen.name)
        except Exception:  # an unreadable log must not blank the dashboard
            detail = None
    if detail is not None:
        rows += [[title, _ago(days)] for title, days in detail.sessions[:2]]
        rows += [[f'"{r}"', ""] for r in detail.requests[:1]]
    elif chosen.title:
        rows.append([chosen.title, ""])
    return {"name": chosen.name, "rows": rows}
