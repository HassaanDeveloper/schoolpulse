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


class RoleEnum(str, enum.Enum):
    school_admin = "school_admin"
    teacher = "teacher"
    parent = "parent"


class StudentStatusEnum(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class School(Base):
    __tablename__ = "schools"

    id = Column(GUID(), primary_key=True, default=_uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
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

    __table_args__ = (
        UniqueConstraint("school_id", "admission_number", name="uq_student_school_admission"),
        Index("ix_student_school_id", "school_id"),
        Index("ix_student_class_id", "class_id"),
    )