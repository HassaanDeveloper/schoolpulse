"""Queries backing the Day 4 attendance dashboard and history.

Everything here is school-scoped and aggregated in the database. No endpoint
loads a school's students or attendance rows into Python just to count them.
"""

import uuid
from datetime import date

from sqlalchemy import Integer, and_, cast, func, or_
from sqlalchemy.orm import Session, aliased

from backend.db.models import (
    AttendanceRecord,
    Class,
    Student,
    StudentStatusEnum,
)
from backend.services.attendance_status import (
    AttendanceStatus,
    derive_status,
    enumerate_dates,
)


class StatusCounts:
    """absent / present / completed tallies that always sum to the total."""

    def __init__(
        self,
        total: int = 0,
        absent: int = 0,
        present: int = 0,
        completed: int = 0,
    ):
        self.total = total
        self.absent = absent
        self.present = present
        self.completed = completed

    def as_dict(self) -> dict[str, int]:
        """Field names matching `AttendanceSummaryRead`."""
        return {
            "total_students": self.total,
            "absent": self.absent,
            "present": self.present,
            "completed": self.completed,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"StatusCounts(total={self.total}, absent={self.absent}, "
            f"present={self.present}, completed={self.completed})"
        )


def student_name(student: Student) -> str:
    return f"{student.first_name} {student.last_name}".strip()


def status_predicate(status_value: AttendanceStatus, target=AttendanceRecord):
    """SQL predicate for one derived status.

    `target` must be the entity the predicate is applied to — the aliased
    AttendanceRecord used in the LEFT JOIN, not the base table. Using the base
    table here would add an unjoined FROM element and turn the query into a
    cartesian product.

    Must mirror `derive_status` exactly: the SQL form drives counting and
    filtering, the Python form drives response assembly.
    """
    if status_value is AttendanceStatus.absent:
        # No row exists for this student on this date.
        return target.id.is_(None)
    if status_value is AttendanceStatus.present:
        return and_(
            target.arrival_at.isnot(None),
            target.departure_at.is_(None),
        )
    return and_(
        target.arrival_at.isnot(None),
        target.departure_at.isnot(None),
    )


def _count_flag(predicate):
    """1 when the predicate holds, else 0, so it can be summed."""
    return func.sum(cast(predicate, Integer))


def summary_for_date(
    db: Session,
    school_id: uuid.UUID,
    attendance_date: date,
    class_id: uuid.UUID | None = None,
) -> StatusCounts:
    """Count absent/present/completed for one school-local date.

    A single grouped query over a LEFT JOIN, so cost tracks the number of
    students rather than the number of attendance rows.
    """
    record = aliased(AttendanceRecord)

    query = (
        db.query(
            func.count(Student.id).label("total"),
            _count_flag(status_predicate(AttendanceStatus.absent, record)).label("absent"),
            _count_flag(status_predicate(AttendanceStatus.present, record)).label("present"),
            _count_flag(status_predicate(AttendanceStatus.completed, record)).label("completed"),
        )
        .select_from(Student)
        .outerjoin(
            record,
            and_(
                record.student_id == Student.id,
                record.attendance_date == attendance_date,
            ),
        )
        .where(Student.school_id == school_id)
        .where(Student.status == StudentStatusEnum.active)
    )

    if class_id is not None:
        query = query.where(Student.class_id == class_id)

    row = query.one()

    total = int(row.total or 0)
    absent = int(row.absent or 0)
    present = int(row.present or 0)
    completed = int(row.completed or 0)

    # Any status outside the three buckets (which should be unreachable) is
    # reported as absent so the counts always reconcile with the total.
    if absent + present + completed != total:
        absent = total - present - completed

    return StatusCounts(total=total, absent=absent, present=present, completed=completed)


def today_page(
    db: Session,
    school_id: uuid.UUID,
    attendance_date: date,
    *,
    class_id: uuid.UUID | None = None,
    search: str | None = None,
    status_filter: AttendanceStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Student, Class, AttendanceRecord | None]], int]:
    """One page of the school-local day's student list, with derived status.

    Returns the page rows plus the unpaginated total for the same filters.
    """
    record = aliased(AttendanceRecord)

    query = (
        db.query(Student, Class, record)
        .select_from(Student)
        .join(Class, Class.id == Student.class_id)
        .outerjoin(
            record,
            and_(
                record.student_id == Student.id,
                record.attendance_date == attendance_date,
            ),
        )
        .where(Student.school_id == school_id)
        .where(Student.status == StudentStatusEnum.active)
    )

    if class_id is not None:
        query = query.filter(Student.class_id == class_id)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Student.first_name.ilike(pattern),
                Student.last_name.ilike(pattern),
                Student.admission_number.ilike(pattern),
            )
        )

    if status_filter is not None:
        query = query.filter(status_predicate(status_filter, record))

    total = query.count()

    rows = (
        query.order_by(
            Student.first_name,
            Student.last_name,
            Student.admission_number,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return rows, total


def history_for_student(
    db: Session,
    student_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Every date in the range for one student, with missing days as ABSENT.

    The date axis comes from the requested range rather than from the rows that
    happen to exist, so a day on which nothing was scanned is reported as
    ABSENT instead of being silently omitted.
    """
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_id)
        .filter(AttendanceRecord.attendance_date >= start_date)
        .filter(AttendanceRecord.attendance_date <= end_date)
        .order_by(AttendanceRecord.attendance_date.desc())
        .all()
    )

    by_date = {record.attendance_date: record for record in records}

    history: list[dict] = []
    # Newest first, which is the order the dashboard and history screen display.
    for day in reversed(enumerate_dates(start_date, end_date)):
        record = by_date.get(day)
        history.append(
            {
                "date": day,
                "status": derive_status(
                    record.arrival_at if record else None,
                    record.departure_at if record else None,
                ),
                "arrival_at": record.arrival_at if record else None,
                "departure_at": record.departure_at if record else None,
            }
        )
    return history


def paginate_history(
    history: list[dict],
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    total = len(history)
    start = (page - 1) * page_size
    return history[start : start + page_size], total
