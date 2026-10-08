"""Prepare a fictional demonstration environment (LOCAL DEVELOPMENT TOOL).

This is a script, not an HTTP endpoint: there is no `/seed`, `/demo-login` or
`/create-admin-without-auth` route anywhere in the application, so it cannot
be triggered over the network in production.

Safety rules enforced here:

* it refuses to write to a hosted PostgreSQL database unless the operator
  passes `--allow-remote-demo-db` AND `--confirm-demo-database <name>`;
* it only creates or updates the fictional demo rows (school, class, student,
  profiles, memberships, parent link); it never deletes anything except the
  demo student's attendance when `--reset` is passed;
* on PostgreSQL it never creates tables. Alembic is the only schema source of
  truth, so run `alembic upgrade head` first.

Real user accounts are created in Supabase Auth (Authentication > Users). This
script creates the application-side rows for them, using the Supabase user ids
you supply through environment variables.

Windows (cmd) example, run from the folder that contains pyproject.toml:

    set PYTHONPATH=src;.
    set DEMO_ADMIN_AUTH_ID=<User UID from Supabase>
    set DEMO_ADMIN_EMAIL=<the email you signed in with>
    python prepare_demo.py --allow-remote-demo-db --confirm-demo-database postgres

Optional extras: DEMO_TEACHER_AUTH_ID / DEMO_TEACHER_EMAIL and
DEMO_PARENT_AUTH_ID / DEMO_PARENT_EMAIL. Roles without an id are skipped.
"""

import argparse
import os
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.config import settings
from backend.db.base import Base
from backend.db.models import (
    Class,
    RoleEnum,
    School,
    SchoolMembership,
    Student,
    StudentParentLink,
    StudentStatusEnum,
    UserProfile,
)

DEMO_SCHOOL = "Karachi Model School"
DEMO_TIMEZONE = "Asia/Karachi"
DEMO_CLASS = "Grade 5"
DEMO_SECTION = "A"
DEMO_ADMISSION = "SP-DEMO-001"
DEMO_STUDENT_FIRST = "Ali"
DEMO_STUDENT_LAST = "Khan"

DEMO_PARENT_EMAIL = os.environ.get("DEMO_PARENT_EMAIL", "demo.parent@example.test")
DEMO_ADMIN_EMAIL = os.environ.get("DEMO_ADMIN_EMAIL", "demo.admin@example.test")
DEMO_TEACHER_EMAIL = os.environ.get("DEMO_TEACHER_EMAIL", "demo.teacher@example.test")

DEMO_MARKER = "schoolpulse-demo-v1"

# auth_user_id values are the "User UID" shown in Supabase > Authentication >
# Users. They are identifiers, not secrets.
AUTH_USERS = {
    "admin": os.environ.get("DEMO_ADMIN_AUTH_ID", "demo-admin-auth-id"),
    "teacher": os.environ.get("DEMO_TEACHER_AUTH_ID", "demo-teacher-auth-id"),
    "parent": os.environ.get("DEMO_PARENT_AUTH_ID", "demo-parent-auth-id"),
}
PROVIDED_AUTH_IDS = {
    "admin": bool(os.environ.get("DEMO_ADMIN_AUTH_ID")),
    "teacher": bool(os.environ.get("DEMO_TEACHER_AUTH_ID")),
    "parent": bool(os.environ.get("DEMO_PARENT_AUTH_ID")),
}


def normalize_database_url(database_url: str) -> str:
    """Use the psycopg (v3) driver for PostgreSQL URLs."""
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]
    return database_url


def require_demo_database(database_url: str, allow_remote: bool) -> None:
    """Refuse to write to a database the operator has not designated as demo."""
    if database_url.startswith("sqlite"):
        return
    if not database_url.startswith(("postgresql", "postgres")):
        raise SystemExit(f"Refusing to use an unrecognised DATABASE_URL: {database_url[:12]}...")
    if not allow_remote:
        raise SystemExit(
            "Refusing to write demo data to a hosted PostgreSQL database.\n"
            "This script is a local development tool. If this database really is a\n"
            "throwaway demo database, re-run with:\n"
            "    --allow-remote-demo-db --confirm-demo-database <database-name>"
        )


