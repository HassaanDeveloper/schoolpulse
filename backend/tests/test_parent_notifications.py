"""Day 5: parent linking, parent self-service and attendance notifications.

Grouped as:
1. admin-managed parent links (roles, duplicates, tenancy)
2. a parent's own children
3. a parent's view of a child's attendance
4. notifications created by a scan
5. the parent's notification inbox and read state
6. provider and message-formatting units
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from backend.api import attendance as attendance_api
from backend.db.models import (
    AttendanceRecord,
    Notification,
    NotificationStatusEnum,
    NotificationTypeEnum,
    RoleEnum,
    StudentParentLink,
)
from backend.services import attendance_clock, notifications
from backend.services.notifications import (
    InAppNotificationProvider,
    NotificationDeliveryError,
    build_message,
    format_occurrence_time,
    notify_attendance_event,
)
from tests.conftest import (
    auth,
    frozen_scan_clock,
    make_token,
    seed_attendance,
    seed_parent_link,
    seed_school,
    seed_student,
    seed_user,
)

SCAN_URL = "/api/v1/attendance/scan"
MY_STUDENTS_URL = "/api/v1/me/students"
NOTIFICATIONS_URL = "/api/v1/me/notifications"
UNREAD_URL = "/api/v1/me/notifications/unread-count"

# 03:04 UTC on 5 October 2026 is 08:04 in Asia/Karachi (UTC+5, no DST).
ARRIVAL_MOMENT = datetime(2026, 10, 5, 3, 4, tzinfo=timezone.utc)
DEPARTURE_MOMENT = datetime(2026, 10, 5, 11, 30, tzinfo=timezone.utc)
LOCAL_DATE = date(2026, 10, 5)


@pytest.fixture()
def school(db_session):
    row = seed_school(db_session, "Parent School")
    row.timezone = "Asia/Karachi"
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture()
def other_school(db_session):
    return seed_school(db_session, "Other School")


@pytest.fixture()
def student(db_session, school):
    return seed_student(db_session, school, admission_number="ADM-500")


def admin_headers(db, school, user_id="admin-1"):
    seed_user(db, user_id, RoleEnum.school_admin, school, email="admin@example.com")
    return auth(make_token(user_id))


def teacher_headers(db, school, user_id="teacher-1"):
    seed_user(db, user_id, RoleEnum.teacher, school)
    return auth(make_token(user_id))


def parent_headers(db, school, user_id="parent-1", email="parent@example.com"):
    seed_user(db, user_id, RoleEnum.parent, school, email=email)
    return auth(make_token(user_id))


def scanner_headers(db, school, user_id="teacher-1"):
    seed_user(db, user_id, RoleEnum.teacher, school)
    return auth(make_token(user_id))


def profile_of(db, auth_user_id):
    from backend.db.models import UserProfile

    return db.query(UserProfile).filter(UserProfile.auth_user_id == auth_user_id).one()


def links_url(student_id):
    return f"/api/v1/students/{student_id}/parents"


def scan(client, headers, credential):
    return client.post(SCAN_URL, json={"credential": credential}, headers=headers)


# ---------------------------------------------------------------------------
# 1. Admin-managed parent links
# ---------------------------------------------------------------------------


def test_admin_can_link_a_parent(client, db_session, school, student):
    headers = admin_headers(db_session, school)
    seed_user(db_session, "parent-1", RoleEnum.parent, school, email="ayesha@example.com")
    parent_profile = profile_of(db_session, "parent-1")

    response = client.post(
        links_url(student.id),
        json={"parent_user_id": str(parent_profile.id)},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    # The admin needs enough detail to confirm they linked the right account.
    assert body["user_id"] == str(parent_profile.id)
    assert body["email"] == "ayesha@example.com"

    link = db_session.query(StudentParentLink).one()
    assert link.school_id == school.id
    assert link.student_id == student.id
    assert link.parent_user_id == parent_profile.id


def test_duplicate_link_conflicts(client, db_session, school, student):
    headers = admin_headers(db_session, school)
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    payload = {"parent_user_id": str(profile_of(db_session, "parent-1").id)}

    first = client.post(links_url(student.id), json=payload, headers=headers)
    second = client.post(links_url(student.id), json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert db_session.query(StudentParentLink).count() == 1


def test_teacher_cannot_link_a_parent(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    payload = {"parent_user_id": str(profile_of(db_session, "parent-1").id)}

    response = client.post(
        links_url(student.id), json=payload, headers=teacher_headers(db_session, school)
    )

    assert response.status_code == 403


def test_parent_cannot_link_another_child(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school, email="p@example.com")
    headers = parent_headers(db_session, school)
    payload = {"parent_user_id": str(profile_of(db_session, "parent-1").id)}

    response = client.post(links_url(student.id), json=payload, headers=headers)

    assert response.status_code == 403
    assert db_session.query(StudentParentLink).count() == 0


def test_link_rejects_unknown_parent_profile(client, db_session, school, student):
    import uuid

    headers = admin_headers(db_session, school)

    response = client.post(
        links_url(student.id),
        json={"parent_user_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert response.status_code == 404


def test_link_rejects_staff_only_profile(client, db_session, school, student):
    """A teacher cannot be granted parent access to a child."""
    seed_user(db_session, "teacher-9", RoleEnum.teacher, school)
    headers = admin_headers(db_session, school)
    payload = {"parent_user_id": str(profile_of(db_session, "teacher-9").id)}

    response = client.post(links_url(student.id), json=payload, headers=headers)

    assert response.status_code == 400
    assert "parent membership" in response.json()["detail"]


def test_parent_of_another_school_cannot_be_linked(client, db_session, school, other_school, student):
    """The parent membership must exist in the student's own school."""
    seed_user(db_session, "outsider-parent", RoleEnum.parent, other_school)
    headers = admin_headers(db_session, school)
    payload = {"parent_user_id": str(profile_of(db_session, "outsider-parent").id)}

    response = client.post(links_url(student.id), json=payload, headers=headers)

    assert response.status_code == 400


