"""Day 4: attendance history and student attendance detail."""

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.db.models import RoleEnum
from backend.services.attendance_status import (
    MAX_HISTORY_DAYS,
    AttendanceStatus,
    default_range,
    derive_status,
    enumerate_dates,
    validate_range,
)
from tests.conftest import (
    auth,
    frozen_clock,
    make_token,
    seed_attendance,
    seed_school,
    seed_student,
    seed_user,
)

HISTORY_URL = "/api/v1/attendance/history"
TODAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc)


@pytest.fixture()
def school(db_session):
    return seed_school(db_session, "History School")


@pytest.fixture()
def school_b(db_session):
    return seed_school(db_session, "Foreign School")


def admin_headers(db, school, user_id="hist-admin"):
    seed_user(db, user_id, RoleEnum.school_admin, school)
    return auth(make_token(user_id))


def teacher_headers(db, school, user_id="hist-teacher"):
    seed_user(db, user_id, RoleEnum.teacher, school)
    return auth(make_token(user_id))


def parent_headers(db, school, user_id="hist-parent"):
    seed_user(db, user_id, RoleEnum.parent, school)
    return auth(make_token(user_id))


def history(client, headers, student_id, **params):
    return client.get(HISTORY_URL, headers=headers, params={"student_id": str(student_id), **params})


def detail(client, headers, student_id, **params):
    return client.get(
        f"/api/v1/students/{student_id}/attendance", headers=headers, params=params
    )


# ---------- derived status unit rules ----------


def test_derive_status_rules():
    assert derive_status(None, None) is AttendanceStatus.absent
    assert derive_status(datetime.now(timezone.utc), None) is AttendanceStatus.present
    assert (
        derive_status(datetime.now(timezone.utc), datetime.now(timezone.utc))
        is AttendanceStatus.completed
    )


def test_derive_status_ignores_departure_without_arrival():
    """A departure with no arrival is not a completed day."""
    assert derive_status(None, datetime.now(timezone.utc)) is AttendanceStatus.absent


def test_enumerate_dates_is_inclusive():
    days = enumerate_dates(date(2026, 10, 1), date(2026, 10, 5))
    assert len(days) == 5
    assert days[0] == date(2026, 10, 1)
    assert days[-1] == date(2026, 10, 5)


def test_enumerate_dates_single_day():
    assert enumerate_dates(date(2026, 10, 1), date(2026, 10, 1)) == [date(2026, 10, 1)]


def test_enumerate_dates_reversed_is_empty():
    assert enumerate_dates(date(2026, 10, 5), date(2026, 10, 1)) == []


def test_default_range_covers_seven_days_ending_today():
    start, end = default_range(date(2026, 10, 4))
    assert end == date(2026, 10, 4)
    assert start == date(2026, 9, 28)
    assert len(enumerate_dates(start, end)) == 7


def test_validate_range_rejects_reversed():
    with pytest.raises(ValueError):
        validate_range(date(2026, 10, 5), date(2026, 10, 1))


def test_validate_range_enforces_maximum_span():
    ok_start = date(2026, 10, 4) - timedelta(days=MAX_HISTORY_DAYS - 1)
    validate_range(ok_start, date(2026, 10, 4))

    too_early = date(2026, 10, 4) - timedelta(days=MAX_HISTORY_DAYS)
    with pytest.raises(ValueError):
        validate_range(too_early, date(2026, 10, 4))


# ---------- history authorization ----------


def test_history_requires_authentication(client, db_session, school):
    student = seed_student(db_session, school)
    assert client.get(HISTORY_URL, params={"student_id": str(student.id)}).status_code == 401


def test_history_denies_parent(client, db_session, school):
    student = seed_student(db_session, school)
    assert history(client, parent_headers(db_session, school), student.id).status_code == 403


def test_history_allows_teacher(client, db_session, school):
    student = seed_student(db_session, school)
    response = history(
        client,
        teacher_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-02",
    )
    assert response.status_code == 200, response.text


def test_history_allows_admin(client, db_session, school):
    student = seed_student(db_session, school)
    response = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-02",
    )
    assert response.status_code == 200, response.text


def test_history_requires_student_id(client, db_session, school):
    response = client.get(HISTORY_URL, headers=admin_headers(db_session, school))
    assert response.status_code == 422


# ---------- history content ----------


def test_history_reports_every_requested_date(client, db_session, school):
    student = seed_student(db_session, school)

    response = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-05",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert [item["date"] for item in body["items"]] == [
        "2026-10-05",
        "2026-10-04",
        "2026-10-03",
        "2026-10-02",
        "2026-10-01",
    ]
    assert all(item["status"] == "absent" for item in body["items"])


