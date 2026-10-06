import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-for-signing-tokens")

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.db import models  # noqa: F401
from backend.db.base import Base
from backend.db.models import (
    AttendanceRecord,
    RoleEnum,
    School,
    SchoolMembership,
    Student,
    UserProfile,
)
from backend.db.session import get_db
from backend.main import app

TEST_JWT_SECRET = "test-secret-for-signing-tokens"
SCHOOL_A = "11111111-1111-4111-8111-111111111111"
SCHOOL_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_token(user_id: str, email: str | None = None) -> str:
    claims = {
        "sub": user_id,
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "role": "authenticated",
        "exp": 9999999999,
    }
    if email:
        claims["email"] = email
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def seed_school(db, name: str = "Demo School") -> School:
    school = School(name=name, slug=unique_slug(db, name))
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


def unique_slug(db, name: str) -> str:
    slug = name.lower().replace(" ", "-")
    base = slug
    suffix = 1
    while db.query(School.id).filter(School.slug == slug).one_or_none() is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def seed_class(db, school: School, name: str = "Class 5", section: str = "A"):
    from backend.db.models import Class

    existing = (
        db.query(Class)
        .filter(
            Class.school_id == school.id,
            Class.name == name,
            Class.section == section,
            Class.academic_year == "2026",
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    school_class = Class(
        school_id=school.id,
        name=name,
        section=section,
        academic_year="2026",
    )
    db.add(school_class)
    db.commit()
    db.refresh(school_class)
    return school_class


def seed_student(
    db,
    school: School,
    school_class=None,
    admission_number: str = "ADM-001",
    first_name: str = "Ayesha",
    last_name: str = "Khan",
    status=None,
):
    from backend.db.models import Student, StudentStatusEnum

    if school_class is None:
        school_class = seed_class(db, school)

    student = Student(
        school_id=school.id,
        class_id=school_class.id,
        admission_number=admission_number,
        first_name=first_name,
        last_name=last_name,
        status=status or StudentStatusEnum.active,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def seed_user(
    db,
    auth_user_id: str,
    role: RoleEnum,
    school: School,
    email: str | None = None,
) -> UserProfile:
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.auth_user_id == auth_user_id)
        .one_or_none()
    )
    if profile is None:
        profile = UserProfile(auth_user_id=auth_user_id, email=email)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    existing_membership = (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.school_id == school.id,
            SchoolMembership.user_id == profile.id,
        )
        .one_or_none()
    )
    if existing_membership is None:
        db.add(
            SchoolMembership(school_id=school.id, user_id=profile.id, role=role)
        )
        db.commit()

    db.refresh(profile)
    return profile


def seed_attendance(
    db,
    student: Student,
    attendance_date,
    arrival_at=None,
    departure_at=None,
    scanned_by=None,
) -> AttendanceRecord:
    """Create an attendance row directly, for setting up Day 4 scenarios.

    `arrival_at` defaults to an aware UTC instant on the given date when it is
    not supplied. `departure_at` stays None (a PRESENT day) unless given, or
    unless `scanned_by` is passed, which implies a completed day.
    """
    base = datetime.combine(attendance_date, time(8, 0), tzinfo=timezone.utc)
    if arrival_at is None:
        arrival_at = base
    if departure_at is None and scanned_by is not None:
        departure_at = base + timedelta(hours=6)

    record = AttendanceRecord(
        school_id=student.school_id,
        student_id=student.id,
        attendance_date=attendance_date,
        arrival_at=arrival_at,
        arrival_scanned_by=scanned_by,
        departure_at=departure_at,
        departure_scanned_by=scanned_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def seed_class_named(db, school: School, name: str, section: str | None = None):
    """A class with an explicit name/section, for class-filter tests."""
    from backend.db.models import Class

    school_class = Class(
        school_id=school.id,
        name=name,
        section=section,
        academic_year="2026",
    )
    db.add(school_class)
    db.commit()
    db.refresh(school_class)
    return school_class


class frozen_clock:
    """Pin `attendance_clock.utc_now()` to a fixed instant.

    Day 4 endpoints call `school_local_date()`, which resolves `utc_now` from
    the `attendance_clock` module at call time, so patching that one attribute
    is enough to control the school's local date.
    """

    def __init__(self, moment: datetime):
        self.moment = moment

    def __enter__(self):
        from backend.services import attendance_clock

        self._original = attendance_clock.utc_now
        attendance_clock.utc_now = lambda: self.moment
        return self

    def __exit__(self, *exc):
        from backend.services import attendance_clock

        attendance_clock.utc_now = self._original
        return False


class frozen_scan_clock:
    """Pin the clock the attendance *scan* path reads.

    `POST /attendance/scan` needs both `attendance_clock.utc_now` (for the
    school's local date) and `backend.api.attendance.utc_now` (for the stored
    scan instant), because the router imports the function by name. Day 3 and
    Day 5 notification tests both depend on the recorded timestamp, so the
    helper lives here rather than in one test module.
    """

    def __init__(self, moment: datetime):
        self.moment = moment
        self._targets: list[tuple[object, object]] = []

    def __enter__(self):
        from backend.api import attendance as attendance_api
        from backend.services import attendance_clock

        moment = self.moment

        def fake_utc_now() -> datetime:
            return moment

        for module in (attendance_clock, attendance_api):
            self._targets.append((module, module.utc_now))
            module.utc_now = fake_utc_now
        return self

    def __exit__(self, *exc):
        for module, original in reversed(self._targets):
            module.utc_now = original
        self._targets.clear()
        return False


def seed_parent_link(
    db,
    student: Student,
    parent: UserProfile,
    school_id=None,
):
    """Grant a parent access to a student, bypassing the admin API.

    Used where the link itself is not the behaviour under test, so the suite
    can keep its Day 3 and Day 4 shape.
    """
    from backend.db.models import StudentParentLink

    link = StudentParentLink(
        school_id=school_id or student.school_id,
        student_id=student.id,
        parent_user_id=parent.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link