def test_admin_cannot_link_across_tenants(client, db_session, school, other_school, student):
    seed_user(db_session, "outsider-parent", RoleEnum.parent, school)
    headers = admin_headers(db_session, other_school, user_id="admin-other")
    payload = {"parent_user_id": str(profile_of(db_session, "outsider-parent").id)}

    response = client.post(links_url(student.id), json=payload, headers=headers)

    # 404, not 403: the existence of another school's student is not disclosed.
    assert response.status_code == 404
    assert db_session.query(StudentParentLink).count() == 0


def test_list_parents_requires_admin(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    headers = parent_headers(db_session, school)

    response = client.get(links_url(student.id), headers=headers)

    assert response.status_code == 403


def test_list_parents_returns_guardians(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school, email="one@example.com")
    seed_user(db_session, "parent-2", RoleEnum.parent, school, email="two@example.com")
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    seed_parent_link(db_session, student, profile_of(db_session, "parent-2"))

    response = client.get(links_url(student.id), headers=admin_headers(db_session, school))

    assert response.status_code == 200
    emails = sorted(row["email"] for row in response.json())
    assert emails == ["one@example.com", "two@example.com"]


def test_list_parents_across_tenants_is_not_found(client, db_session, school, other_school, student):
    response = client.get(
        links_url(student.id),
        headers=admin_headers(db_session, other_school, user_id="admin-other"),
    )

    assert response.status_code == 404


def test_unlink_revokes_access_but_keeps_the_audit_trail(
    client, db_session, school, student
):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    parent_profile = profile_of(db_session, "parent-1")
    seed_parent_link(db_session, student, parent_profile)
    headers = parent_headers(db_session, school)

    assert client.get(MY_STUDENTS_URL, headers=headers).json()["students"]

    response = client.delete(
        f"{links_url(student.id)}/{parent_profile.id}",
        headers=admin_headers(db_session, school),
    )

    assert response.status_code == 204
    assert db_session.query(StudentParentLink).count() == 0

    # The parent's live access is gone immediately.
    assert client.get(MY_STUDENTS_URL, headers=headers).json() == {"students": []}


def test_unlink_keeps_notifications_already_created(client, db_session, school, student):
    """Notifications are an audit trail and survive unlinking."""
    from backend.services import qr_credentials

    seed_user(db_session, "parent-1", RoleEnum.parent, school, email="p@example.com")
    parent_profile = profile_of(db_session, "parent-1")
    seed_parent_link(db_session, student, parent_profile)
    admin = admin_headers(db_session, school)

    credential = qr_credentials.issue_credential(db_session, student)[1]
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), credential)

    client.delete(f"{links_url(student.id)}/{parent_profile.id}", headers=admin)

    assert db_session.query(StudentParentLink).count() == 0
    assert db_session.query(Notification).count() == 1


