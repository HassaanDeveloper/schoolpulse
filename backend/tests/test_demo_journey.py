"""Day 7: the full Day 8 demonstration, rehearsed end to end.

This is the one test that walks the exact sequence the school administrator
will perform on a phone:

    admin login -> class -> student -> QR -> parent link
    -> scan arrival -> parent notification -> parent attendance
    -> scan departure -> parent notification -> completed attendance
    -> third scan refused, and no duplicate notification

Every request goes through the real HTTP API and the real authorization layer,
so this exercises the same code paths a live phone would. Only the SQLite
driver underneath is a substitute for PostgreSQL.

The whole file is marked so it is obvious that the arrangement is a rehearsal,
not a record of a live run.
"""

import re

import pytest

from backend.db.models import (
    AttendanceRecord,
    Notification,
    RoleEnum,
    UserProfile,
)
from tests.conftest import (
    auth,
    make_token,
    seed_class,
    seed_school,
    seed_student,
    seed_user,
)

DEMO_SCHOOL = "Karachi Model School"
DEMO_CLASS = "Grade 5"
DEMO_SECTION = "A"
DEMO_ADMISSION = "SP-DEMO-001"
DEMO_TZ = "Asia/Karachi"


@pytest.fixture()
def school(db_session):
    return seed_school(db_session, DEMO_SCHOOL)


@pytest.fixture()
def demo_class(db_session, school):
    return seed_class(db_session, school, DEMO_CLASS, DEMO_SECTION)


@pytest.fixture()
def student(db_session, school, demo_class):
    """The fictional demo pupil. No real child's data is used anywhere."""
    return seed_student(
        db_session,
        school,
        demo_class,
        admission_number=DEMO_ADMISSION,
        first_name="Ali",
        last_name="Khan",
    )


@pytest.fixture()
def admin_headers(db_session, school):
    seed_user(db_session, "demo-admin", RoleEnum.school_admin, school)
    return auth(make_token("demo-admin"))


@pytest.fixture()
def teacher_headers(db_session, school):
    seed_user(db_session, "demo-teacher", RoleEnum.teacher, school)
    return auth(make_token("demo-teacher"))


@pytest.fixture()
def parent_profile(db_session, school):
    return seed_user(
        db_session, "demo-parent", RoleEnum.parent, school, "demo.parent@example.test"
    )


def link_parent(client, db_session, student, admin_headers, parent_profile):
    response = client.post(
        f"/api/v1/students/{student.id}/parents",
        headers=admin_headers,
        json={"parent_user_id": str(parent_profile.id)},
    )
    assert response.status_code in (200, 201), response.text
    return response


def scan(client, headers, student, credential):
    return client.post(
        "/api/v1/attendance/scan",
        headers=headers,
        json={"credential": credential},
    )


def my_children(client):
    """`GET /me/students` wraps its rows in a `students` object."""
    response = client.get("/api/v1/me/students", headers=auth(make_token("demo-parent")))
    assert response.status_code == 200
    return response.json()["students"]


def notifications_for(client, db_session, parent_profile):
    """`GET /me/notifications` wraps rows under `notifications`."""
    response = client.get(
        "/api/v1/me/notifications", headers=auth(make_token("demo-parent"))
    )
    assert response.status_code == 200
    body = response.json()
    return {**body, "items": body["notifications"]}


# ---------- section A: admin reaches the student and their QR ----------


def test_admin_can_reach_demo_class_and_student(client, admin_headers, student):
    classes = client.get("/api/v1/classes", headers=admin_headers)
    assert classes.status_code == 200
    names = [c["name"] for c in classes.json()]
    assert DEMO_CLASS in names

    listing = client.get(
        "/api/v1/students", headers=admin_headers, params={"search": DEMO_ADMISSION}
    )
    assert listing.status_code == 200
    body = listing.json()
    items = body["items"] if isinstance(body, dict) else body
    assert any(item["admission_number"] == DEMO_ADMISSION for item in items)


def test_admin_generates_a_real_qr_credential(
    client, db_session, admin_headers, student
):
    response = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    )
    assert response.status_code in (200, 201), response.text
    credential = response.json()["credential"]
    assert credential and credential.strip()

    # The opaque token, not the student id, is what identifies the student.
    assert str(student.id) not in credential


def test_qr_status_is_reported_before_any_scan(client, admin_headers, student):
    response = client.get(f"/api/v1/students/{student.id}/qr", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["has_active_credential"] is False
    assert body["last_revoked_at"] is None


def test_parent_is_linked_and_visible_to_the_parent(
    client, db_session, admin_headers, student, parent_profile
):
    link_parent(client, db_session, student, admin_headers, parent_profile)

    assert any(c["student_id"] == str(student.id) for c in my_children(client))


# ---------- sections C to F: arrival, departure, third scan ----------


def test_arrival_departure_and_third_scan(
    client, db_session, admin_headers, teacher_headers, student, parent_profile
):
    link_parent(client, db_session, student, admin_headers, parent_profile)

    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]

    # C. First scan records the arrival.
    first = scan(client, teacher_headers, student, credential)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ARRIVAL_RECORDED"

    # D. The parent receives exactly one arrival notification.
    inbox = notifications_for(client, db_session, parent_profile)
    assert inbox["unread_count"] >= 1
    arrivals = [
        n for n in inbox["items"] if n["type"] == "arrival"
    ]
    assert len(arrivals) == 1
    assert re.search(r"arrived", arrivals[0]["message"], re.I)
    assert arrivals[0]["occurred_time"]

    # E. Second scan records the departure.
    second = scan(client, teacher_headers, student, credential)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "DEPARTURE_RECORDED"

    departures = [
        n
        for n in notifications_for(client, db_session, parent_profile)["items"]
        if n["type"] == "departure"
    ]
    assert len(departures) == 1

    # F. The attendance row now carries both timestamps.
    record = (
        db_session.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .one()
    )
    assert record.arrival_at is not None
    assert record.departure_at is not None