def test_history_fills_gaps_as_absent(client, db_session, school):
    """The scenario from the Day 4 brief, including out-of-order records."""
    student = seed_student(db_session, school)

    seed_attendance(db_session, student, date(2026, 10, 1), departure_at=None)  # present
    seed_attendance(
        db_session,
        student,
        date(2026, 10, 3),
        departure_at=datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc),
    )  # completed
    seed_attendance(db_session, student, date(2026, 10, 5), departure_at=None)  # present

    body = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-05",
    ).json()

    by_date = {item["date"]: item for item in body["items"]}
    assert by_date["2026-10-01"]["status"] == "present"
    assert by_date["2026-10-02"]["status"] == "absent"
    assert by_date["2026-10-03"]["status"] == "completed"
    assert by_date["2026-10-04"]["status"] == "absent"
    assert by_date["2026-10-05"]["status"] == "present"
    assert by_date["2026-10-02"]["arrival_at"] is None


def test_history_returns_timestamps(client, db_session, school):
    student = seed_student(db_session, school)
    arrival = datetime(2026, 10, 3, 3, 1, tzinfo=timezone.utc)
    departure = datetime(2026, 10, 3, 10, 57, tzinfo=timezone.utc)
    seed_attendance(db_session, student, date(2026, 10, 3), arrival_at=arrival, departure_at=departure)

    body = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-03",
        end_date="2026-10-03",
    ).json()

    item = body["items"][0]
    assert item["status"] == "completed"
    assert item["arrival_at"] is not None
    assert item["departure_at"] is not None


def test_history_is_ordered_newest_first(client, db_session, school):
    student = seed_student(db_session, school)
    for day in range(1, 6):
        seed_attendance(db_session, student, date(2026, 10, day), departure_at=None)

    body = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-05",
    ).json()

    dates = [item["date"] for item in body["items"]]
    assert dates == sorted(dates, reverse=True)


def test_history_ignores_records_outside_the_range(client, db_session, school):
    student = seed_student(db_session, school)
    seed_attendance(db_session, student, date(2026, 9, 1), departure_at=None)
    seed_attendance(db_session, student, date(2026, 12, 1), departure_at=None)

    body = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-03",
    ).json()

    assert body["total"] == 3
    assert all(item["status"] == "absent" for item in body["items"])


def test_history_defaults_to_last_seven_school_days(client, db_session, school):
    student = seed_student(db_session, school)
    headers = admin_headers(db_session, school)

    with frozen_clock(NOW):
        body = history(client, headers, student.id).json()

    assert body["start_date"] == "2026-09-28"
    assert body["end_date"] == "2026-10-04"
    assert body["total"] == 7


# ---------- history validation ----------


def test_history_rejects_reversed_range(client, db_session, school):
    student = seed_student(db_session, school)
    response = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-05",
        end_date="2026-10-01",
    )
    assert response.status_code == 422
    assert "end_date" in response.json()["detail"]


def test_history_rejects_oversized_range(client, db_session, school):
    student = seed_student(db_session, school)
    response = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2020-01-01",
        end_date="2026-10-01",
    )
    assert response.status_code == 422
    assert str(MAX_HISTORY_DAYS) in response.json()["detail"]


def test_history_accepts_the_maximum_range(client, db_session, school):
    student = seed_student(db_session, school)
    start = date(2026, 10, 4) - timedelta(days=MAX_HISTORY_DAYS - 1)
    response = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date=start.isoformat(),
        end_date="2026-10-04",
    )
    assert response.status_code == 200
    assert response.json()["total"] == MAX_HISTORY_DAYS


def test_history_rejects_half_specified_range(client, db_session, school):
    student = seed_student(db_session, school)
    headers = admin_headers(db_session, school)

    only_start = history(client, headers, student.id, start_date="2026-10-01")
    only_end = history(client, headers, student.id, end_date="2026-10-05")

    assert only_start.status_code == 422
    assert only_end.status_code == 422


def test_history_rejects_invalid_date_format(client, db_session, school):
    student = seed_student(db_session, school)
    response = history(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="not-a-date",
        end_date="2026-10-05",
    )
    assert response.status_code == 422


def test_history_paginates(client, db_session, school):
    student = seed_student(db_session, school)
    for day in range(1, 11):
        seed_attendance(db_session, student, date(2026, 10, day), departure_at=None)

    headers = admin_headers(db_session, school)
    first = history(client, headers, student.id, start_date="2026-10-01", end_date="2026-10-10", page=1, page_size=4).json()
    second = history(client, headers, student.id, start_date="2026-10-01", end_date="2026-10-10", page=2, page_size=4).json()
    third = history(client, headers, student.id, start_date="2026-10-01", end_date="2026-10-10", page=3, page_size=4).json()

    assert first["total"] == 10
    assert len(first["items"]) == 4
    assert len(second["items"]) == 4
    assert len(third["items"]) == 2

    seen = [item["date"] for page in (first, second, third) for item in page["items"]]
    assert len(set(seen)) == 10