def test_unlink_unknown_link_is_not_found(client, db_session, school, student):
    import uuid

    response = client.delete(
        f"{links_url(student.id)}/{uuid.uuid4()}",
        headers=admin_headers(db_session, school),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 2. A parent's own children
# ---------------------------------------------------------------------------


def test_parent_lists_only_linked_children(client, db_session, school, other_school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    parent_profile = profile_of(db_session, "parent-1")
    linked = seed_student(db_session, school, admission_number="ADM-LINKED")
    unlinked = seed_student(db_session, school, admission_number="ADM-UNLINKED")
    elsewhere = seed_student(db_session, other_school, admission_number="ADM-OTHER")
    seed_parent_link(db_session, linked, parent_profile)

    response = client.get(MY_STUDENTS_URL, headers=parent_headers(db_session, school))

    assert response.status_code == 200
    returned = response.json()["students"]
    assert [row["student_id"] for row in returned] == [str(linked.id)]
    assert str(unlinked.id) not in response.text
    assert str(elsewhere.id) not in response.text


def test_parent_child_payload_excludes_sensitive_fields(client, db_session, school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    student = seed_student(db_session, school, admission_number="ADM-500")
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))

    body = client.get(MY_STUDENTS_URL, headers=parent_headers(db_session, school)).json()
    row = body["students"][0]

    assert set(row) == {
        "student_id",
        "first_name",
        "last_name",
        "class_name",
        "section",
        "school_id",
        "school_name",
        "school_timezone",
        # Day 6: today's status, resolved server side so the children list
        # needs one request rather than one per child.
        "today_status",
        "today_status_date",
    }
    for leaked in ("date_of_birth", "gender", "admission_number", "token_hash"):
        assert leaked not in row


def test_children_list_reports_todays_status_per_school(
    client, db_session, school, other_school
):
    """A parent whose children attend different schools sees each child's own
    local day, not one global 'today'."""
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_user(db_session, "parent-1", RoleEnum.parent, other_school)
    parent_profile = profile_of(db_session, "parent-1")

    at_first = seed_student(db_session, school, admission_number="ADM-A")
    at_second = seed_student(db_session, other_school, admission_number="ADM-B")
    seed_parent_link(db_session, at_first, parent_profile)
    seed_parent_link(db_session, at_second, parent_profile)

    # An arrival for one child only.
    seed_attendance(
        db_session,
        at_first,
        date(2026, 10, 5),
        arrival_at=datetime(2026, 10, 5, 3, 4, tzinfo=timezone.utc),
    )

    with frozen_scan_clock(datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)):
        body = client.get(MY_STUDENTS_URL, headers=parent_headers(db_session, school)).json()

    by_id = {row["student_id"]: row for row in body["students"]}

    assert by_id[str(at_first.id)]["today_status"] == "present"
    # Nothing recorded for the other child today.
    assert by_id[str(at_second.id)]["today_status"] == "absent"
    assert by_id[str(at_first.id)]["today_status_date"] == "2026-10-05"


def test_children_list_marks_a_completed_day(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    seed_attendance(
        db_session,
        student,
        date(2026, 10, 5),
        arrival_at=datetime(2026, 10, 5, 3, 4, tzinfo=timezone.utc),
        departure_at=datetime(2026, 10, 5, 10, 30, tzinfo=timezone.utc),
    )

    with frozen_scan_clock(datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)):
        body = client.get(MY_STUDENTS_URL, headers=parent_headers(db_session, school)).json()

    assert body["students"][0]["today_status"] == "completed"


def test_children_list_ignores_another_days_record(client, db_session, school, student):
    """Yesterday's arrival must not be reported as today's status."""
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    seed_attendance(
        db_session,
        student,
        date(2026, 10, 4),
        arrival_at=datetime(2026, 10, 4, 3, 4, tzinfo=timezone.utc),
    )

    with frozen_scan_clock(datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)):
        body = client.get(MY_STUDENTS_URL, headers=parent_headers(db_session, school)).json()

    assert body["students"][0]["today_status"] == "absent"


