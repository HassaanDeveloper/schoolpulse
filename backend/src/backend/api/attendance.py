import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.security import (
    AuthenticatedUser,
    require_profile,
    require_teacher_or_admin,
)
from backend.db.models import (
    AttendanceRecord,
    NotificationTypeEnum,
    RoleEnum,
    School,
    Student,
    StudentStatusEnum,
)
from backend.db.session import get_db
from backend.schemas.attendance import (
    ScanRequest,
    ScanResponse,
    ScanStatus,
    ScannedStudent,
)
from backend.services import qr_credentials
from backend.services.attendance_clock import school_local_date, utc_now
from backend.services.notifications import notify_attendance_event

logger = logging.getLogger(__name__)

router = APIRouter()

INVALID_CREDENTIAL_DETAIL = "Invalid or inactive QR credential."
INACTIVE_STUDENT_DETAIL = "This student is inactive and cannot be marked present."
CROSS_SCHOOL_DETAIL = "This QR credential cannot be used at your school."


def student_name(student: Student) -> str:
    return f"{student.first_name} {student.last_name}".strip()


def build_response(
    status_value: ScanStatus,
    student: Student,
    record: AttendanceRecord,
) -> ScanResponse:
    if status_value is ScanStatus.ARRIVAL_RECORDED:
        timestamp = record.arrival_at
    else:
        timestamp = record.departure_at

    return ScanResponse(
        status=status_value,
        student=ScannedStudent(
            id=student.id,
            name=student_name(student),
            admission_number=student.admission_number,
        ),
        attendance_date=record.attendance_date,
        arrival_at=record.arrival_at,
        departure_at=record.departure_at,
        timestamp=timestamp,
    )


def find_record(
    db: Session,
    student_id,
    attendance_date,
) -> AttendanceRecord | None:
    """Load today's record for a student, taking a row lock when supported.

    `SELECT ... FOR UPDATE` serialises concurrent scanners on PostgreSQL so that
    two simultaneous departure scans cannot both observe `departure_at IS NULL`
    and both write a departure. SQLite does not implement row locking, so the
    clause is a no-op there; the UNIQUE (student_id, attendance_date) constraint
    still prevents duplicate rows.
    """
    query = db.query(AttendanceRecord).filter(
        AttendanceRecord.student_id == student_id,
        AttendanceRecord.attendance_date == attendance_date,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    return query.one_or_none()


@router.post(
    "/scan",
    response_model=ScanResponse,
    summary="Record arrival or departure from a scanned QR credential",
)
def scan_attendance(
    payload: ScanRequest,
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> ScanResponse:
    profile = require_profile(user)

    # 1. Resolve the credential. Unknown or revoked tokens are indistinguishable.
    credential = qr_credentials.resolve_active_credential(db, payload.credential)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVALID_CREDENTIAL_DETAIL
        )

    # 2. Resolve the student from the credential, never from the request.
    student = (
        db.query(Student).filter(Student.id == credential.student_id).one_or_none()
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVALID_CREDENTIAL_DETAIL
        )

    # 3. The scanner must administer or teach at the student's school.
    scanner_school_ids = {
        membership.school_id
        for membership in profile.memberships
        if membership.role in (RoleEnum.school_admin, RoleEnum.teacher)
    }
    if student.school_id not in scanner_school_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=CROSS_SCHOOL_DETAIL
        )

    # 4. Inactive students cannot be marked present.
    if student.status != StudentStatusEnum.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_STUDENT_DETAIL
        )

    school = db.query(School).filter(School.id == student.school_id).one_or_none()
    if school is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVALID_CREDENTIAL_DETAIL
        )

    # 5. The attendance date is always the school's local date.
    attendance_date = school_local_date(db, school)
    now = utc_now()

    record = find_record(db, student.id, attendance_date)

    # 6a. First scan of the day records the arrival.
    if record is None:
        record = AttendanceRecord(
            school_id=student.school_id,
            student_id=student.id,
            attendance_date=attendance_date,
            arrival_at=now,
            arrival_scanned_by=profile.id,
        )
        db.add(record)
        try:
            # Day 5: the arrival notices are written in the scan's own
            # transaction, so attendance and notification either both land or
            # neither does.
            db.flush()
            _notify(db, record, student, school, NotificationTypeEnum.arrival)
            db.commit()
        except IntegrityError:
            # A concurrent scanner inserted the same student/date row first.
            db.rollback()
            record = find_record(db, student.id, attendance_date)
            if record is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Attendance could not be recorded. Please retry.",
                )
            return _apply_existing(record, student, profile, now, db, school)

        db.refresh(record)
        return build_response(ScanStatus.ARRIVAL_RECORDED, student, record)

    # 6b/6c. Existing record: departure on the second scan, no-op afterwards.
    return _apply_existing(record, student, profile, now, db, school)


def _notify(
    db: Session,
    record: AttendanceRecord,
    student: Student,
    school: School,
    notification_type: NotificationTypeEnum,
) -> None:
    """Day 5 notification hook for a scan.

    Failures are logged rather than raised: a broken notification path must
    never turn a successful scan into an error or lose the attendance record.
    No rollback is issued either, because rolling back would discard the
    caller's pending attendance write. Transaction recovery belongs to the
    caller's own `IntegrityError` handler.
    """
    try:
        notify_attendance_event(
            db,
            record=record,
            student=student,
            school=school,
            notification_type=notification_type,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "could not create %s notifications for attendance %s",
            notification_type.value,
            record.id,
        )


def _apply_existing(
    record: AttendanceRecord,
    student: Student,
    profile,
    now,
    db: Session,
    school: School,
) -> ScanResponse:
    if record.arrival_at is not None and record.departure_at is None:
        record.departure_at = now
        record.departure_scanned_by = profile.id
        try:
            # Same transaction as the Day 3 departure write.
            db.flush()
            _notify(db, record, student, school, NotificationTypeEnum.departure)
            db.commit()
        except IntegrityError:
            db.rollback()
            db.refresh(record)
            return build_response(ScanStatus.ALREADY_RECORDED, student, record)
        db.refresh(record)
        return build_response(ScanStatus.DEPARTURE_RECORDED, student, record)

    # ALREADY_RECORDED: both scans already happened, so no notice is due.
    return build_response(ScanStatus.ALREADY_RECORDED, student, record)