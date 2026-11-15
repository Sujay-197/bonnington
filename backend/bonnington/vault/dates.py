"""Turn dates and times as people say them ("next Thursday", "the 24th", "9am") into real ones.

Deterministic on purpose: a small language model gets date arithmetic wrong often enough to matter.
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1}


def _month(word: str) -> int | None:
    word = word.lower().rstrip(".")
    for i, name in enumerate(MONTHS, 1):
        if len(word) >= 3 and name.startswith(word):
            return i
    return None


def _weekday(word: str) -> int | None:
    word = word.lower().rstrip(".")
    for i, name in enumerate(WEEKDAYS):
        if len(word) >= 3 and name.startswith(word):
            return i
    return None


def _number(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return NUMBER_WORDS.get(word.lower())


def _make(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as e:
        raise ValueError(f"no such date: {day}/{month}/{year}") from e


def resolve_date(text: str, today: date) -> date:
    raw = (text or "").strip().lower()
    t = re.sub(r"\b(on|the|of|at|by|due)\b", " ", raw)
    t = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", t)
    t = re.sub(r"[,]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        raise ValueError("no date given")

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return _make(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?", t)     # day first, as in India
    if m:
        return _day_month(int(m[1]), int(m[2]), int(m[3]) if m[3] else None, today)

    if t == "today":
        return today
    if t == "tomorrow":
        return today + timedelta(days=1)
    if t == "day after tomorrow":
        return today + timedelta(days=2)
    if t == "next week":
        return today + timedelta(days=7)

    m = re.fullmatch(r"in (\w+) (day|days|week|weeks)", t)
    if m and _number(m[1]) is not None:
        n = _number(m[1])
        return today + timedelta(days=n * (7 if m[2].startswith("week") else 1))

    m = re.fullmatch(r"(this |next |coming )?(\w+)", t)
    if m and _weekday(m[2]) is not None:
        ahead = (_weekday(m[2]) - today.weekday() - 1) % 7 + 1          # 1..7 days from now
        upcoming = today + timedelta(days=ahead)
        same_week = upcoming.isocalendar()[:2] == today.isocalendar()[:2]
        if (m[1] or "").strip() == "next" and same_week:
            upcoming += timedelta(days=7)
        return upcoming

    if re.fullmatch(r"\d{1,2}", t):
        return _day_of_month(int(t), today)

    words = t.split()
    day = next((int(w) for w in words if re.fullmatch(r"\d{1,2}", w)), None)
    month = next((_month(w) for w in words if _month(w)), None)
    year = next((int(w) for w in words if re.fullmatch(r"\d{4}", w)), None)
    if day is not None and month is not None:
        return _day_month(day, month, year, today)
    raise ValueError(f"could not understand the date {text!r}")


def _day_month(day: int, month: int, year: int | None, today: date) -> date:
    if year is not None:
        return _make(year, month, day)
    d = _make(today.year, month, day)
    return d if d >= today else _make(today.year + 1, month, day)


def _day_of_month(day: int, today: date) -> date:
    """The next day with this number, today included."""
    year, month = today.year, today.month
    for _ in range(13):
        try:
            d = date(year, month, day)
            if d >= today:
                return d
        except ValueError:
            pass
        month += 1
        if month == 13:
            year, month = year + 1, 1
    raise ValueError(f"no such day of the month: {day}")


def resolve_time(text: str | None) -> time | None:
    t = (text or "").strip().lower().replace(".", "")
    if not t:
        return None
    if t in ("noon", "midday"):
        return time(12, 0)
    if t == "midnight":
        return time(0, 0)
    m = re.fullmatch(r"(\d{1,2}|[a-z]+)(?::(\d{2}))?\s*(am|pm)?(?: o'?clock)?", t)
    if not m:
        return None
    hour = _number(m[1])
    if hour is None or hour > 23:
        return None
    minute = int(m[2]) if m[2] else 0
    if m[3] == "pm" and hour < 12:
        hour += 12
    if m[3] == "am" and hour == 12:
        hour = 0
    if minute > 59:
        return None
    return time(hour, minute)


def spoken_date(d: date, today: date | None = None) -> str:
    text = f"{WEEKDAYS[d.weekday()].capitalize()} {d.day} {MONTHS[d.month - 1].capitalize()}"
    if today is not None and d.year != today.year:
        text += f" {d.year}"
    return text