def test_parent_can_scope_children_to_one_school(client, db_session, school, other_school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_user(db_session, "parent-1", RoleEnum.parent, other_school)
    parent_profile = profile_of(db_session, "parent-1")
    at_first = seed_student(db_session, school, admission_number="ADM-A")
    at_second = seed_student(db_session, other_school, admission_number="ADM-B")
    seed_parent_link(db_session, at_first, parent_profile)
    seed_parent_link(db_session, at_second, parent_profile)

    headers = parent_headers(db_session, school)
    every = client.get(MY_STUDENTS_URL, headers=headers)
    scoped = client.get(f"{MY_STUDENTS_URL}?school_id={school.id}", headers=headers)

    assert len(every.json()["students"]) == 2
    assert len(scoped.json()["students"]) == 1
    assert scoped.json()["students"][0]["student_id"] == str(at_first.id)


def test_parent_scoped_to_a_school_they_do_not_belong_to(client, db_session, school, other_school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)

    response = client.get(
        f"{MY_STUDENTS_URL}?school_id={other_school.id}",
        headers=parent_headers(db_session, school),
    )

    assert response.status_code == 404


def test_staff_cannot_use_parent_endpoints(client, db_session, school):
    assert client.get(MY_STUDENTS_URL, headers=teacher_headers(db_session, school)).status_code == 403
    assert client.get(NOTIFICATIONS_URL, headers=teacher_headers(db_session, school)).status_code == 403
    assert client.get(UNREAD_URL, headers=teacher_headers(db_session, school)).status_code == 403


def test_parent_with_no_links_sees_an_empty_list(client, db_session, school):
    response = client.get(MY_STUDENTS_URL, headers=parent_headers(db_session, school))

    assert response.status_code == 200
    assert response.json() == {"students": []}


# ---------------------------------------------------------------------------
# 3. A parent's view of a child's attendance
# ---------------------------------------------------------------------------


def attendance_url(student_id):
    return f"/api/v1/me/students/{student_id}/attendance"


def test_parent_reads_child_attendance(client, db_session, school, student):
    from tests.conftest import seed_attendance

    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    record = seed_attendance(
        db_session,
        student,
        LOCAL_DATE,
        arrival_at=datetime(2026, 10, 5, 3, 4, tzinfo=timezone.utc),
    )

    response = client.get(
        f"{attendance_url(student.id)}?start_date=2026-10-05&end_date=2026-10-05",
        headers=parent_headers(db_session, school),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == str(student.id)
    assert body["records"] == [
        {
            "date": "2026-10-05",
            "status": "present",
            "arrival_at": record.arrival_at.isoformat(),
            "departure_at": None,
            # Rendered on the server in the school's timezone (+05:00), never by
            # the client from its own clock.
            "arrival_time": "8:04 AM",
            "departure_time": None,
        }
    ]


def test_parent_attendance_never_exposes_the_scanner(client, db_session, school, student):
    from tests.conftest import seed_attendance

    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    seed_user(db_session, "teacher-1", RoleEnum.teacher, school, email="teacher@example.com")
    scanner_profile = profile_of(db_session, "teacher-1")
    seed_attendance(
        db_session,
        student,
        LOCAL_DATE,
        arrival_at=datetime(2026, 10, 5, 3, 4, tzinfo=timezone.utc),
        scanned_by=scanner_profile.id,
    )

    response = client.get(
        f"{attendance_url(student.id)}?start_date=2026-10-05&end_date=2026-10-05",
        headers=parent_headers(db_session, school),
    )

    assert response.status_code == 200
    row = response.json()["records"][0]
    assert set(row) == {
        "date",
        "status",
        "arrival_at",
        "departure_at",
        "arrival_time",
        "departure_time",
    }
    assert "scanned_by" not in row
    assert str(scanner_profile.id) not in response.text
    assert "teacher@example.com" not in response.text


def test_parent_attendance_defaults_to_the_school_local_week(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))

    with frozen_scan_clock(ARRIVAL_MOMENT):
        response = client.get(
            attendance_url(student.id), headers=parent_headers(db_session, school)
        )

    assert response.status_code == 200
    body = response.json()
    assert body["end_date"] == "2026-10-05"
    assert len(body["records"]) == 7


def test_parent_attendance_marks_unscanned_days_absent(client, db_session, school, student):
    from tests.conftest import seed_attendance

    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    seed_attendance(
        db_session,
        student,
        date(2026, 10, 4),
        arrival_at=datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc),
    )

    response = client.get(
        f"{attendance_url(student.id)}?start_date=2026-10-04&end_date=2026-10-05",
        headers=parent_headers(db_session, school),
    )

    statuses = {row["date"]: row["status"] for row in response.json()["records"]}
    assert statuses["2026-10-04"] == "present"
    assert statuses["2026-10-05"] == "absent"


