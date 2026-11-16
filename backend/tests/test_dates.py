from datetime import date, time

import pytest

from bonnington.vault.dates import resolve_date, resolve_time, spoken_date

TODAY = date(2026, 11, 15)   # a Sunday


@pytest.mark.parametrize("text,expected", [
    ("2026-11-24", date(2026, 11, 24)),
    ("today", date(2026, 11, 15)),
    ("tomorrow", date(2026, 11, 16)),
    ("day after tomorrow", date(2026, 11, 17)),
    ("Thursday", date(2026, 11, 19)),
    ("this thursday", date(2026, 11, 19)),
    ("on Monday", date(2026, 11, 16)),
    ("sunday", date(2026, 11, 22)),            # today is Sunday: the coming one
    ("the 24th", date(2026, 11, 24)),
    ("24", date(2026, 11, 24)),
    ("3rd", date(2026, 12, 3)),                 # already past this month
    ("15th", date(2026, 11, 15)),               # today counts
    ("24 Nov", date(2026, 11, 24)),
    ("Nov 24", date(2026, 11, 24)),
    ("24th of November", date(2026, 11, 24)),
    ("November 24, 2026", date(2026, 11, 24)),
    ("2 January", date(2027, 1, 2)),            # past this year -> next year
    ("in 3 days", date(2026, 11, 18)),
    ("in two weeks", date(2026, 11, 29)),
    ("next week", date(2026, 11, 22)),
    ("24/11/2026", date(2026, 11, 24)),
    ("24-11", date(2026, 11, 24)),
])
def test_resolve_date(text, expected):
    assert resolve_date(text, TODAY) == expected


def test_next_weekday_means_the_week_after_when_this_week_has_one():
    wednesday = date(2026, 11, 18)
    assert resolve_date("friday", wednesday) == date(2026, 11, 20)
    assert resolve_date("next friday", wednesday) == date(2026, 11, 27)
    assert resolve_date("next monday", wednesday) == date(2026, 11, 23)   # no Monday left this week


@pytest.mark.parametrize("text", ["", "soonish", "the 32nd", "31 February", "blah 2026"])
def test_unresolvable_dates_raise(text):
    with pytest.raises(ValueError):
        resolve_date(text, TODAY)


@pytest.mark.parametrize("text,expected", [
    ("09:00", time(9, 0)),
    ("9", time(9, 0)),
    ("9am", time(9, 0)),
    ("9 a.m.", time(9, 0)),
    ("9:30 pm", time(21, 30)),
    ("12pm", time(12, 0)),
    ("12am", time(0, 0)),
    ("noon", time(12, 0)),
    ("14:15", time(14, 15)),
    ("nine", time(9, 0)),
    ("half past two", None),
    ("", None),
    (None, None),
])
def test_resolve_time(text, expected):
    assert resolve_time(text) == expected


def test_spoken_date():
    assert spoken_date(date(2026, 11, 24)) == "Tuesday 24 November"
    assert spoken_date(date(2027, 1, 2), today=TODAY) == "Saturday 2 January 2027"
