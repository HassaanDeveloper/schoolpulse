from datetime import date, datetime, timedelta, timezone

import pytest

from backend.db.models import (
    AttendanceRecord,
    RoleEnum,
    StudentStatusEnum,
)
from backend.services import attendance_clock
from tests.conftest import (
    auth,
    frozen_scan_clock as freeze,
    make_token,
    seed_school,
    seed_student,
    seed_user,
)

SCAN_URL = "/api/v1/attendance/scan"


@pytest.fixture()
def school(db_session):
    return seed_school(db_session, "Scan School")


def scanner_headers(db, school, user_id="teacher-1", role=RoleEnum.teacher):
    seed_user(db, user_id, role, school)
    return auth(make_token(user_id))


def issue_credential(client, db, school, student, user_id="admin-1"):
    seed_user(db, user_id, RoleEnum.school_admin, school)
    response = client.post(
        f"/api/v1/students/{student.id}/qr", headers=auth(make_token(user_id))
    )
    assert response.status_code == 201, response.text
    return response.json()["credential"]


def scan(client, headers, credential):
    return client.post(SCAN_URL, json={"credential": credential}, headers=headers)


def only_record(db, student):
    return (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .one_or_none()
    )


# ---------- authorization ----------


def test_unauthenticated_scan_returns_401(client, db_session, school):
    assert client.post(SCAN_URL, json={"credential": "anything"}).status_code == 401


