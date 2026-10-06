"""Day 5 endpoints: admin-managed parent links and parent self-service.

Two distinct audiences share this module:

* `/students/{id}/parents` is a **school admin** tool that grants and revokes
  guardian access.
* `/me/students` and `/me/notifications` are the **parent's own** view of
  their children.

Both resolve identity from the verified JWT profile and scope every query by
school, so a parent can only ever reach students a school administrator linked
to them.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from backend.api.attendance_report import validated_range

from backend.core.security import (
    AuthenticatedUser,
    require_parent,
    require_profile,
    require_school_admin,
)
from backend.db.models import (
    AttendanceRecord,
    Class,
    Notification,
    RoleEnum,
    School,
    SchoolMembership,
    Student,
    StudentParentLink,
    UserProfile,
)
from backend.db.session import get_db
from backend.schemas.parent import (
    LinkedParentRead,
    NotificationList,
    NotificationRead,
    ParentAttendanceDayRead,
    ParentAttendanceHistory,
    ParentChildList,
    ParentChildRead,
    ParentDirectoryList,
    ParentDirectoryRead,
    ParentLinkCreate,
    UnreadCount,
)
from backend.services.attendance_status import derive_status
from backend.services.attendance_clock import school_local_date, utc_now
from backend.services.attendance_reports import history_for_student
from backend.services.notifications import format_occurrence_time, unread_count
from backend.services.school_access import (
    linked_students,
    resolve_admin_school,
    resolve_admin_school_for_student,
    resolve_linked_student,
    resolve_parent_profile,
    resolve_parent_school,
)

# Two routers on purpose. The admin link routes and the parent's own routes
# live under different prefixes with different audiences; keeping them separate
# means the admin surface can never be reached through /me, and vice versa.
router = APIRouter()
me_router = APIRouter()

# Day 6: the admin-side directory of linkable parent accounts. It hangs off
# /parents rather than /students, because it is about accounts rather than one
# student's links. Still an admin-only surface.
directory_router = APIRouter()


@directory_router.get(
    "",
    response_model=ParentDirectoryList,
    summary="List parent accounts that can be linked (school admin only)",
)
def list_parent_accounts(
    school_id: uuid.UUID | None = Query(
        default=None,
        description="Defaults to the caller's only school; required when they administer several.",
    ),
    search: str | None = Query(default=None, max_length=100),
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> ParentDirectoryList:
    """Search the parent accounts of a school the caller administers.

    This is a **read-only directory**, added for Day 6 because the mobile
    parent-linking screen has to offer an administrator a way to choose an
    existing guardian, and `POST /students/{id}/parents` needs a `user_id`.

    It deliberately does not create accounts. There is no public parent
    registration in SchoolPulse, so an administrator can only link guardians
    that already exist; adding a create-user endpoint here would be a
    backdoor into the identity system.

    The result is restricted twice over: the school must be one the caller
    administers, and each profile must hold a `parent` membership in *that*
    school. Staff accounts and parents of other schools are never returned.
    """
    school = resolve_admin_school(db, user, school_id)

    # Scoped from the membership outwards, so a parent who is also staff, or a
    # guardian of two schools, only ever appears under the school being viewed.
    query = (
        db.query(UserProfile)
        .join(SchoolMembership, SchoolMembership.user_id == UserProfile.id)
        .filter(
            SchoolMembership.school_id == school.id,
            SchoolMembership.role == RoleEnum.parent,
        )
    )

    if search:
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(UserProfile.full_name).like(term),
                func.lower(UserProfile.email).like(term),
            )
        )

    profiles = query.order_by(UserProfile.full_name).distinct().all()

    return ParentDirectoryList(
        parents=[
            ParentDirectoryRead(
                user_id=profile.id,
                full_name=profile.full_name,
                email=profile.email,
            )
            for profile in profiles
        ]
    )


# ---------------------------------------------------------------------------
# School admin: manage parent links
# ---------------------------------------------------------------------------


@router.post(
    "/{student_id}/parents",
    response_model=LinkedParentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Link a parent to a student (school admin only)",
)
def link_parent(
    student_id: uuid.UUID,
    payload: ParentLinkCreate,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> LinkedParentRead:
    # The student determines the school, so a client cannot nominate a school
    # it does not administer.
    school = resolve_admin_school_for_student(db, user, student_id)
    parent = resolve_parent_profile(db, payload.parent_user_id, school.id)

    existing = (
        db.query(StudentParentLink)
        .filter(
            StudentParentLink.student_id == student_id,
            StudentParentLink.parent_user_id == parent.id,
        )
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This parent is already linked to this student.",
        )

    link = StudentParentLink(
        school_id=school.id,
        student_id=student_id,
        parent_user_id=parent.id,
    )
    db.add(link)
    try:
        db.commit()
    except Exception:  # noqa: BLE001 - unique constraint from a concurrent admin
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This parent is already linked to this student.",
        ) from None
    db.refresh(link)

    return LinkedParentRead(
        user_id=parent.id,
        full_name=parent.full_name,
        email=parent.email,
        linked_at=link.created_at,
    )


@router.get(
    "/{student_id}/parents",
    response_model=list[LinkedParentRead],
    summary="List a student's linked parents (school admin only)",
)
def list_parents(
    student_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> list[LinkedParentRead]:
    resolve_admin_school_for_student(db, user, student_id)

    # joinedload keeps this to a single query; the admin sees the guardian's
    # name and email so they can confirm they linked the right account.
    links = (
        db.query(StudentParentLink)
        .options(joinedload(StudentParentLink.parent))
        .filter(StudentParentLink.student_id == student_id)
        .order_by(StudentParentLink.created_at, StudentParentLink.id)
        .all()
    )

    return [
        LinkedParentRead(
            user_id=link.parent_user_id,
            full_name=link.parent.full_name,
            email=link.parent.email,
            linked_at=link.created_at,
        )
        for link in links
    ]


@router.delete(
    "/{student_id}/parents/{parent_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink a parent from a student (school admin only)",
)
def unlink_parent(
    student_id: uuid.UUID,
    parent_user_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> None:
    resolve_admin_school_for_student(db, user, student_id)

    link = (
        db.query(StudentParentLink)
        .filter(
            StudentParentLink.student_id == student_id,
            StudentParentLink.parent_user_id == parent_user_id,
        )
        .one_or_none()
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent link not found.",
        )

    # Only the link is removed. Notifications already delivered to the family
    # stay behind as an audit trail, and no attendance record is touched.
    db.delete(link)
    db.commit()


# ---------------------------------------------------------------------------
# Parent: own children
# ---------------------------------------------------------------------------


@me_router.get(
    "/students",
    response_model=ParentChildList,
    summary="List the students linked to the signed-in parent",
)
def list_my_students(
    school_id: uuid.UUID | None = Query(
        default=None,
        description="Restrict to one school. Must be a school the caller is a parent of.",
    ),
    user: AuthenticatedUser = Depends(require_parent),
    db: Session = Depends(get_db),
) -> ParentChildList:
    profile = require_profile(user)

    if school_id is not None:
        # Scopes the result and rejects a school the caller is not a parent of.
        resolve_parent_school(db, user, school_id)

    pairs = linked_students(db, profile, school_id)
    if not pairs:
        return ParentChildList(students=[])

    student_ids = [student.id for _, student in pairs]
    classes = {
        school_class.id: school_class
        for school_class in db.query(Class)
        .filter(Class.id.in_([student.class_id for _, student in pairs]))
        .all()
    }
    schools = {
        row.id: row
        for row in db.query(School).filter(School.id.in_([student.school_id for _, student in pairs])).all()
    }

    # Day 6: today's derived status for every linked child, in one query.
    #
    # The mobile children list shows today's status on each row. Doing that with
    # one request per child would be an N+1 against the most-used parent screen,
    # so the status is resolved here instead.
    #
    # "Today" is per school, so a parent whose children attend different schools
    # gets each child's own local day rather than one global date.
    today_by_school: dict[uuid.UUID, date] = {}
    for _, student in pairs:
        if student.school_id not in today_by_school:
            school_row = schools.get(student.school_id)
            if school_row is not None:
                today_by_school[student.school_id] = school_local_date(db, school_row)

    today_status: dict[uuid.UUID, str] = {}
    wanted_dates = set(today_by_school.values())
    if wanted_dates:
        records = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.student_id.in_(student_ids),
                AttendanceRecord.attendance_date.in_(wanted_dates),
            )
            .all()
        )
        by_student = {record.student_id: record for record in records}
        for student_id in student_ids:
            record = by_student.get(student_id)
            if record is not None:
                today_status[student_id] = derive_status(
                    record.arrival_at, record.departure_at
                ).value

    return ParentChildList(
        students=[
            ParentChildRead(
                student_id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                class_name=classes[student.class_id].name
                if student.class_id in classes
                else None,
                section=classes[student.class_id].section
                if student.class_id in classes
                else None,
                school_id=student.school_id,
                school_name=schools[student.school_id].name
                if student.school_id in schools
                else "",
                school_timezone=schools[student.school_id].timezone
                if student.school_id in schools
                else "Asia/Karachi",
                today_status=today_status.get(student.id, "absent"),
                today_status_date=today_by_school[student.school_id].isoformat()
                if student.school_id in today_by_school
                else None,
            )
            for _, student in pairs
        ]
    )


@me_router.get(
    "/students/{student_id}/attendance",
    response_model=ParentAttendanceHistory,
    summary="Attendance history for a child (parent view)",
)
def my_child_attendance(
    student_id: uuid.UUID,
    start_date: date | None = Query(default=None, description="YYYY-MM-DD, school timezone."),
    end_date: date | None = Query(default=None, description="YYYY-MM-DD, school timezone."),
    user: AuthenticatedUser = Depends(require_parent),
    db: Session = Depends(get_db),
) -> ParentAttendanceHistory:
    profile = require_profile(user)

    # 404 for an unlinked student, so ids cannot be probed.
    student = resolve_linked_student(db, profile, student_id)

    school = db.query(School).filter(School.id == student.school_id).one_or_none()
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    # The school's own date decides the default window, exactly as in Day 4.
    today = school_local_date(db, school)
    start, end = validated_range(start_date, end_date, today)

    # Reuses the Day 4 history builder, so a day with no scans is reported as
    # ABSENT instead of being omitted.
    history = history_for_student(db, student.id, start, end)

    return ParentAttendanceHistory(
        student_id=student.id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        records=[
            ParentAttendanceDayRead(
                date=entry["date"].isoformat(),
                status=entry["status"].value,
                arrival_at=entry["arrival_at"],
                departure_at=entry["departure_at"],
                # Rendered server side in the school's timezone, so the app never
                # reformats a scan time using the phone's clock.
                arrival_time=(
                    format_occurrence_time(entry["arrival_at"], school)
                    if entry["arrival_at"]
                    else None
                ),
                departure_time=(
                    format_occurrence_time(entry["departure_at"], school)
                    if entry["departure_at"]
                    else None
                ),
            )
            for entry in history
        ],
    )


# ---------------------------------------------------------------------------
# Parent: notifications
# ---------------------------------------------------------------------------


def _own_notification(
    db: Session, profile_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    """Load one notification owned by this parent, else 404.

    The owner check is part of the lookup, so another parent's notification id
    is reported as missing rather than forbidden.
    """
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.parent_user_id == profile_id,
        )
        .one_or_none()
    )
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    return notification


def _render_notification(db: Session, notification: Notification) -> NotificationRead:
    """Build the read model, including the school-local occurrence time.

    `occurred_time` needs the school row, which `model_validate` cannot reach on
    its own. One school lookup per response is enough: a parent's notifications
    come from a small set of schools, so they are resolved in one query.
    """
    school = db.get(School, notification.school_id)
    payload = NotificationRead.model_validate(notification)
    if school is not None:
        payload.occurred_time = format_occurrence_time(notification.occurred_at, school)
    else:
        payload.occurred_time = ""
    return payload


def _render_notifications(
    db: Session, notifications: list[Notification]
) -> list[NotificationRead]:
    """Render a batch, resolving every distinct school in a single query."""
    if not notifications:
        return []

    schools = {
        row.id: row
        for row in db.query(School)
        .filter(School.id.in_({n.school_id for n in notifications}))
        .all()
    }
    rendered: list[NotificationRead] = []
    for notification in notifications:
        payload = NotificationRead.model_validate(notification)
        school = schools.get(notification.school_id)
        payload.occurred_time = (
            format_occurrence_time(notification.occurred_at, school)
            if school is not None
            else ""
        )
        rendered.append(payload)
    return rendered


@me_router.get(
    "/notifications",
    response_model=NotificationList,
    summary="List the signed-in parent's notifications",
)
def list_my_notifications(
    school_id: uuid.UUID | None = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(require_parent),
    db: Session = Depends(get_db),
) -> NotificationList:
    profile = require_profile(user)
    if school_id is not None:
        resolve_parent_school(db, user, school_id)

    query = db.query(Notification).filter(Notification.parent_user_id == profile.id)
    if school_id is not None:
        query = query.filter(Notification.school_id == school_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    notifications = (
        query.order_by(Notification.occurred_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return NotificationList(
        notifications=_render_notifications(db, notifications),
        unread_count=unread_count(db, profile.id, school_id),
    )


@me_router.get(
    "/notifications/unread-count",
    response_model=UnreadCount,
    summary="Unread notification count for the badge",
)
def my_unread_count(
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_parent),
    db: Session = Depends(get_db),
) -> UnreadCount:
    profile = require_profile(user)
    if school_id is not None:
        resolve_parent_school(db, user, school_id)
    return UnreadCount(unread_count=unread_count(db, profile.id, school_id))


@me_router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark one of the parent's notifications as read",
)
def mark_notification_read(
    notification_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_parent),
    db: Session = Depends(get_db),
) -> NotificationRead:
    profile = require_profile(user)
    notification = _own_notification(db, profile.id, notification_id)

    if notification.read_at is None:
        notification.read_at = utc_now()
        db.commit()
        db.refresh(notification)

    # Re-reading is a no-op that returns the same body, so a double tap in the
    # Flutter app is harmless.
    return _render_notification(db, notification)