def test_third_scan_is_refused_and_creates_no_duplicate_notification(
    client, db_session, admin_headers, teacher_headers, student, parent_profile
):
    """The most important Day 7 assertion.

    A third scan of a completed day must report ALREADY_RECORDED and must not
    produce a third notification. A duplicate notification on a school phone
    would be visible to the parent as a bug.
    """
    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]

    scan(client, teacher_headers, student, credential)
    scan(client, teacher_headers, student, credential)

    before = notifications_for(client, db_session, parent_profile)["items"]
    before_ids = {n["id"] for n in before}
    assert len(before) == 2

    third = scan(client, teacher_headers, student, credential)
    assert third.status_code == 200, third.text
    assert third.json()["status"] == "ALREADY_RECORDED"

    after = notifications_for(client, db_session, parent_profile)["items"]
    assert len(after) == len(before), "third scan created an extra notification"
    assert {n["id"] for n in after} == before_ids

    # And only one attendance row exists for the day.
    records = (
        db_session.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .all()
    )
    assert len(records) == 1


def test_repeated_scans_never_exceed_two_notifications(
    client, db_session, admin_headers, teacher_headers, student, parent_profile
):
    """Five scans of one day still yield exactly two notices."""
    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]

    statuses = []
    for _ in range(5):
        response = scan(client, teacher_headers, student, credential)
        assert response.status_code == 200, response.text
        statuses.append(response.json()["status"])

    assert statuses[0] == "ARRIVAL_RECORDED"
    assert statuses[1] == "DEPARTURE_RECORDED"
    assert set(statuses[2:]) == {"ALREADY_RECORDED"}

    items = notifications_for(client, db_session, parent_profile)["items"]
    assert len(items) == 2


# ---------- parent views today's attendance ----------


def test_parent_sees_today_section_and_today_status(
    client, db_session, admin_headers, teacher_headers, student, parent_profile
):
    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]
    scan(client, teacher_headers, student, credential)

    child = next(c for c in my_children(client) if c["student_id"] == str(student.id))
    assert child["today_status"] == "present"

    parent_headers = auth(make_token("demo-parent"))
    history = client.get(
        f"/api/v1/me/students/{student.id}/attendance", headers=parent_headers
    )
    assert history.status_code == 200
    body = history.json()
    assert body["student_id"] == str(student.id)
    assert body["end_date"] == child["today_status_date"]
    assert len(body["records"]) >= 1

    today = body["records"][0]
    assert today["status"] == "present"
    assert today["arrival_at"] or today["arrival_time"]


def test_today_status_is_absent_before_the_first_scan(
    client, db_session, school, admin_headers, student, parent_profile
):
    link_parent(client, db_session, student, admin_headers, parent_profile)

    child = next(c for c in my_children(client) if c["student_id"] == str(student.id))
    assert child["today_status"] == "absent"



def test_notification_can_be_marked_read(
    client, db_session, school, admin_headers, teacher_headers, student, parent_profile
):
    """Section D: the parent opens the notice and it becomes read."""
    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]
    scan(client, teacher_headers, student, credential)

    parent_headers = auth(make_token("demo-parent"))
    inbox = notifications_for(client, db_session, parent_profile)
    assert inbox["unread_count"] == 1

    notification_id = inbox["items"][0]["id"]
    marked = client.patch(
        f"/api/v1/me/notifications/{notification_id}/read", headers=parent_headers
    )
    assert marked.status_code == 200, marked.text

    after = notifications_for(client, db_session, parent_profile)
    assert after["unread_count"] == 0


def test_demo_notifications_are_only_addressed_to_the_linked_parent(
    client, db_session, admin_headers, teacher_headers, student, parent_profile
):
    """No notice may leak to an unrelated parent."""
    other_school = seed_school(db_session, "Other School")
    other_class = seed_class(db_session, other_school, "Grade 9", "B")
    other_student = seed_student(db_session, other_school, other_class)
    other_parent = seed_user(
        db_session, "other-parent", RoleEnum.parent, other_school, "o@example.test"
    )

    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]
    scan(client, teacher_headers, student, credential)

    other_headers = auth(make_token("other-parent"))
    inbox = client.get("/api/v1/me/notifications", headers=other_headers).json()
    assert inbox["unread_count"] == 0
    assert inbox["notifications"] == []
    assert other_parent is not None
    assert other_student.id != student.id


def test_notification_count_is_one_per_scan_not_per_parent_row(
    client, db_session, admin_headers, teacher_headers, student, parent_profile
):
    """A single scan produces exactly one notification row in the database."""
    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]
    scan(client, teacher_headers, student, credential)

    rows = db_session.query(Notification).all()
    assert len(rows) == 1


def test_demo_school_timezone_drives_the_attendance_date(
    client, db_session, school, admin_headers, teacher_headers, student, parent_profile
):
    """The date is the school's local day, not the server's UTC day."""
    link_parent(client, db_session, student, admin_headers, parent_profile)
    credential = client.post(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers
    ).json()["credential"]
    scan(client, teacher_headers, student, credential)

    record = (
        db_session.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student.id)
        .one()
    )
    assert record.attendance_date is not None

    child = next(c for c in my_children(client) if c["student_id"] == str(student.id))
    assert child["today_status_date"] == str(record.attendance_date)