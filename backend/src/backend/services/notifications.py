"""Day 5 notification creation for attendance events.

Design constraints that shape this module:

* **In-app only.** `InAppNotificationProvider` is the sole provider. WhatsApp,
  SMS, email and push are planned, so the provider seam exists now and stays
  one class wide.
* **Same transaction as the scan.** The service is called by
  `POST /attendance/scan` before that request commits, so the attendance row
  and the notices derived from it land together.
* **A notice must never cost an attendance record.** Provider failures are
  caught per notice and recorded as `status = failed`; the scan still commits.
* **Idempotent.** A repeat scan of the same event produces no second notice,
  enforced first by an existence check and then by a unique constraint.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    AttendanceRecord,
    Notification,
    NotificationStatusEnum,
    NotificationTypeEnum,
    School,
    Student,
    StudentParentLink,
)
from backend.services.attendance_clock import get_timezone

logger = logging.getLogger(__name__)

ARRIVAL_TITLE = "Arrival recorded"
DEPARTURE_TITLE = "Departure recorded"


class NotificationDeliveryError(Exception):
    """A provider refused to deliver one notice.

    Raised by a provider and caught by the caller so the attendance record is
    unaffected.
    """


class NotificationProvider:
    """Base shape for a delivery channel.

    `name` ends up in logs and makes it obvious later which channel a `sent`
    status came from. Deliberately a plain class rather than a dataclass: a
    dataclass here would generate an `__init__` that every subclass inherits,
    silently shadowing each subclass's own `name`.
    """

    name = "base"

    def deliver(
        self,
        notification: Notification,
        *,
        student: Student,
        school: School,
        occurred_at: datetime,
    ) -> None:
        raise NotImplementedError

    def mark_sent(self, notification: Notification) -> None:
        notification.status = NotificationStatusEnum.sent

    def mark_failed(self, notification: Notification) -> None:
        notification.status = NotificationStatusEnum.failed


class InAppNotificationProvider(NotificationProvider):
    """Delivery is "the row exists and is visible in the parent's inbox".

    There is no external call and nothing to retry, so `sent` simply records
    that the in-app notice was produced. This keeps the status vocabulary
    meaningful for the external providers Day 6 adds.
    """

    name = "in_app"

    def deliver(
        self,
        notification: Notification,
        *,
        student: Student,
        school: School,
        occurred_at: datetime,
    ) -> None:
        self.mark_sent(notification)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise a timestamp to an aware UTC instant.

    SQLite hands back naive datetimes, so an already-stored scan time must be
    assumed to be UTC rather than rejected.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_occurrence_time(occurred_at: datetime, school: School) -> str:
    """Render the scan time in the school's own timezone.

    Example: `8:04 AM`. The message is built on the server from the stored
    timestamp so the Flutter app never recomputes the moment from its own
    device clock.
    """
    local = _as_utc(occurred_at).astimezone(get_timezone(school.timezone))
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d} {local.strftime('%p')}"


def build_title(notification_type: NotificationTypeEnum) -> str:
    return ARRIVAL_TITLE if notification_type == NotificationTypeEnum.arrival else DEPARTURE_TITLE


def build_message(
    notification_type: NotificationTypeEnum,
    *,
    student: Student,
    school: School,
    occurred_at: datetime,
) -> str:
    """Build a data-minimal message.

    Only the child's name and the school-local time appear. Nothing about
    classmates, staff, the scanning device, tokens or QR credentials.
    """
    when = format_occurrence_time(occurred_at, school)
    student_name = f"{student.first_name} {student.last_name}".strip()
    if notification_type == NotificationTypeEnum.arrival:
        return f"{student_name} arrived at {school.name} at {when}."
    return f"{student_name} departed {school.name} at {when}."


def linked_parent_ids(db: Session, student: Student) -> list[uuid.UUID]:
    """Parent profile ids linked to this student in the student's school.

    An empty list is normal and must not be an error: not every student has a
    parent registered yet.
    """
    return [
        parent_user_id
        for (parent_user_id,) in db.execute(
            select(StudentParentLink.parent_user_id).where(
                StudentParentLink.school_id == student.school_id,
                StudentParentLink.student_id == student.id,
            )
        ).all()
    ]


def _existing_notice_ids(
    db: Session,
    *,
    attendance_id: uuid.UUID,
    notification_type: NotificationTypeEnum,
) -> set[uuid.UUID]:
    """Parents who already have this exact notice."""
    return {
        parent_user_id
        for (parent_user_id,) in db.execute(
            select(Notification.parent_user_id).where(
                Notification.attendance_id == attendance_id,
                Notification.type == notification_type,
            )
        ).all()
    }


def notify_attendance_event(
    db: Session,
    *,
    record: AttendanceRecord,
    student: Student,
    school: School,
    notification_type: NotificationTypeEnum,
    provider: NotificationProvider | None = None,
) -> list[Notification]:
    """Create one notice per linked parent for an arrival or departure.

    Call this inside the scan's transaction, before it commits. Returns the
    notices created, which is empty when the student has no linked parents or
    when every notice already existed.
    """
    provider = provider or InAppNotificationProvider()
    occurred_at = _as_utc(
        record.arrival_at if notification_type == NotificationTypeEnum.arrival else record.departure_at
    )
    if occurred_at is None:
        return []

    parent_ids = linked_parent_ids(db, student)
    if not parent_ids:
        logger.debug(
            "no linked parents for student %s; attendance recorded without notification",
            student.id,
        )
        return []

    already_notified = _existing_notice_ids(
        db,
        attendance_id=record.id,
        notification_type=notification_type,
    )

    title = build_title(notification_type)
    message = build_message(
        notification_type,
        student=student,
        school=school,
        occurred_at=occurred_at,
    )

    created: list[Notification] = []
    for parent_user_id in parent_ids:
        if parent_user_id in already_notified:
            continue

        notification = Notification(
            school_id=student.school_id,
            parent_user_id=parent_user_id,
            student_id=student.id,
            attendance_id=record.id,
            type=notification_type,
            title=title,
            message=message,
            occurred_at=occurred_at,
            status=NotificationStatusEnum.queued,
        )

        # The savepoint keeps the surrounding attendance transaction alive if
        # the unique constraint fires from a concurrent scan.
        savepoint = db.begin_nested()
        try:
            db.add(notification)
            db.flush()
        except IntegrityError:
            savepoint.rollback()
            logger.info(
                "notification already exists for parent %s, attendance %s",
                parent_user_id,
                record.id,
            )
            continue
        savepoint.commit()

        try:
            provider.deliver(
                notification,
                student=student,
                school=school,
                occurred_at=occurred_at,
            )
        except Exception:  # noqa: BLE001 - a channel must never cost attendance
            logger.exception(
                "notification provider %s failed for parent %s; attendance unaffected",
                provider.name,
                parent_user_id,
            )
            provider.mark_failed(notification)

        created.append(notification)

    return created


def unread_count(db: Session, parent_user_id: uuid.UUID, school_id: uuid.UUID | None = None) -> int:
    """Number of notices the parent has not opened yet."""
    query = db.query(func.count(Notification.id)).filter(
        Notification.parent_user_id == parent_user_id,
        Notification.read_at.is_(None),
    )
    if school_id is not None:
        query = query.filter(Notification.school_id == school_id)
    return query.scalar() or 0