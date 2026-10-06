"""Day 5 request/response schemas for parent linking and notifications.

Every parent-facing schema is deliberately narrow. A parent sees their own
children and their own notices — never staff identity, QR credentials, tokens,
or another family's data.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.db.models import NotificationStatusEnum, NotificationTypeEnum


class ParentLinkCreate(BaseModel):
    """Admin request to grant a parent access to one student."""

    parent_user_id: uuid.UUID = Field(
        description="user_profiles.id of an existing account holding a parent membership."
    )


class LinkedParentRead(BaseModel):
    """A guardian shown to a school administrator.

    `user_id` is the profile id used by the link API; `full_name` and `email`
    are included so an administrator can recognise the right account.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    full_name: str | None = None
    email: str | None = None
    linked_at: datetime | None = None


class ParentDirectoryRead(BaseModel):
    """A parent account an administrator may choose to link.

    Day 6 addition. This is a **directory of existing accounts**, not a
    creation endpoint: SchoolPulse has no public parent registration, so the
    only safe way for an administrator to pick a guardian is to search the
    accounts that already hold a `parent` membership in their own school.

    Deliberately minimal — the id, a display name and an email so an
    administrator can recognise the right account. No attendance, no children,
    no notification state, and nothing from another school.
    """

    user_id: uuid.UUID
    full_name: str | None = None
    email: str | None = None


class ParentDirectoryList(BaseModel):
    parents: list[ParentDirectoryRead]


class ParentChildRead(BaseModel):
    """A student as seen by their own parent.

    Only display fields a parent legitimately needs: no date of birth, no
    gender, no admission number.
    """

    model_config = ConfigDict(from_attributes=True)

    student_id: uuid.UUID
    first_name: str
    last_name: str
    class_name: str | None = None
    section: str | None = None
    school_id: uuid.UUID
    school_name: str
    school_timezone: str

    # Day 6: the child's derived status for the school's local today, so the
    # children list can show it without a request per child. Defaults to
    # `absent`, which is what a day with no attendance record means.
    today_status: str = "absent"

    # The school's local date that `today_status` refers to. The app renders
    # this date rather than its own, so a parent in another timezone is never
    # shown the wrong day.
    today_status_date: str | None = None


class ParentChildList(BaseModel):
    students: list[ParentChildRead]


class ParentAttendanceDayRead(BaseModel):
    """One day of a child's attendance, parent view.

    Intentionally excludes `scanned_by`, so the scanning staff member is never
    disclosed to a family.
    """

    date: str = Field(description="Attendance date (YYYY-MM-DD) in the school's timezone.")
    status: str = Field(
        description="present, absent or completed, as derived by the shared Day 4 rules."
    )
    arrival_at: datetime | None = None
    departure_at: datetime | None = None
    arrival_time: str | None = Field(
        default=None,
        description="Arrival time already rendered in the school's timezone, e.g. '8:04 AM'.",
    )
    departure_time: str | None = Field(
        default=None,
        description="Departure time already rendered in the school's timezone, e.g. '4:30 PM'.",
    )


class ParentAttendanceHistory(BaseModel):
    student_id: uuid.UUID
    start_date: str
    end_date: str
    records: list[ParentAttendanceDayRead]


class NotificationRead(BaseModel):
    """One in-app notice as shown to its addressee.

    `occurred_at` is the attendance event time in UTC, so the Flutter app can
    show a real timestamp instead of parsing the human-readable `message`.

    `occurred_time` is that same instant already rendered in the school's
    timezone. The app shows this rather than converting `occurred_at` on the
    device, which would report a time the school never recorded for a parent
    travelling in another timezone.

    It defaults to empty because it cannot come from the ORM row; the routes
    populate it, and an empty value means the school row could not be resolved.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationTypeEnum
    title: str
    message: str
    status: NotificationStatusEnum
    occurred_at: datetime
    occurred_time: str = ""
    read_at: datetime | None = None
    created_at: datetime | None = None


class NotificationList(BaseModel):
    notifications: list[NotificationRead]
    unread_count: int


class UnreadCount(BaseModel):
    unread_count: int