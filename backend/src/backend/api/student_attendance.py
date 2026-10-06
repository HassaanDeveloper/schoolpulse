"""Day 4 student attendance detail.

Mounted under /api/v1/students, alongside the Day 3 QR credential routes.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.attendance_report import (
    MAX_PAGE_SIZE,
    resolve_scope,
    student_detail_payload,
    validated_range,
)
from backend.core.security import (
    AuthenticatedUser,
    require_teacher_or_admin,
)
from backend.db.session import get_db
from backend.schemas.attendance_report import StudentAttendanceDetailRead
from backend.services.attendance_clock import school_local_date
from backend.services.school_access import resolve_student

router = APIRouter()


@router.get(
    "/{student_id}/attendance",
    response_model=StudentAttendanceDetailRead,
    summary="One student's attendance history with summary counts",
)
def student_attendance_detail(
    student_id: uuid.UUID,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> StudentAttendanceDetailRead:
    school, _ = resolve_scope(db, user, school_id, None)
    today = school_local_date(db, school)

    start, end = validated_range(start_date, end_date, today)

    # resolve_student refuses a student from any other school.
    student = resolve_student(db, student_id, school.id)

    payload = student_detail_payload(db, student, start, end, page, page_size)
    return StudentAttendanceDetailRead(**payload)
