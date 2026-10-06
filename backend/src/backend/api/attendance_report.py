"""Day 4 read-only attendance reporting endpoints.

Every route here is read-only. The Day 3 scanner remains the only writer, so
there is no route to edit or delete attendance.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.security import (
    AuthenticatedUser,
    require_teacher_or_admin,
)
from backend.db.models import Class, School, Student
from backend.db.session import get_db
from backend.schemas.attendance_report import (
    AttendanceHistoryPageRead,
    AttendanceHistoryRecordRead,
    AttendanceSummaryRead,
    ClassOptionRead,
    TodayAttendanceItemRead,
    TodayAttendancePageRead,
)
from backend.services import attendance_reports
from backend.services.attendance_clock import school_local_date
from backend.services.attendance_status import (
    AttendanceStatus,
    default_range,
    derive_status,
    validate_range,
)
from backend.services.school_access import resolve_class, resolve_staff_school, resolve_student

router = APIRouter()

MAX_PAGE_SIZE = 100


def resolve_scope(
    db: Session,
    user: AuthenticatedUser,
    school_id: uuid.UUID | None,
    class_id: uuid.UUID | None,
) -> tuple[School, uuid.UUID | None]:
    """Resolve the school and optional class filter for an attendance read.

    The school always comes from the caller's memberships; a client-supplied
    school_id is only honoured when it matches one of them. A class_id is
    validated against that school, and another school's class is reported as
    missing rather than forbidden.
    """
    school = resolve_staff_school(db, user, school_id)

    if class_id is not None:
        resolve_class(db, class_id, school.id)

    return school, class_id


def validated_range(
    start_date: date | None,
    end_date: date | None,
    today: date,
) -> tuple[date, date]:
    """Validate an optional history range, defaulting to the last 7 school days."""
    if start_date is None and end_date is None:
        return default_range(today)

    if start_date is None or end_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide both start_date and end_date, or neither.",
        )

    try:
        validate_range(start_date, end_date)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        )

    return start_date, end_date


def summarise_history(history: list[dict]):
    """Count each derived status across a full (unpaginated) history."""
    counts = attendance_reports.StatusCounts()
    for entry in history:
        counts.total += 1
        if entry["status"] is AttendanceStatus.absent:
            counts.absent += 1
        elif entry["status"] is AttendanceStatus.present:
            counts.present += 1
        else:
            counts.completed += 1
    return counts


@router.get(
    "/summary",
    response_model=AttendanceSummaryRead,
    summary="Absent / present / completed counts for the school's local today",
)
def attendance_summary(
    school_id: uuid.UUID | None = Query(default=None),
    class_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> AttendanceSummaryRead:
    school, class_filter = resolve_scope(db, user, school_id, class_id)

    # Always the school's local date; a client cannot supply its own "today".
    attendance_date = school_local_date(db, school)

    counts = attendance_reports.summary_for_date(
        db,
        school_id=school.id,
        attendance_date=attendance_date,
        class_id=class_filter,
    )

    return AttendanceSummaryRead(
        date=attendance_date,
        school_id=school.id,
        school_name=school.name,
        class_id=class_filter,
        **counts.as_dict(),
    )


@router.get(
    "/today",
    response_model=TodayAttendancePageRead,
    summary="Paginated student attendance for the school's local today",
)
def attendance_today(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = Query(default=None, max_length=100),
    class_id: uuid.UUID | None = Query(default=None),
    status_filter: AttendanceStatus | None = Query(default=None, alias="status"),
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> TodayAttendancePageRead:
    school, class_filter = resolve_scope(db, user, school_id, class_id)
    attendance_date = school_local_date(db, school)

    rows, total = attendance_reports.today_page(
        db,
        school_id=school.id,
        attendance_date=attendance_date,
        class_id=class_filter,
        search=search,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )

    items = [
        TodayAttendanceItemRead(
            student_id=student.id,
            student_name=attendance_reports.student_name(student),
            admission_number=student.admission_number,
            class_id=school_class.id,
            class_name=school_class.name,
            section=school_class.section,
            status=derive_status(
                record.arrival_at if record else None,
                record.departure_at if record else None,
            ),
            arrival_at=record.arrival_at if record else None,
            departure_at=record.departure_at if record else None,
        )
        for student, school_class, record in rows
    ]

    return TodayAttendancePageRead(
        date=attendance_date,
        school_id=school.id,
        school_name=school.name,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/history",
    response_model=AttendanceHistoryPageRead,
    summary="A student's attendance across a date range, gaps reported as absent",
)
def attendance_history(
    student_id: uuid.UUID = Query(...),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> AttendanceHistoryPageRead:
    school, _ = resolve_scope(db, user, school_id, None)
    today = school_local_date(db, school)

    start, end = validated_range(start_date, end_date, today)
    student = resolve_student(db, student_id, school.id)

    history = attendance_reports.history_for_student(db, student.id, start, end)
    page_items, total = attendance_reports.paginate_history(history, page, page_size)

    return AttendanceHistoryPageRead(
        student_id=student.id,
        student_name=attendance_reports.student_name(student),
        start_date=start,
        end_date=end,
        items=[AttendanceHistoryRecordRead(**item) for item in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/classes",
    response_model=list[ClassOptionRead],
    summary="Classes the caller may filter the dashboard by",
)
def attendance_filter_classes(
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> list[ClassOptionRead]:
    school = resolve_staff_school(db, user, school_id)

    rows = (
        db.query(Class)
        .filter(Class.school_id == school.id)
        .order_by(Class.name, Class.section)
        .all()
    )
    return [ClassOptionRead(id=row.id, name=row.name, section=row.section) for row in rows]


def student_detail_payload(
    db: Session,
    student: Student,
    start: date,
    end: date,
    page: int,
    page_size: int,
) -> dict:
    """Build the student attendance detail body.

    Shared with the student detail router so both endpoints derive status and
    summarise counts through exactly the same code path.
    """
    history = attendance_reports.history_for_student(db, student.id, start, end)
    page_items, total = attendance_reports.paginate_history(history, page, page_size)
    counts = summarise_history(history)

    school_class = student.class_
    return {
        "student": {
            "id": student.id,
            "name": attendance_reports.student_name(student),
            "admission_number": student.admission_number,
            "class_name": school_class.name if school_class else "",
            "section": school_class.section if school_class else None,
        },
        "start_date": start,
        "end_date": end,
        "records": page_items,
        "summary": {
            "total_days": counts.total,
            "present_days": counts.present,
            "absent_days": counts.absent,
            "completed_days": counts.completed,
        },
        "total": total,
        "page": page,
        "page_size": page_size,
    }