def test_history_page_size_bounds(client, db_session, school):
    student = seed_student(db_session, school)
    headers = admin_headers(db_session, school)
    assert history(client, headers, student.id, page_size=101).status_code == 422
    assert history(client, headers, student.id, page=0).status_code == 422


# ---------- cross-tenant isolation ----------


def test_history_rejects_student_from_another_school(client, db_session, school, school_b):
    foreign = seed_student(db_session, school_b, admission_number="B-1", first_name="Secret")

    response = history(
        client,
        admin_headers(db_session, school),
        foreign.id,
        start_date="2026-10-01",
        end_date="2026-10-02",
    )

    assert response.status_code == 404
    assert "Secret" not in response.text


def test_history_rejects_other_school_id_override(client, db_session, school, school_b):
    """Naming the other school explicitly must not bypass membership."""
    seed_user(db_session, "admin-a", RoleEnum.school_admin, school)
    seed_user(db_session, "admin-b", RoleEnum.school_admin, school_b)
    foreign = seed_student(db_session, school_b, admission_number="B-1")

    response = history(
        client,
        auth(make_token("admin-b")),
        foreign.id,
        start_date="2026-10-01",
        end_date="2026-10-02",
        school_id=str(school.id),
    )

    assert response.status_code == 403


def test_unknown_student_is_404(client, db_session, school):
    response = history(
        client,
        admin_headers(db_session, school),
        "00000000-0000-4000-8000-000000000000",
        start_date="2026-10-01",
        end_date="2026-10-02",
    )
    assert response.status_code == 404


# ---------- student attendance detail ----------


def test_detail_requires_authentication(client, db_session, school):
    student = seed_student(db_session, school)
    assert client.get(f"/api/v1/students/{student.id}/attendance").status_code == 401


def test_detail_denies_parent(client, db_session, school):
    student = seed_student(db_session, school)
    assert detail(client, parent_headers(db_session, school), student.id).status_code == 403


def test_detail_allows_teacher_and_admin(client, db_session, school):
    student = seed_student(db_session, school)
    assert detail(client, admin_headers(db_session, school), student.id).status_code == 200
    assert detail(client, teacher_headers(db_session, school), student.id).status_code == 200


def test_detail_returns_student_information(client, db_session, school):
    from backend.db.models import Class

    school_class = Class(
        school_id=school.id, name="Grade 8", section="B", academic_year="2026"
    )
    db_session.add(school_class)
    db_session.commit()
    db_session.refresh(school_class)

    student = seed_student(
        db_session,
        school,
        school_class,
        admission_number="SP-1001",
        first_name="Ali",
        last_name="Khan",
    )

    body = detail(client, admin_headers(db_session, school), student.id).json()

    assert body["student"]["id"] == str(student.id)
    assert body["student"]["name"] == "Ali Khan"
    assert body["student"]["admission_number"] == "SP-1001"
    assert body["student"]["class_name"] == "Grade 8"
    assert body["student"]["section"] == "B"


def test_detail_returns_records_and_summary(client, db_session, school):
    student = seed_student(db_session, school)

    seed_attendance(db_session, student, date(2026, 10, 1), departure_at=None)
    seed_attendance(
        db_session,
        student,
        date(2026, 10, 2),
        departure_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
    )
    # 2026-10-03 intentionally has no record -> absent.

    body = detail(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-05",
    ).json()

    assert len(body["records"]) == 5
    assert body["summary"] == {
        "total_days": 5,
        "present_days": 1,
        "absent_days": 3,
        "completed_days": 1,
    }
    assert (
        body["summary"]["present_days"]
        + body["summary"]["absent_days"]
        + body["summary"]["completed_days"]
        == body["summary"]["total_days"]
    )


def test_detail_summary_covers_whole_range_not_one_page(client, db_session, school):
    student = seed_student(db_session, school)
    for day in range(1, 6):
        seed_attendance(db_session, student, date(2026, 10, day), departure_at=None)

    body = detail(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-05",
        page=1,
        page_size=2,
    ).json()

    assert len(body["records"]) == 2
    assert body["total"] == 5
    assert body["summary"]["total_days"] == 5
    assert body["summary"]["present_days"] == 5


def test_detail_matches_history_endpoint(client, db_session, school):
    """The detail endpoint reuses the history logic rather than duplicating it."""
    student = seed_student(db_session, school)
    seed_attendance(db_session, student, date(2026, 10, 2), departure_at=None)

    headers = admin_headers(db_session, school)
    params = {"start_date": "2026-10-01", "end_date": "2026-10-04"}

    detail_body = detail(client, headers, student.id, **params).json()
    history_body = history(client, headers, student.id, **params).json()

    assert detail_body["records"] == history_body["items"]