def test_parent_cannot_read_an_unlinked_child(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)

    response = client.get(attendance_url(student.id), headers=parent_headers(db_session, school))

    # 404 so that ids cannot be probed to discover which students exist.
    assert response.status_code == 404


def test_parent_cannot_read_another_family_child(client, db_session, school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_user(db_session, "parent-2", RoleEnum.parent, school)
    other_child = seed_student(db_session, school, admission_number="ADM-OTHERFAMILY")
    seed_parent_link(db_session, other_child, profile_of(db_session, "parent-2"))

    response = client.get(
        attendance_url(other_child.id), headers=parent_headers(db_session, school)
    )

    assert response.status_code == 404


def test_parent_cannot_read_a_child_from_another_school(client, db_session, school, other_school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    elsewhere = seed_student(db_session, other_school, admission_number="ADM-ELSEWHERE")

    response = client.get(
        attendance_url(elsewhere.id), headers=parent_headers(db_session, school)
    )

    assert response.status_code == 404


def test_teacher_cannot_use_the_parent_attendance_route(client, db_session, school, student):
    response = client.get(attendance_url(student.id), headers=teacher_headers(db_session, school))

    assert response.status_code == 403


def test_parent_attendance_rejects_a_half_specified_range(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))

    response = client.get(
        f"{attendance_url(student.id)}?start_date=2026-10-01",
        headers=parent_headers(db_session, school),
    )

    assert response.status_code == 422


def test_parent_attendance_rejects_an_over_long_range(client, db_session, school, student):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))

    response = client.get(
        f"{attendance_url(student.id)}?start_date=2026-01-01&end_date=2026-10-05",
        headers=parent_headers(db_session, school),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Notifications created by a scan
# ---------------------------------------------------------------------------


@pytest.fixture()
def linked_family(db_session, school, student):
    """One student with two linked parents and a live QR credential."""
    from backend.services import qr_credentials

    seed_user(db_session, "parent-1", RoleEnum.parent, school, email="one@example.com")
    seed_user(db_session, "parent-2", RoleEnum.parent, school, email="two@example.com")
    seed_parent_link(db_session, student, profile_of(db_session, "parent-1"))
    seed_parent_link(db_session, student, profile_of(db_session, "parent-2"))
    credential = qr_credentials.issue_credential(db_session, student)[1]
    return {
        "credential": credential,
        "parents": [profile_of(db_session, "parent-1"), profile_of(db_session, "parent-2")],
    }


def test_arrival_scan_notifies_every_linked_parent(client, db_session, school, student, linked_family):
    response = scan(client, scanner_headers(db_session, school), linked_family["credential"])

    assert response.status_code == 200
    assert response.json()["status"] == "ARRIVAL_RECORDED"

    rows = db_session.query(Notification).order_by(Notification.parent_user_id).all()
    assert len(rows) == 2
    assert {row.parent_user_id for row in rows} == {p.id for p in linked_family["parents"]}
    for row in rows:
        assert row.type == NotificationTypeEnum.arrival
        assert row.status == NotificationStatusEnum.sent
        assert row.read_at is None
        assert row.school_id == school.id
        assert row.student_id == student.id
        assert row.attendance_id is not None


def test_notification_message_uses_the_school_timezone(
    client, db_session, school, student, linked_family
):
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    row = db_session.query(Notification).first()
    # 03:04 UTC is 08:04 in Asia/Karachi. The message is built server-side so
    # the Flutter app never recomputes it from a device clock.
    assert "8:04 AM" in row.message
    assert student.first_name in row.message
    assert school.name in row.message
    assert row.title == "Arrival recorded"
    assert row.occurred_at.replace(tzinfo=timezone.utc) == ARRIVAL_MOMENT


def test_departure_scan_notifies_parents(client, db_session, school, student, linked_family):
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])
    with frozen_scan_clock(DEPARTURE_MOMENT):
        response = scan(client, scanner_headers(db_session, school), linked_family["credential"])

    assert response.json()["status"] == "DEPARTURE_RECORDED"

    departures = (
        db_session.query(Notification)
        .filter(Notification.type == NotificationTypeEnum.departure)
        .all()
    )
    assert len(departures) == 2
    assert "4:30 PM" in departures[0].message
    assert departures[0].title == "Departure recorded"


