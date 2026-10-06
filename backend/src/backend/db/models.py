import enum
import uuid as _uuid
from datetime import date, datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from backend.db.base import Base
from backend.db.types import GUID

DEFAULT_SCHOOL_TIMEZONE = "Asia/Karachi"


class RoleEnum(str, enum.Enum):
    school_admin = "school_admin"
    teacher = "teacher"
    parent = "parent"


class StudentStatusEnum(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class NotificationTypeEnum(str, enum.Enum):
    """Day 5: only arrival and departure notices.

    Absence, late and fee notices are deliberately absent — they belong to a
    later day.
    """

    arrival = "arrival"
    departure = "departure"


class NotificationStatusEnum(str, enum.Enum):
    """Delivery state of a notification.

    `sent` means "successfully created in SchoolPulse and visible in-app". It
    does NOT mean an external channel delivered anything: WhatsApp, SMS and
    push are planned, not implemented.
    """

    queued = "queued"
    sent = "sent"
    failed = "failed"


class School(Base):
    __tablename__ = "schools"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    timezone = Column(
        String(64),
        nullable=False,
        default=DEFAULT_SCHOOL_TIMEZONE,
        server_default=DEFAULT_SCHOOL_TIMEZONE,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    memberships = relationship(
        "SchoolMembership",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    classes = relationship(
        "Class",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    students = relationship(
        "Student",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    qr_credentials = relationship(
        "StudentQrCredential",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    attendance_records = relationship(
        "AttendanceRecord",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    parent_links = relationship(
        "StudentParentLink",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="school",
        cascade="all, delete-orphan",
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    auth_user_id = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    memberships = relationship(
        "SchoolMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent_links = relationship(
        "StudentParentLink",
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class SchoolMembership(Base):
    __tablename__ = "school_memberships"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(GUID(), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False)
    role = Column(SQLEnum(RoleEnum, name="roleenum"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    school = relationship("School", back_populates="memberships")
    user = relationship("UserProfile", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("school_id", "user_id", name="uq_membership_school_user"),
        Index("ix_membership_school_id", "school_id"),
        Index("ix_membership_user_id", "user_id"),
    )


class Class(Base):
    __tablename__ = "classes"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    section = Column(String(50), nullable=True)
    academic_year = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    school = relationship("School", back_populates="classes")
    students = relationship("Student", back_populates="class_")

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "name",
            "section",
            "academic_year",
            name="uq_class_school_name_section_year",
        ),
        Index("ix_class_school_id", "school_id"),
    )


class Student(Base):
    __tablename__ = "students"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(GUID(), ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False)
    admission_number = Column(String(50), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    status = Column(
        SQLEnum(StudentStatusEnum, name="studentstatusenum"),
        nullable=False,
        default=StudentStatusEnum.active,
        server_default=StudentStatusEnum.active.value,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    school = relationship("School", back_populates="students")
    class_ = relationship("Class", back_populates="students")
    qr_credentials = relationship(
        "StudentQrCredential",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    attendance_records = relationship(
        "AttendanceRecord",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    parent_links = relationship(
        "StudentParentLink",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="student",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("school_id", "admission_number", name="uq_student_school_admission"),
        Index("ix_student_school_id", "school_id"),
        Index("ix_student_class_id", "class_id"),
    )


class StudentQrCredential(Base):
    """An opaque, revocable QR credential for exactly one student.

    Only the SHA-256 hash of the credential is stored. The plaintext token is
    returned once, at generation time, and is never persisted or logged.
    """

    __tablename__ = "student_qr_credentials"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    student_id = Column(GUID(), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    student = relationship("Student", back_populates="qr_credentials")
    school = relationship("School", back_populates="qr_credentials")

    __table_args__ = (
        Index("ix_qr_credential_student_id", "student_id"),
        Index("ix_qr_credential_school_id", "school_id"),
        Index("ix_qr_credential_active", "student_id", "revoked_at"),
    )


class AttendanceRecord(Base):
    """At most one attendance record per student per school day.

    `arrival_at` and `departure_at` are stored as timezone-aware UTC timestamps;
    `attendance_date` is always calculated in the school's timezone.
    """

    __tablename__ = "attendance_records"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(GUID(), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    attendance_date = Column(Date, nullable=False)
    arrival_at = Column(DateTime(timezone=True), nullable=True)
    arrival_scanned_by = Column(GUID(), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True)
    departure_at = Column(DateTime(timezone=True), nullable=True)
    departure_scanned_by = Column(GUID(), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    school = relationship("School", back_populates="attendance_records")
    student = relationship("Student", back_populates="attendance_records")

    __table_args__ = (
        UniqueConstraint("student_id", "attendance_date", name="uq_attendance_student_date"),
        Index("ix_attendance_school_id", "school_id"),
        Index("ix_attendance_school_date", "school_id", "attendance_date"),
        Index("ix_attendance_student_id", "student_id"),
    )


class StudentParentLink(Base):
    """An explicit, school-scoped guardian relationship for one student.

    A parent cannot see a student until a school administrator creates this
    row, so access is granted by the school rather than claimed by the parent.
    Removing the link stops future access but deliberately keeps the
    notifications already produced, as an audit trail.
    """

    __tablename__ = "student_parent_links"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(GUID(), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    parent_user_id = Column(
        GUID(), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    school = relationship("School", back_populates="parent_links")
    student = relationship("Student", back_populates="parent_links")
    parent = relationship("UserProfile", back_populates="parent_links")

    __table_args__ = (
        # One guardian relationship per student/parent pair.
        UniqueConstraint("student_id", "parent_user_id", name="uq_student_parent_link"),
        Index("ix_parent_link_school_id", "school_id"),
        Index("ix_parent_link_student_id", "student_id"),
        Index("ix_parent_link_parent_user_id", "parent_user_id"),
    )


class Notification(Base):
    """An in-app notice addressed to one parent about one student.

    Day 5 delivers these in-app only. `status = sent` records that the notice
    exists in SchoolPulse; it is not a claim that WhatsApp, SMS or push
    delivered anything.

    `UNIQUE (parent_user_id, attendance_id, type)` is what makes a repeated QR
    scan harmless: at most one notice per parent, per attendance record, per
    notice type.
    """

    __tablename__ = "notifications"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    school_id = Column(GUID(), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)
    parent_user_id = Column(
        GUID(), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(GUID(), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    attendance_id = Column(
        GUID(), ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=True
    )
    type = Column(
        SQLEnum(NotificationTypeEnum, name="notificationtypeenum"), nullable=False
    )
    title = Column(String(120), nullable=False)
    message = Column(String(255), nullable=False)
    # When the attendance event happened, as opposed to `created_at`, which is
    # when this row was written. Ordering the inbox by the event keeps it in
    # step with the day's arrival and departure times.
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        SQLEnum(NotificationStatusEnum, name="notificationstatusenum"),
        nullable=False,
        default=NotificationStatusEnum.queued,
        server_default=NotificationStatusEnum.queued.value,
    )
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    school = relationship("School", back_populates="notifications")
    parent = relationship("UserProfile", back_populates="notifications")
    student = relationship("Student", back_populates="notifications")

    __table_args__ = (
        # Duplicate-scan protection.
        UniqueConstraint(
            "parent_user_id",
            "attendance_id",
            "type",
            name="uq_notification_parent_attendance_type",
        ),
        Index("ix_notification_parent_user_id", "parent_user_id"),
        Index("ix_notification_student_id", "student_id"),
        Index("ix_notification_school_id", "school_id"),
        Index("ix_notification_created_at", "created_at"),
        Index("ix_notification_status", "status"),
    )