def confirm_database_name(database_url: str, expected: str) -> None:
    if expected.strip() != expected.strip().lower() or not expected.strip():
        raise SystemExit("--confirm-demo-database needs the database name.")
    if expected.strip().lower() not in database_url.lower():
        raise SystemExit(
            f"--confirm-demo-database '{expected}' does not appear in the DATABASE_URL.\n"
            "Refusing to continue."
        )


def upsert_school(db, timezone_name: str = DEMO_TIMEZONE) -> School:
    school = db.query(School).filter(School.name == DEMO_SCHOOL).one_or_none()
    if school is None:
        school = School(
            name=DEMO_SCHOOL,
            slug=f"demo-{DEMO_MARKER}",
            timezone=timezone_name,
        )
        db.add(school)
        db.commit()
        db.refresh(school)
    return school


def upsert_membership(db, profile: UserProfile, school: School, role: RoleEnum) -> None:
    existing = (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.school_id == school.id,
            SchoolMembership.user_id == profile.id,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(SchoolMembership(school_id=school.id, user_id=profile.id, role=role))
        db.commit()


def upsert_profile(db, auth_user_id: str, email: str, full_name: str) -> UserProfile:
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.auth_user_id == auth_user_id)
        .one_or_none()
    )
    if profile is None:
        profile = UserProfile(auth_user_id=auth_user_id, email=email, full_name=full_name)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def upsert_class(db, school: School) -> Class:
    existing = (
        db.query(Class)
        .filter(
            Class.school_id == school.id,
            Class.name == DEMO_CLASS,
            Class.section == DEMO_SECTION,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    school_class = Class(
        school_id=school.id,
        name=DEMO_CLASS,
        section=DEMO_SECTION,
        academic_year="2026",
    )
    db.add(school_class)
    db.commit()
    db.refresh(school_class)
    return school_class


def upsert_student(db, school: School, school_class: Class) -> Student:
    existing = (
        db.query(Student)
        .filter(Student.school_id == school.id, Student.admission_number == DEMO_ADMISSION)
        .one_or_none()
    )
    if existing is not None:
        return existing
    student = Student(
        school_id=school.id,
        class_id=school_class.id,
        admission_number=DEMO_ADMISSION,
        first_name=DEMO_STUDENT_FIRST,
        last_name=DEMO_STUDENT_LAST,
        status=StudentStatusEnum.active,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def upsert_parent_link(db, student: Student, parent: UserProfile, school: School) -> None:
    existing = (
        db.query(StudentParentLink)
        .filter(
            StudentParentLink.student_id == student.id,
            StudentParentLink.parent_user_id == parent.id,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(
            StudentParentLink(
                school_id=school.id,
                student_id=student.id,
                parent_user_id=parent.id,
            )
        )
        db.commit()


def reset_demo_attendance(db, student: Student) -> int:
    """Return the demo student to 'not scanned today' so the demo can be repeated.

    Only this student's rows are touched. Notifications created by those scans
    are removed with them, so a repeated demonstration does not show the parent
    several arrivals.
    """
    from backend.db.models import AttendanceRecord, Notification

    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .all()
    )
    record_ids = [r.id for r in records]
    if record_ids:
        db.query(Notification).filter(
            Notification.attendance_id.in_(record_ids)
        ).delete(synchronize_session=False)
        db.query(AttendanceRecord).filter(
            AttendanceRecord.id.in_(record_ids)
        ).delete(synchronize_session=False)
        db.commit()
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
        help="Target database. Defaults to the configured DATABASE_URL.",
    )
    parser.add_argument(
        "--allow-remote-demo-db",
        action="store_true",
        help="Permit a hosted PostgreSQL database (still requires --confirm-demo-database).",
    )
    parser.add_argument(
        "--confirm-demo-database",
        default="",
        help="The database name, spelled out, for a hosted database.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo student's attendance and notifications before seeding.",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("No DATABASE_URL supplied and none configured.")

    database_url = normalize_database_url(args.database_url)
    is_sqlite = database_url.startswith("sqlite")

    require_demo_database(database_url, args.allow_remote_demo_db)
    if args.allow_remote_demo_db and not args.confirm_demo_database:
        raise SystemExit("--allow-remote-demo-db requires --confirm-demo-database.")
    if args.confirm_demo_database:
        confirm_database_name(database_url, args.confirm_demo_database)

    if not is_sqlite:
        if not PROVIDED_AUTH_IDS["admin"]:
            raise SystemExit(
                "Set DEMO_ADMIN_AUTH_ID to the User UID of your Supabase user\n"
                "(Supabase > Authentication > Users > click the user > User UID)."
            )
        for role, value in AUTH_USERS.items():
            if PROVIDED_AUTH_IDS[role]:
                try:
                    uuid.UUID(value)
                except ValueError:
                    raise SystemExit(f"DEMO_{role.upper()}_AUTH_ID is not a valid UUID: {value!r}")

    engine_kwargs = {"future": True}
    if is_sqlite:
        engine = create_engine(database_url, **engine_kwargs)
        # Local throwaway SQLite database only. PostgreSQL schema comes from Alembic.
        Base.metadata.create_all(engine)
    else:
        # Supabase poolers do not support server-side prepared statements.
        engine = create_engine(
            database_url, connect_args={"prepare_threshold": None}, **engine_kwargs
        )

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    created_roles = []
    cleared = 0
    try:
        school = upsert_school(db)
        school_class = upsert_class(db, school)
        student = upsert_student(db, school, school_class)

        if is_sqlite or PROVIDED_AUTH_IDS["admin"]:
            admin = upsert_profile(db, AUTH_USERS["admin"], DEMO_ADMIN_EMAIL, "Demo Admin")
            upsert_membership(db, admin, school, RoleEnum.school_admin)
            created_roles.append("admin")

        if is_sqlite or PROVIDED_AUTH_IDS["teacher"]:
            teacher = upsert_profile(db, AUTH_USERS["teacher"], DEMO_TEACHER_EMAIL, "Demo Teacher")
            upsert_membership(db, teacher, school, RoleEnum.teacher)
            created_roles.append("teacher")

        if is_sqlite or PROVIDED_AUTH_IDS["parent"]:
            parent = upsert_profile(db, AUTH_USERS["parent"], DEMO_PARENT_EMAIL, "Demo Parent")
            upsert_membership(db, parent, school, RoleEnum.parent)
            upsert_parent_link(db, student, parent, school)
            created_roles.append("parent")

        if args.reset:
            cleared = reset_demo_attendance(db, student)

        # Captured before the session closes; the ORM detaches on close.
        student_id = str(student.id)
    finally:
        db.close()
        engine.dispose()

    print()
    print("SchoolPulse demonstration environment ready (all data fictional)")
    print("=" * 62)
    print(f"School          : {DEMO_SCHOOL}  [{DEMO_TIMEZONE}]")
    print(f"Class           : {DEMO_CLASS} - {DEMO_SECTION}")
    print(f"Student         : {DEMO_STUDENT_FIRST} {DEMO_STUDENT_LAST}")
    print(f"Admission number: {DEMO_ADMISSION}")
    print(f"Student id      : {student_id}")
    print(f"Attendance reset: {cleared} record(s) removed" if args.reset else "Attendance reset: not requested")
    print(f"Roles linked    : {', '.join(created_roles) if created_roles else 'none'}")
    print()
    print("Next: sign in with the admin account, open the student, generate the QR.")
    print("No QR is generated here on purpose: the demonstration must use a real")
    print("credential from the real generation endpoint, not a token printed by a script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