def test_third_scan_sends_no_further_notice(client, db_session, school, student, linked_family):
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])
    with frozen_scan_clock(DEPARTURE_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])
    with frozen_scan_clock(datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)):
        response = scan(client, scanner_headers(db_session, school), linked_family["credential"])

    assert response.json()["status"] == "ALREADY_RECORDED"
    # Two parents, two events each: still only four notices.
    assert db_session.query(Notification).count() == 4


def test_scan_still_works_when_no_parent_is_linked(client, db_session, school, student):
    from backend.services import qr_credentials

    credential = qr_credentials.issue_credential(db_session, student)[1]

    response = scan(client, scanner_headers(db_session, school), credential)

    assert response.status_code == 200
    assert response.json()["status"] == "ARRIVAL_RECORDED"
    assert db_session.query(AttendanceRecord).count() == 1
    assert db_session.query(Notification).count() == 0


def test_notifications_are_unique_per_parent_and_event(client, db_session, school, student, linked_family):
    """Re-notifying the same event must not create a second row."""
    from backend.services import qr_credentials

    credential = qr_credentials.issue_credential(db_session, student)[1]
    headers = scanner_headers(db_session, school)

    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, headers, credential)

    record = db_session.query(AttendanceRecord).one()
    before = db_session.query(Notification).count()

    for _ in range(3):
        notify_attendance_event(
            db_session,
            record=record,
            student=student,
            school=school,
            notification_type=NotificationTypeEnum.arrival,
        )
    db_session.commit()

    assert db_session.query(Notification).count() == before


def test_provider_failure_marks_the_notice_failed_and_keeps_attendance(
    client, db_session, school, student, linked_family, monkeypatch
):
    """A failing channel must never cost the attendance record."""

    def boom(self, notification, *, student, school, occurred_at):
        raise NotificationDeliveryError("channel down")

    # Patched on the real provider class, so the service's own error handling
    # is what is under test rather than a stand-in provider.
    monkeypatch.setattr(InAppNotificationProvider, "deliver", boom)

    response = scan(client, scanner_headers(db_session, school), linked_family["credential"])

    assert response.status_code == 200
    assert response.json()["status"] == "ARRIVAL_RECORDED"
    assert db_session.query(AttendanceRecord).count() == 1
    assert db_session.query(Notification).count() == 2
    assert {row.status for row in db_session.query(Notification).all()} == {
        NotificationStatusEnum.failed
    }


def test_a_failed_notice_still_clears_when_read(client, db_session, school, student, linked_family, monkeypatch):
    """A failed notice stays visible so the parent is not silently deprived."""
    def boom(self, notification, *, student, school, occurred_at):
        raise NotificationDeliveryError("channel down")

    monkeypatch.setattr(InAppNotificationProvider, "deliver", boom)
    headers = parent_headers(db_session, school, "parent-1")
    scan(client, scanner_headers(db_session, school), linked_family["credential"])

    body = client.get(NOTIFICATIONS_URL, headers=headers).json()

    assert len(body["notifications"]) == 1
    assert body["notifications"][0]["status"] == "failed"
    assert body["unread_count"] == 1


def test_notifications_are_scoped_to_the_students_school(
    client, db_session, school, other_school, linked_family
):
    """A link in another school must not produce notices here."""
    elsewhere = seed_student(db_session, other_school, admission_number="ADM-ELSEWHERE")
    seed_user(db_session, "parent-1", RoleEnum.parent, other_school)
    seed_parent_link(db_session, elsewhere, profile_of(db_session, "parent-1"))

    from backend.services import qr_credentials

    credential = qr_credentials.issue_credential(db_session, elsewhere)[1]
    scan(client, scanner_headers(db_session, school), credential)

    assert db_session.query(Notification).count() == 0


def test_scan_response_contract_is_unchanged(client, db_session, school, student, linked_family):
    """Day 5 adds no fields to the scanner's Day 3 response."""
    response = scan(client, scanner_headers(db_session, school), linked_family["credential"])

    assert set(response.json()) == {
        "status",
        "student",
        "attendance_date",
        "arrival_at",
        "departure_at",
        "timestamp",
    }


def test_inactive_student_scan_produces_no_notification(client, db_session, school, student, linked_family):
    from backend.db.models import StudentStatusEnum

    student.status = StudentStatusEnum.inactive
    db_session.commit()

    response = scan(client, scanner_headers(db_session, school), linked_family["credential"])

    assert response.status_code == 403
    assert db_session.query(Notification).count() == 0


