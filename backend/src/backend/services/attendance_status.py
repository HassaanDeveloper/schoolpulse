"""Deriving attendance display status from Day 3 attendance records.

Day 4 deliberately adds **no** database enum and **no** stored status column.
The status of a student on a given school-local date is derived from the
attendance record:

    no record                  -> ABSENT
    arrival recorded           -> PRESENT
    arrival and departure      -> COMPLETED

Deriving rather than storing means a record can never disagree with itself, and
Day 3's scanner stays the only writer.
"""

import enum
from datetime import date, timedelta


class AttendanceStatus(str, enum.Enum):
    """Display status for one student on one school-local date."""

    absent = "absent"
    present = "present"
    completed = "completed"

    @property
    def label(self) -> str:
        return {
            AttendanceStatus.absent: "Absent",
            AttendanceStatus.present: "Present",
            AttendanceStatus.completed: "Completed",
        }[self]


def derive_status(arrival_at, departure_at) -> AttendanceStatus:
    """Return the display status implied by an attendance record's timestamps.

    `arrival_at`/`departure_at` may be None (absent) or an aware datetime.
    """
    if arrival_at is None:
        return AttendanceStatus.absent
    if departure_at is None:
        return AttendanceStatus.present
    return AttendanceStatus.completed


# A reasonable MVP ceiling on a history range. Keeps a single request from
# fanning out over an unbounded number of dates.
MAX_HISTORY_DAYS = 90

DEFAULT_HISTORY_DAYS = 7


def enumerate_dates(start: date, end: date) -> list[date]:
    """Every calendar date from `start` to `end` inclusive.

    SchoolPulse has no holiday calendar in Day 4, so weekends and holidays are
    reported as ordinary attendance dates (and therefore usually ABSENT). This
    is a deliberate simplification, not an oversight.
    """
    if end < start:
        return []
    span = (end - start).days
    return [start + timedelta(days=offset) for offset in range(span + 1)]


def validate_range(start: date, end: date, max_days: int = MAX_HISTORY_DAYS) -> None:
    """Raise ValueError when a requested date range is unusable."""
    if end < start:
        raise ValueError("end_date must be on or after start_date.")
    if (end - start).days + 1 > max_days:
        raise ValueError(f"Date range must not exceed {max_days} days.")


def default_range(today: date, days: int = DEFAULT_HISTORY_DAYS) -> tuple[date, date]:
    """The trailing window ending on `today`, inclusive of today."""
    span = max(1, days)
    return today - timedelta(days=span - 1), today