def test_detail_defaults_to_last_seven_days(client, db_session, school):
    student = seed_student(db_session, school)
    with frozen_clock(NOW):
        body = detail(client, admin_headers(db_session, school), student.id).json()

    assert body["start_date"] == "2026-09-28"
    assert body["end_date"] == "2026-10-04"
    assert body["summary"]["total_days"] == 7


def test_detail_rejects_invalid_range(client, db_session, school):
    student = seed_student(db_session, school)
    response = detail(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-05",
        end_date="2026-10-01",
    )
    assert response.status_code == 422


def test_detail_rejects_cross_school_student(client, db_session, school, school_b):
    foreign = seed_student(db_session, school_b, admission_number="B-1", first_name="Secret")

    response = detail(
        client,
        admin_headers(db_session, school),
        foreign.id,
        start_date="2026-10-01",
        end_date="2026-10-02",
    )

    assert response.status_code == 404
    assert "Secret" not in response.text


def test_detail_does_not_leak_pii(client, db_session, school):
    student = seed_student(db_session, school, admission_number="SP-1001")
    raw = detail(
        client,
        admin_headers(db_session, school),
        student.id,
        start_date="2026-10-01",
        end_date="2026-10-02",
    ).text

    for forbidden in ("date_of_birth", "gender", "token_hash", "credential", "scanned_by"):
        assert forbidden not in raw, f"{forbidden} leaked into the detail payload"


# ---------- timezone behaviour ----------


def test_history_default_range_uses_school_local_today(client, db_session, school):
    student = seed_student(db_session, school)
    headers = admin_headers(db_session, school)

    # 2026-10-04 20:00 UTC is 2026-10-05 01:00 in Asia/Karachi.
    late_utc = datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc)
    with frozen_clock(late_utc):
        body = history(client, headers, student.id).json()

    assert body["end_date"] == "2026-10-05"


def test_history_midnight_boundary_records_land_on_the_right_day(
    client, db_session, school
):
    """A scan just before and just after local midnight splits across days."""
    student = seed_student(db_session, school)
    headers = admin_headers(db_session, school)

    # 2026-10-04 18:59:59 UTC == 2026-10-04 23:59:59 PKT -> Oct 4
    just_before = datetime(2026, 10, 4, 18, 59, 59, tzinfo=timezone.utc)
    with frozen_clock(just_before):
        oct4 = detail(client, headers, student.id).json()
    assert oct4["end_date"] == "2026-10-04"

    # 2026-10-04 19:00:00 UTC == 2026-10-05 00:00:00 PKT -> Oct 5
    exactly_midnight = datetime(2026, 10, 4, 19, 0, 0, tzinfo=timezone.utc)
    with frozen_clock(exactly_midnight):
        oct5 = detail(client, headers, student.id).json()
    assert oct5["end_date"] == "2026-10-05"

    # The two local days are consecutive in the reported range.
    assert oct4["end_date"] == "2026-10-04"
    assert oct5["start_date"] == "2026-09-29"


def test_scan_then_dashboard_reflects_the_new_state(client, db_session, school):
    """Day 3 scan -> Day 4 dashboard shows the arrival, then the departure."""
    from backend.db.models import StudentStatusEnum  # noqa: F401

    student = seed_student(db_session, school, admission_number="SP-1001")
    headers = admin_headers(db_session, school)

    # Issue a credential and scan, exactly as Day 3 does.
    generated = client.post(
        f"/api/v1/students/{student.id}/qr",
        headers=admin_headers(db_session, school, "qr-admin"),
    )
    credential = generated.json()["credential"]

    scanner = teacher_headers(db_session, school, "scan-teacher")

    with frozen_clock(NOW):
        arrival_scan = client.post(
            "/api/v1/attendance/scan", json={"credential": credential}, headers=scanner
        )
        assert arrival_scan.json()["status"] == "ARRIVAL_RECORDED"

        summary_after_arrival = client.get(
            "/api/v1/attendance/summary", headers=headers
        ).json()
        assert summary_after_arrival["present"] == 1
        assert summary_after_arrival["absent"] == 0

        departure_scan = client.post(
            "/api/v1/attendance/scan", json={"credential": credential}, headers=scanner
        )
        assert departure_scan.json()["status"] == "DEPARTURE_RECORDED"

        summary_after_departure = client.get(
            "/api/v1/attendance/summary", headers=headers
        ).json()
        assert summary_after_departure["completed"] == 1
        assert summary_after_departure["present"] == 0

        listed = client.get("/api/v1/attendance/today", headers=headers).json()
        assert listed["items"][0]["status"] == "completed"
        assert listed["items"][0]["arrival_at"] is not None
        assert listed["items"][0]["departure_at"] is not None