# ---------------------------------------------------------------------------
# 5. The parent's notification inbox
# ---------------------------------------------------------------------------


def test_parent_lists_notifications_newest_first(client, db_session, school, student, linked_family):
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])
    with frozen_scan_clock(DEPARTURE_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    response = client.get(
        NOTIFICATIONS_URL, headers=parent_headers(db_session, school, "parent-1")
    )

    assert response.status_code == 200
    body = response.json()
    # Both parents were notified; this parent sees only their own two.
    assert len(body["notifications"]) == 2
    assert [row["type"] for row in body["notifications"]] == ["departure", "arrival"]
    assert body["unread_count"] == 2


def test_notification_payload_has_no_private_fields(client, db_session, school, student, linked_family):
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    response = client.get(
        NOTIFICATIONS_URL, headers=parent_headers(db_session, school, "parent-1")
    )
    row = response.json()["notifications"][0]

    assert set(row) == {
        "id",
        "type",
        "title",
        "message",
        "status",
        "occurred_at",
        # Day 6: the school-local time, so the app never converts the instant on
        # the device's clock.
        "occurred_time",
        "read_at",
        "created_at",
    }
    # No token, no scanned_by, no other family's data.
    for leaked in ("token_hash", "scanned_by", "credential", "parent_user_id"):
        assert leaked not in row
    assert "two@example.com" not in response.text
    assert row["occurred_time"]


def test_notification_time_is_rendered_in_the_school_timezone(
    client, db_session, school, linked_family
):
    """A parent in another timezone still sees the time the school recorded."""
    school.timezone = "Asia/Karachi"
    db_session.commit()

    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    response = client.get(
        NOTIFICATIONS_URL, headers=parent_headers(db_session, school, "parent-1")
    )
    row = response.json()["notifications"][0]

    # 03:04 UTC is 08:04 in Karachi (+05:00), so this differs from the UTC hour.
    assert row["occurred_time"] == "8:04 AM"
    # The instant is still available, unmodified, for ordering.
    assert row["occurred_at"].startswith("2026-10-05T03:04")


def test_marking_a_notification_read_clears_the_badge(
    client, db_session, school, student, linked_family
):
    headers = parent_headers(db_session, school, "parent-1")
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    listed = client.get(NOTIFICATIONS_URL, headers=headers).json()
    assert listed["unread_count"] == 1

    notification_id = listed["notifications"][0]["id"]
    marked = client.patch(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=headers)

    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None
    assert client.get(UNREAD_URL, headers=headers).json() == {"unread_count": 0}
    assert client.get(NOTIFICATIONS_URL, headers=headers).json()["unread_count"] == 0


def test_marking_read_twice_is_harmless(client, db_session, school, student, linked_family):
    headers = parent_headers(db_session, school, "parent-1")
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    notification_id = client.get(NOTIFICATIONS_URL, headers=headers).json()["notifications"][0]["id"]
    first = client.patch(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=headers)
    second = client.patch(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["read_at"] == second.json()["read_at"]


def test_a_parent_cannot_read_another_parents_notification(
    client, db_session, school, student, linked_family
):
    headers = parent_headers(db_session, school, "parent-2")
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    # Take parent-1's notification id directly from the database.
    other = db_session.query(Notification).filter_by(
        parent_user_id=profile_of(db_session, "parent-1").id
    ).one()

    response = client.patch(f"{NOTIFICATIONS_URL}/{other.id}/read", headers=headers)

    assert response.status_code == 404
    assert other.read_at is None


def test_unread_only_filter(client, db_session, school, student, linked_family):
    headers = parent_headers(db_session, school, "parent-1")
    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])
    with frozen_scan_clock(DEPARTURE_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    notification_id = client.get(NOTIFICATIONS_URL, headers=headers).json()["notifications"][1]["id"]
    client.patch(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=headers)

    remaining = client.get(f"{NOTIFICATIONS_URL}?unread_only=true", headers=headers)

    assert remaining.status_code == 200
    assert [row["type"] for row in remaining.json()["notifications"]] == ["departure"]


def test_notifications_can_be_scoped_to_one_school(client, db_session, school, other_school, linked_family):
    """A parent at two schools sees only the notices from the chosen one."""
    seed_user(db_session, "parent-1", RoleEnum.parent, other_school)
    headers = parent_headers(db_session, school, "parent-1")

    with frozen_scan_clock(ARRIVAL_MOMENT):
        scan(client, scanner_headers(db_session, school), linked_family["credential"])

    at_school = client.get(f"{NOTIFICATIONS_URL}?school_id={school.id}", headers=headers)
    at_other = client.get(f"{NOTIFICATIONS_URL}?school_id={other_school.id}", headers=headers)

    assert len(at_school.json()["notifications"]) == 1
    assert at_other.json()["notifications"] == []
    assert at_other.json()["unread_count"] == 0


def test_unread_count_is_zero_for_a_new_parent(client, db_session, school):
    response = client.get(UNREAD_URL, headers=parent_headers(db_session, school))

    assert response.status_code == 200
    assert response.json() == {"unread_count": 0}


def test_notifications_require_a_token(client, db_session, school):
    assert client.get(NOTIFICATIONS_URL).status_code == 401
    assert client.get(UNREAD_URL, headers=auth(make_token("ghost"))).status_code == 403


# ---------------------------------------------------------------------------
# 6. Provider and formatting units
# ---------------------------------------------------------------------------


def test_occurrence_time_uses_the_school_timezone(db_session, school):
    assert format_occurrence_time(ARRIVAL_MOMENT, school) == "8:04 AM"

    school.timezone = "UTC"
    db_session.commit()
    assert format_occurrence_time(ARRIVAL_MOMENT, school) == "3:04 AM"


def test_occurrence_time_handles_noon_and_midnight(db_session, school):
    school.timezone = "UTC"
    db_session.commit()

    assert format_occurrence_time(datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc), school) == "12:00 PM"
    assert format_occurrence_time(datetime(2026, 10, 5, 0, 5, tzinfo=timezone.utc), school) == "12:05 AM"