def test_parent_scan_returns_403(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    response = scan(client, auth(make_token("parent-1")), credential)

    assert response.status_code == 403
    assert only_record(db_session, student) is None, "parent must not record attendance"


def test_teacher_scan_succeeds(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    response = scan(client, scanner_headers(db_session, school), credential)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ARRIVAL_RECORDED"


def test_admin_scan_succeeds(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    headers = scanner_headers(db_session, school, "admin-2", RoleEnum.school_admin)
    assert scan(client, headers, credential).json()["status"] == "ARRIVAL_RECORDED"


def test_empty_credential_returns_422(client, db_session, school):
    headers = scanner_headers(db_session, school)
    assert client.post(SCAN_URL, json={"credential": ""}, headers=headers).status_code == 422


def test_credential_field_is_required(client, db_session, school):
    headers = scanner_headers(db_session, school)
    assert client.post(SCAN_URL, json={}, headers=headers).status_code == 422


def test_client_cannot_supply_student_or_date(client, db_session, school):
    """The client must not be able to influence who is marked present."""
    student = seed_student(db_session, school)
    other_student = seed_student(
        db_session, school, admission_number="ADM-999", first_name="Impostor"
    )
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    response = client.post(
        SCAN_URL,
        json={
            "credential": credential,
            "student_id": str(other_student.id),
            "attendance_date": "1999-01-01",
            "school_id": str(school.id),
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["student"]["id"] == str(student.id)
    assert body["attendance_date"] != "1999-01-01"
    assert only_record(db_session, other_student) is None


# ---------- credential validation ----------


def test_unknown_credential_returns_404(client, db_session, school):
    headers = scanner_headers(db_session, school)
    response = scan(client, headers, "not-a-real-credential")
    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid or inactive QR credential."


def test_invalid_and_revoked_credential_are_indistinguishable(client, db_session, school):
    """Unknown vs revoked must not leak which tokens ever existed."""
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    unknown = scan(client, scanner_headers(db_session, school), "totally-bogus-token")
    assert unknown.status_code == 404

    client.delete(
        f"/api/v1/students/{student.id}/qr",
        headers=auth(make_token("admin-1")),
    )
    revoked = scan(client, scanner_headers(db_session, school), credential)

    assert revoked.status_code == unknown.status_code
    assert revoked.json() == unknown.json()


# ---------- core arrival / departure sequence ----------


def test_arrival_then_departure_then_already(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    first = scan(client, headers, credential)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["status"] == "ARRIVAL_RECORDED"
    assert first_body["student"]["name"] == "Ayesha Khan"
    assert first_body["student"]["admission_number"] == student.admission_number
    assert first_body["arrival_at"] is not None
    assert first_body["departure_at"] is None
    assert first_body["timestamp"] == first_body["arrival_at"]

    second = scan(client, headers, credential)
    second_body = second.json()
    assert second_body["status"] == "DEPARTURE_RECORDED"
    assert second_body["arrival_at"] == first_body["arrival_at"]
    assert second_body["departure_at"] is not None
    assert second_body["timestamp"] == second_body["departure_at"]

    third = scan(client, headers, credential)
    third_body = third.json()
    assert third_body["status"] == "ALREADY_RECORDED"
    assert third_body["arrival_at"] == first_body["arrival_at"]
    assert third_body["departure_at"] == second_body["departure_at"]


def test_repeat_scans_never_create_extra_records(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    for _ in range(10):
        scan(client, headers, credential)

    assert (
        db_session.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .count()
        == 1
    )


def test_already_recorded_does_not_mutate_timestamps(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    scan(client, headers, credential)
    scan(client, headers, credential)
    before = only_record(db_session, student)
    snapshot = (before.arrival_at, before.departure_at)

    for _ in range(3):
        assert scan(client, headers, credential).json()["status"] == "ALREADY_RECORDED"

    after = only_record(db_session, student)
    assert (after.arrival_at, after.departure_at) == snapshot


def test_arrival_is_recorded_before_departure(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    scan(client, headers, credential)
    record = only_record(db_session, student)
    assert record.arrival_at is not None
    assert record.departure_at is None

    scan(client, headers, credential)
    record = only_record(db_session, student)
    assert record.arrival_at is not None
    assert record.departure_at is not None
    assert record.departure_at >= record.arrival_at


def test_scan_records_scanner_identity(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)
    scanner = seed_user(db_session, "teacher-x", RoleEnum.teacher, school)
    headers = auth(make_token("teacher-x"))

    scan(client, headers, credential)
    record = only_record(db_session, student)
    assert record.arrival_scanned_by == scanner.id
    assert record.departure_scanned_by is None

    scan(client, headers, credential)
    record = only_record(db_session, student)
    assert record.arrival_scanned_by == scanner.id
    assert record.departure_scanned_by == scanner.id


def test_record_is_attributed_to_student_school(client, db_session, school):
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    scan(client, scanner_headers(db_session, school), credential)

    record = only_record(db_session, student)
    assert record.school_id == school.id
    assert record.student_id == student.id


# ---------- uniqueness ----------


def test_unique_constraint_exists_on_student_and_date(client, db_session, school):
    """The database, not just the endpoint, prevents duplicate daily rows."""
    student = seed_student(db_session, school)
    record = AttendanceRecord(
        school_id=school.id,
        student_id=student.id,
        attendance_date=date(2026, 3, 2),
        arrival_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    db_session.commit()

    duplicate = AttendanceRecord(
        school_id=school.id,
        student_id=student.id,
        attendance_date=date(2026, 3, 2),
        arrival_at=datetime.now(timezone.utc),
    )
    db_session.add(duplicate)

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_students_get_separate_daily_records(client, db_session, school):
    first = seed_student(db_session, school, admission_number="ADM-A")
    second = seed_student(db_session, school, admission_number="ADM-B", first_name="Bilal")
    admin = auth(make_token("admin-1"))
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)
    headers = scanner_headers(db_session, school)

    for student in (first, second):
        credential = client.post(
            f"/api/v1/students/{student.id}/qr", headers=admin
        ).json()["credential"]
        assert scan(client, headers, credential).json()["status"] == "ARRIVAL_RECORDED"

    assert db_session.query(AttendanceRecord).count() == 2


# ---------- tenant isolation ----------


def test_cross_school_scan_returns_403(client, db_session):
    school_a = seed_school(db_session, "Alpha")
    school_b = seed_school(db_session, "Beta")
    student_b = seed_student(db_session, school_b, admission_number="ADM-B")

    seed_user(db_session, "admin-b", RoleEnum.school_admin, school_b)
    credential = client.post(
        f"/api/v1/students/{student_b.id}/qr", headers=auth(make_token("admin-b"))
    ).json()["credential"]

    seed_user(db_session, "teacher-a", RoleEnum.teacher, school_a)
    response = scan(client, auth(make_token("teacher-a")), credential)

    assert response.status_code == 403
    assert response.json()["detail"] == "This QR credential cannot be used at your school."
    assert only_record(db_session, student_b) is None


def test_scanner_with_membership_at_school_can_scan(client, db_session):
    school_a = seed_school(db_session, "Alpha")
    school_b = seed_school(db_session, "Beta")
    student_a = seed_student(db_session, school_a, admission_number="ADM-A")

    seed_user(db_session, "admin-a", RoleEnum.school_admin, school_a)
    credential = client.post(
        f"/api/v1/students/{student_a.id}/qr", headers=auth(make_token("admin-a"))
    ).json()["credential"]

    # The same user is a teacher at school A and a parent at school B.
    seed_user(db_session, "multi", RoleEnum.teacher, school_a)
    seed_user(db_session, "multi", RoleEnum.parent, school_b)

    response = scan(client, auth(make_token("multi")), credential)
    assert response.status_code == 200
    assert response.json()["status"] == "ARRIVAL_RECORDED"


# ---------- inactive students ----------


@pytest.mark.parametrize(
    "student_status",
    [
        StudentStatusEnum.inactive,
    ],
)
def test_inactive_student_scan_returns_403(client, db_session, school, student_status):
    student = seed_student(db_session, school, status=student_status)
    credential = issue_credential(client, db_session, school, student)

    response = scan(client, scanner_headers(db_session, school), credential)

    assert response.status_code == 403
    assert response.json()["detail"] == "This student is inactive and cannot be marked present."
    assert only_record(db_session, student) is None


def test_student_reactivated_can_be_scanned_again(client, db_session, school):
    student = seed_student(db_session, school, status=StudentStatusEnum.inactive)
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    assert scan(client, headers, credential).status_code == 403

    student.status = StudentStatusEnum.active
    db_session.commit()

    assert scan(client, headers, credential).json()["status"] == "ARRIVAL_RECORDED"


# ---------- school timezone ----------


def test_attendance_date_uses_school_timezone(client, db_session, school):
    """A school ahead of UTC rolls the date over before the server does."""
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    school.timezone = "Pacific/Kiritimati"  # UTC+14
    db_session.commit()

    fake_utc = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)  # 2026-03-03 02:00 local
    with freeze(fake_utc):
        body = scan(client, scanner_headers(db_session, school), credential).json()

    assert body["attendance_date"] == "2026-03-03"


def test_attendance_date_uses_school_timezone_behind_utc(client, db_session, school):
    school.timezone = "Pacific/Honolulu"  # UTC-10
    db_session.commit()
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)

    fake_utc = datetime(2026, 3, 2, 2, 0, tzinfo=timezone.utc)  # 2026-03-01 16:00 local
    with freeze(fake_utc):
        body = scan(client, scanner_headers(db_session, school), credential).json()

    assert body["attendance_date"] == "2026-03-01"


def test_different_school_days_produce_separate_records(client, db_session, school):
    """Scanning across a local midnight starts a new daily record."""
    student = seed_student(db_session, school)
    credential = issue_credential(client, db_session, school, student)
    headers = scanner_headers(db_session, school)

    with freeze(datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)):
        assert scan(client, headers, credential).json()["status"] == "ARRIVAL_RECORDED"

    with freeze(datetime(2026, 3, 2, 11, 0, tzinfo=timezone.utc)):
        assert scan(client, headers, credential).json()["status"] == "DEPARTURE_RECORDED"

    with freeze(datetime(2026, 3, 3, 9, 0, tzinfo=timezone.utc)):
        assert scan(client, headers, credential).json()["status"] == "ARRIVAL_RECORDED"

    assert db_session.query(AttendanceRecord).count() == 2


# ---------- helpers ----------


def test_utc_now_is_timezone_aware():
    assert attendance_clock.utc_now().tzinfo is not None
    assert attendance_clock.utc_now().utcoffset() == timedelta(0)


# ---------- timezone helpers ----------


def test_get_timezone_defaults_to_karachi_when_missing():
    assert attendance_clock.get_timezone(None).key == "Asia/Karachi"
    assert attendance_clock.get_timezone("").key == "Asia/Karachi"


def test_get_timezone_falls_back_on_unknown_zone():
    assert attendance_clock.get_timezone("Not/ARealZone").key == "Asia/Karachi"


def test_get_timezone_resolves_valid_zone():
    assert attendance_clock.get_timezone("Pacific/Kiritimati").key == "Pacific/Kiritimati"


def test_school_local_now_uses_school_timezone(db_session):
    school = seed_school(db_session, "Karachi TZ")
    moment = datetime(2026, 3, 2, 19, 0, tzinfo=timezone.utc)  # 2026-03-03 00:00 PKT

    with freeze(moment):
        local = attendance_clock.school_local_now(db_session, school)

    assert local.date() == date(2026, 3, 3)
    assert local.tzinfo is not None


def test_school_local_now_keeps_utc_instant(db_session):
    school = seed_school(db_session, "Honolulu TZ")
    school.timezone = "Pacific/Honolulu"
    db_session.commit()
    moment = datetime(2026, 3, 2, 2, 0, tzinfo=timezone.utc)  # 2026-03-01 16:00 HST

    with freeze(moment):
        local = attendance_clock.school_local_now(db_session, school)

    assert local.date() == date(2026, 3, 1)
    assert local.astimezone(timezone.utc) == moment


def test_school_local_date_rolls_over_before_utc(db_session):
    """Karachi is UTC+5, so the school day starts 5 hours before UTC does."""
    school = seed_school(db_session, "Rollover TZ")
    moment = datetime(2026, 3, 2, 19, 30, tzinfo=timezone.utc)

    with freeze(moment):
        assert attendance_clock.school_local_date(db_session, school) == date(2026, 3, 3)


def test_unknown_school_timezone_still_produces_a_date(db_session):
    """A broken timezone must not stop attendance from being recorded."""
    school = seed_school(db_session, "Broken TZ")
    school.timezone = "Not/ARealZone"
    db_session.commit()

    with freeze(datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)):
        assert isinstance(attendance_clock.school_local_date(db_session, school), date)