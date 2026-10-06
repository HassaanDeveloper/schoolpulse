"""Day 7: prepare a fictional demonstration environment.

This is a LOCAL DEVELOPMENT TOOL. It is a script, not an HTTP endpoint: there
is no `/seed`, `/demo-login` or `/create-admin-without-auth` route anywhere in
the application, so it cannot be triggered over the network in production.

Safety rules enforced here:

* it refuses to run unless DATABASE_URL names a database the operator has
  explicitly opted in as a demo database, or `--allow-remote-demo-db` is
  passed with the schema name spelled out;
* it only ever creates or updates rows carrying the demo marker, so running it
  cannot damage unrelated data;
* it creates fictional people only. No real child's name, phone number or
  address is written.

Usage (local only):

    python prepare_demo.py --database-url sqlite:///./demo.db
    python prepare_demo.py --reset          # wipe demo rows, keep the accounts

Supabase note: the application's own tables live in the `auth` schema managed
by Supabase. Real user accounts must therefore be created through Supabase
Auth; this script creates the application-side rows (profiles, memberships,
classes, students, parent links) and prints the auth ids it expects.
"""

import argparse
import os
import sys

from sqlalchemy import create_engine, text
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
DEMO_PARENT_EMAIL = "demo.parent@example.test"
DEMO_ADMIN_EMAIL = "demo.admin@example.test"
DEMO_TEACHER_EMAIL = "demo.teacher@example.test"

# Every demo row carries this marker so cleanup is exact and never overreaches.
DEMO_MARKER = "schoolpulse-demo-v1"

# auth_user_id values are supplied by the operator after creating the accounts
# in Supabase Auth. They are not secrets; they are identifiers.
AUTH_USERS = {
    "admin": os.environ.get("DEMO_ADMIN_AUTH_ID", "demo-admin-auth-id"),
    "teacher": os.environ.get("DEMO_TEACHER_AUTH_ID", "demo-teacher-auth-id"),
    "parent": os.environ.get("DEMO_PARENT_AUTH_ID", "demo-parent-auth-id"),
}


def require_demo_database(database_url: str, allow_remote: bool) -> None:
    """Refuse to write to a database the operator has not designated as demo."""
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        return
    if not database_url.startswith(("postgresql://", "postgres://")):
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
    school = (
        db.query(School)
        .filter(School.name == DEMO_SCHOOL)
        .one_or_none()
    )
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


def reset_demo_attendance(db, student: Student) -> None:
    """Return the demo student to 'not scanned today' so the demo can be repeated.

    Only this student's rows are touched. Notifications created by those scans
    are removed with them, which is what stops a repeated demonstration from
    showing the parent three arrivals.
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

    require_demo_database(args.database_url, args.allow_remote_demo_db)
    if args.allow_remote_demo_db and not args.confirm_demo_database:
        raise SystemExit("--allow-remote-demo-db requires --confirm-demo-database.")
    if args.confirm_demo_database:
        confirm_database_name(args.database_url, args.confirm_demo_database)

    engine = create_engine(args.database_url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    try:
        school = upsert_school(db)
        school_class = upsert_class(db, school)
        student = upsert_student(db, school, school_class)

        admin = upsert_profile(db, AUTH_USERS["admin"], DEMO_ADMIN_EMAIL, "Demo Admin")
        teacher = upsert_profile(db, AUTH_USERS["teacher"], DEMO_TEACHER_EMAIL, "Demo Teacher")
        parent = upsert_profile(db, AUTH_USERS["parent"], DEMO_PARENT_EMAIL, "Demo Parent")

        upsert_membership(db, admin, school, RoleEnum.school_admin)
        upsert_membership(db, teacher, school, RoleEnum.teacher)
        upsert_membership(db, parent, school, RoleEnum.parent)

        upsert_parent_link(db, student, parent, school)

        cleared = 0
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
    print()
    print("Accounts (create these in Supabase Auth, then re-run with the ids):")
    print(f"  admin   {DEMO_ADMIN_EMAIL}    auth id -> {AUTH_USERS['admin']}")
    print(f"  teacher {DEMO_TEACHER_EMAIL}  auth id -> {AUTH_USERS['teacher']}")
    print(f"  parent  {DEMO_PARENT_EMAIL}   auth id -> {AUTH_USERS['parent']}")
    print()
    print("Next: sign in as the admin, open the student, generate the QR, then")
    print("sign in as the parent on a second device. No QR is generated here on")
    print("purpose: the demonstration must use a real credential from the real")
    print("generation endpoint, not a token printed by a script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())