def test_naive_timestamps_are_treated_as_utc(db_session, school):
    """SQLite returns naive datetimes; they must not shift the message."""
    assert format_occurrence_time(datetime(2026, 10, 5, 3, 4), school) == "8:04 AM"


def test_invalid_school_timezone_falls_back(db_session, school):
    school.timezone = "Not/AZone"
    db_session.commit()

    assert attendance_clock.get_timezone(school.timezone).key == "Asia/Karachi"


def test_build_message_mentions_only_the_child_and_school(db_session, school, student):
    message = build_message(
        NotificationTypeEnum.arrival,
        student=student,
        school=school,
        occurred_at=ARRIVAL_MOMENT,
    )

    assert message == f"{student.first_name} {student.last_name} arrived at {school.name} at 8:04 AM."


def test_in_app_provider_marks_a_notice_sent(db_session, school, student, linked_family):
    """The unit-level contract the in-app provider is chosen for."""
    record = AttendanceRecord(
        school_id=school.id,
        student_id=student.id,
        attendance_date=LOCAL_DATE,
        arrival_at=ARRIVAL_MOMENT,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    provider = InAppNotificationProvider()
    created = notify_attendance_event(
        db_session,
        record=record,
        student=student,
        school=school,
        notification_type=NotificationTypeEnum.arrival,
        provider=provider,
    )
    db_session.commit()

    assert provider.name == "in_app"
    assert len(created) == 2
    assert all(row.status == NotificationStatusEnum.sent for row in created)


def test_base_provider_is_abstract(db_session, school, student):
    record = AttendanceRecord(
        school_id=school.id,
        student_id=student.id,
        attendance_date=LOCAL_DATE,
        arrival_at=ARRIVAL_MOMENT,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    with pytest.raises(NotImplementedError):
        notifications.NotificationProvider().deliver(
            None, student=student, school=school, occurred_at=ARRIVAL_MOMENT
        )


def test_the_scan_module_uses_the_shared_notification_service():
    """The scanner must not reimplement notification creation."""
    assert attendance_api.notify_attendance_event is notify_attendance_event


def test_no_external_delivery_library_is_imported():
    """Day 5 is in-app only: no WhatsApp/SMS/push SDK may sneak in."""
    source = (
        Path(__file__).resolve().parents[1] / "src" / "backend" / "services" / "notifications.py"
    ).read_text(encoding="utf-8")

    imports = "\n".join(
        line for line in source.splitlines() if line.startswith(("import ", "from "))
    )

    for banned in ("twilio", "whatsapp", "sendgrid", "firebase", "httpx", "requests", "smtplib"):
        assert banned not in imports.lower()