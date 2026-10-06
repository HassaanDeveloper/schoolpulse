"""Day 4: today's attendance summary and list endpoints."""

from datetime import date, datetime, timezone

import pytest

from backend.db.models import RoleEnum
from tests.conftest import (
    auth,
    frozen_clock,
    make_token,
    seed_attendance,
    seed_class_named,
    seed_school,
    seed_student,
    seed_user,
)

SUMMARY_URL = "/api/v1/attendance/summary"
TODAY_URL = "/api/v1/attendance/today"

# A fixed "now" so the school's local date is deterministic.
TODAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc)  # 11:00 Asia/Karachi


@pytest.fixture()
def school(db_session):
    return seed_school(db_session, "Dashboard School")


@pytest.fixture()
def school_b(db_session):
    return seed_school(db_session, "Other School")


def admin_headers(db, school, user_id="dash-admin"):
    seed_user(db, user_id, RoleEnum.school_admin, school)
    return auth(make_token(user_id))


def teacher_headers(db, school, user_id="dash-teacher"):
    seed_user(db, user_id, RoleEnum.teacher, school)
    return auth(make_token(user_id))


def parent_headers(db, school, user_id="dash-parent"):
    seed_user(db, user_id, RoleEnum.parent, school)
    return auth(make_token(user_id))


def summary(client, headers, **params):
    return client.get(SUMMARY_URL, headers=headers, params=params)


def today(client, headers, **params):
    return client.get(TODAY_URL, headers=headers, params=params)


# ---------- authorization ----------


@pytest.mark.parametrize("url", [SUMMARY_URL, TODAY_URL])
def test_unauthenticated_returns_401(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", [SUMMARY_URL, TODAY_URL])
def test_parent_is_forbidden(client, db_session, school, url):
    assert client.get(url, headers=parent_headers(db_session, school)).status_code == 403


def test_admin_may_read_summary(client, db_session, school):
    seed_student(db_session, school)
    response = summary(client, admin_headers(db_session, school))
    assert response.status_code == 200, response.text


def test_teacher_may_read_summary(client, db_session, school):
    seed_student(db_session, school)
    response = summary(client, teacher_headers(db_session, school))
    assert response.status_code == 200, response.text


def test_user_with_no_school_gets_403(client, db_session):
    seed_user(db_session, "orphan", RoleEnum.teacher, seed_school(db_session, "Tmp"))
    # Strip the membership so the caller has no eligible school at all.
    from backend.db.models import SchoolMembership

    db_session.query(SchoolMembership).delete()
    db_session.commit()

    assert summary(client, auth(make_token("orphan"))).status_code == 403


def test_profile_without_memberships_is_rejected(client, db_session):
    from backend.db.models import UserProfile

    db_session.add(UserProfile(auth_user_id="ghost"))
    db_session.commit()

    assert summary(client, auth(make_token("ghost"))).status_code == 403


# ---------- summary counts ----------


def test_summary_with_no_students(client, db_session, school):
    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["total_students"] == 0
    assert body["absent"] == 0
    assert body["present"] == 0
    assert body["completed"] == 0
    assert body["date"] == "2026-10-04"


def test_summary_counts_every_status(client, db_session, school):
    absent = seed_student(db_session, school, admission_number="ADM-A1", first_name="Zara")
    present = seed_student(db_session, school, admission_number="ADM-A2", first_name="Yusuf")
    completed = seed_student(db_session, school, admission_number="ADM-A3", first_name="Xina")

    seed_attendance(db_session, present, TODAY, departure_at=None)
    seed_attendance(
        db_session,
        completed,
        TODAY,
        departure_at=datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc),
    )

    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["total_students"] == 3
    assert body["absent"] == 1
    assert body["present"] == 1
    assert body["completed"] == 1
    assert body["absent"] + body["present"] + body["completed"] == body["total_students"]
    assert absent.id is not None


def test_summary_counts_sum_to_total(client, db_session, school):
    for index in range(7):
        student = seed_student(db_session, school, admission_number=f"ADM-{index}")
        if index % 3 == 0:
            continue
        if index % 3 == 1:
            seed_attendance(db_session, student, TODAY, departure_at=None)
        else:
            seed_attendance(
                db_session,
                student,
                TODAY,
                departure_at=datetime(2026, 10, 4, 11, 0, tzinfo=timezone.utc),
            )

    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["absent"] + body["present"] + body["completed"] == body["total_students"]
    assert body["total_students"] == 7


def test_summary_ignores_other_days_records(client, db_session, school):
    student = seed_student(db_session, school)

    # Yesterday's arrival must not make the student present today.
    seed_attendance(db_session, student, date(2026, 10, 3), departure_at=None)

    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["absent"] == 1
    assert body["present"] == 0


def test_summary_excludes_inactive_students(client, db_session, school):
    from backend.db.models import StudentStatusEnum

    seed_student(db_session, school, admission_number="ADM-ACTIVE")
    seed_student(
        db_session,
        school,
        admission_number="ADM-INACTIVE",
        status=StudentStatusEnum.inactive,
    )

    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    # An inactive student can never be scanned, so counting them would
    # permanently inflate ABSENT.
    assert body["total_students"] == 1
    assert body["absent"] == 1


def test_summary_is_school_scoped(client, db_session, school, school_b):
    for index in range(3):
        seed_student(db_session, school, admission_number=f"A-{index}")
    for index in range(5):
        seed_student(db_session, school_b, admission_number=f"B-{index}")

    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["total_students"] == 3
    assert body["school_id"] == str(school.id)


def test_client_supplied_other_school_id_is_refused(client, db_session, school, school_b):
    seed_student(db_session, school_b, admission_number="B-1")

    with frozen_clock(NOW):
        response = summary(
            client,
            admin_headers(db_session, school),
            school_id=str(school_b.id),
        )

    assert response.status_code == 403


def test_multi_school_user_must_name_the_school(client, db_session, school, school_b):
    headers = admin_headers(db_session, school, "multi")
    seed_user(db_session, "multi", RoleEnum.school_admin, school_b)
    seed_student(db_session, school, admission_number="A-1")
    seed_student(db_session, school_b, admission_number="B-1")

    with frozen_clock(NOW):
        ambiguous = summary(client, headers)
        explicit = summary(client, headers, school_id=str(school.id))
        other = summary(client, headers, school_id=str(school_b.id))

    assert ambiguous.status_code == 400
    assert explicit.json()["total_students"] == 1
    assert other.json()["total_students"] == 1


# ---------- class filtering ----------


def test_summary_class_filter(client, db_session, school):
    grade6 = seed_class_named(db_session, school, "Grade 6", "A")
    grade7 = seed_class_named(db_session, school, "Grade 7", "A")

    for index in range(2):
        seed_student(
            db_session, school, grade6, admission_number=f"G6-{index}", first_name=f"Six{index}"
        )
    for index in range(4):
        seed_student(
            db_session, school, grade7, admission_number=f"G7-{index}", first_name=f"Seven{index}"
        )

    headers = admin_headers(db_session, school)

    with frozen_clock(NOW):
        all_classes = summary(client, headers).json()
        filtered = summary(client, headers, class_id=str(grade6.id)).json()

    assert all_classes["total_students"] == 6
    assert filtered["total_students"] == 2
    assert filtered["class_id"] == str(grade6.id)


def test_class_from_another_school_is_not_usable(client, db_session, school, school_b):
    class_b = seed_class_named(db_session, school_b, "Grade 9", "B")
    seed_student(db_session, school, admission_number="A-1")
    headers = admin_headers(db_session, school)

    with frozen_clock(NOW):
        response = summary(client, headers, class_id=str(class_b.id))

    assert response.status_code == 404
    assert "Grade 9" not in response.text


def test_unknown_class_is_404(client, db_session, school):
    headers = admin_headers(db_session, school)
    with frozen_clock(NOW):
        response = summary(
            client,
            headers,
            class_id="00000000-0000-4000-8000-000000000000",
        )
    assert response.status_code == 404


def test_class_options_are_school_scoped(client, db_session, school, school_b):
    seed_class_named(db_session, school, "Grade 6", "A")
    seed_class_named(db_session, school, "Grade 6", "B")
    seed_class_named(db_session, school_b, "Grade 9", "Z")

    response = client.get(
        "/api/v1/attendance/classes", headers=admin_headers(db_session, school)
    )

    assert response.status_code == 200
    labels = sorted(item["name"] + "-" + (item["section"] or "") for item in response.json())
    assert labels == ["Grade 6-A", "Grade 6-B"]


# ---------- today's list ----------


def test_today_lists_students_with_derived_status(client, db_session, school):
    absent = seed_student(db_session, school, admission_number="ADM-1", first_name="Absent")
    present = seed_student(db_session, school, admission_number="ADM-2", first_name="Present")
    completed = seed_student(db_session, school, admission_number="ADM-3", first_name="Complete")

    seed_attendance(db_session, present, TODAY, departure_at=None)
    seed_attendance(
        db_session,
        completed,
        TODAY,
        departure_at=datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc),
    )

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school)).json()

    by_admission = {item["admission_number"]: item for item in body["items"]}
    assert by_admission["ADM-1"]["status"] == "absent"
    assert by_admission["ADM-1"]["arrival_at"] is None
    assert by_admission["ADM-2"]["status"] == "present"
    assert by_admission["ADM-2"]["arrival_at"] is not None
    assert by_admission["ADM-2"]["departure_at"] is None
    assert by_admission["ADM-3"]["status"] == "completed"
    assert by_admission["ADM-3"]["departure_at"] is not None

    assert body["total"] == 3
    assert by_admission["ADM-1"]["student_id"] == str(absent.id)
    assert present.id is not None and completed.id is not None


def test_today_includes_class_name_and_section(client, db_session, school):
    school_class = seed_class_named(db_session, school, "Grade 8", "B")
    seed_student(db_session, school, school_class, admission_number="ADM-1")

    with frozen_clock(NOW):
        item = today(client, admin_headers(db_session, school)).json()["items"][0]

    assert item["class_name"] == "Grade 8"
    assert item["section"] == "B"


def test_today_excludes_unnecessary_student_pii(client, db_session, school):
    from backend.db.models import StudentStatusEnum

    seed_student(db_session, school, admission_number="ADM-1")

    with frozen_clock(NOW):
        raw = today(client, admin_headers(db_session, school)).text

    for forbidden in (
        "date_of_birth",
        "gender",
        "token_hash",
        "credential",
        "arrival_scanned_by",
        "departure_scanned_by",
    ):
        assert forbidden not in raw, f"{forbidden} leaked into the dashboard payload"


def test_today_timestamps_are_returned(client, db_session, school):
    student = seed_student(db_session, school, admission_number="ADM-1")
    arrival = datetime(2026, 10, 4, 3, 4, tzinfo=timezone.utc)
    seed_attendance(db_session, student, TODAY, arrival_at=arrival, departure_at=None)

    with frozen_clock(NOW):
        item = today(client, admin_headers(db_session, school)).json()["items"][0]

    assert item["arrival_at"] is not None
    assert item["status"] == "present"


# ---------- search ----------


def test_search_by_first_name(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1", first_name="Ali", last_name="Khan")
    seed_student(db_session, school, admission_number="ADM-2", first_name="Sara", last_name="Noor")

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school), search="Ali").json()

    assert body["total"] == 1
    assert body["items"][0]["student_name"] == "Ali Khan"


def test_search_by_last_name(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1", first_name="Ali", last_name="Khan")
    seed_student(db_session, school, admission_number="ADM-2", first_name="Sara", last_name="Noor")

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school), search="Noor").json()

    assert body["total"] == 1
    assert body["items"][0]["admission_number"] == "ADM-2"


def test_search_by_admission_number(client, db_session, school):
    seed_student(db_session, school, admission_number="SP-1001", first_name="Ali")
    seed_student(db_session, school, admission_number="SP-2002", first_name="Sara")

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school), search="SP-1001").json()

    assert body["total"] == 1
    assert body["items"][0]["admission_number"] == "SP-1001"


def test_search_is_case_insensitive(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1", first_name="Ali")

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school), search="ali").json()

    assert body["total"] == 1


def test_search_with_no_match_returns_empty_page(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1", first_name="Ali")

    with frozen_clock(NOW):
        response = today(client, admin_headers(db_session, school), search="Nobody")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


# ---------- status filtering ----------


@pytest.mark.parametrize(
    "filter_value,expected_total",
    [("absent", 2), ("present", 1), ("completed", 1)],
)
def test_status_filter(client, db_session, school, filter_value, expected_total):
    seed_student(db_session, school, admission_number="ADM-1", first_name="NoShow1")
    seed_student(db_session, school, admission_number="ADM-2", first_name="NoShow2")
    arrived = seed_student(db_session, school, admission_number="ADM-3", first_name="Here")
    gone = seed_student(db_session, school, admission_number="ADM-4", first_name="Done")

    seed_attendance(db_session, arrived, TODAY, departure_at=None)
    seed_attendance(
        db_session,
        gone,
        TODAY,
        departure_at=datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc),
    )

    with frozen_clock(NOW):
        body = today(
            client, admin_headers(db_session, school), status=filter_value
        ).json()

    assert body["total"] == expected_total
    assert all(item["status"] == filter_value for item in body["items"])


def test_invalid_status_filter_is_422(client, db_session, school):
    with frozen_clock(NOW):
        response = today(client, admin_headers(db_session, school), status="teleported")

    assert response.status_code == 422


def test_status_filter_combines_with_class_and_search(client, db_session, school):
    grade6 = seed_class_named(db_session, school, "Grade 6", "A")
    grade7 = seed_class_named(db_session, school, "Grade 7", "A")

    target = seed_student(db_session, school, grade6, admission_number="ADM-1", first_name="Ali")
    seed_student(db_session, school, grade6, admission_number="ADM-2", first_name="Bilal")
    seed_student(db_session, school, grade7, admission_number="ADM-3", first_name="Ali")
    seed_attendance(db_session, target, TODAY, departure_at=None)

    with frozen_clock(NOW):
        body = today(
            client,
            admin_headers(db_session, school),
            class_id=str(grade6.id),
            search="Ali",
            status="present",
        ).json()

    assert body["total"] == 1
    assert body["items"][0]["admission_number"] == "ADM-1"


# ---------- pagination ----------


def test_pagination(client, db_session, school):
    for index in range(7):
        seed_student(
            db_session,
            school,
            admission_number=f"ADM-{index:02d}",
            first_name=f"Student{index:02d}",
        )

    headers = admin_headers(db_session, school)

    with frozen_clock(NOW):
        first = today(client, headers, page=1, page_size=3).json()
        second = today(client, headers, page=2, page_size=3).json()
        third = today(client, headers, page=3, page_size=3).json()

    assert first["total"] == 7
    assert len(first["items"]) == 3
    assert len(second["items"]) == 3
    assert len(third["items"]) == 1
    assert first["page"] == 1
    assert first["page_size"] == 3

    seen = [item["admission_number"] for page in (first, second, third) for item in page["items"]]
    assert len(set(seen)) == 7, "pages must not repeat students"


def test_page_beyond_end_is_empty(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1")

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school), page=9, page_size=20).json()

    assert body["items"] == []
    assert body["total"] == 1


def test_page_size_is_capped_at_100(client, db_session, school):
    headers = admin_headers(db_session, school)
    with frozen_clock(NOW):
        assert today(client, headers, page_size=100).status_code == 200
        assert today(client, headers, page_size=101).status_code == 422


def test_page_size_must_be_positive(client, db_session, school):
    headers = admin_headers(db_session, school)
    with frozen_clock(NOW):
        assert today(client, headers, page_size=0).status_code == 422
        assert today(client, headers, page=0).status_code == 422


def test_default_page_size(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1")

    with frozen_clock(NOW):
        body = today(client, admin_headers(db_session, school)).json()

    assert body["page"] == 1
    assert body["page_size"] == 20


# ---------- timezone reuse ----------


def test_summary_uses_school_local_date(client, db_session, school):
    """Late UTC is already the next day in Karachi, and the dashboard follows."""
    seed_student(db_session, school, admission_number="ADM-1")
    headers = admin_headers(db_session, school)

    # 2026-10-04 20:00 UTC == 2026-10-05 01:00 in Asia/Karachi (UTC+5).
    late_utc = datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc)

    with frozen_clock(late_utc):
        body = summary(client, headers).json()

    assert body["date"] == "2026-10-05"


def test_summary_respects_a_custom_school_timezone(client, db_session, school):
    school.timezone = "Pacific/Kiritimati"  # UTC+14
    db_session.commit()
    seed_student(db_session, school, admission_number="ADM-1")

    # 2026-10-04 12:00 UTC == 2026-10-05 02:00 in UTC+14.
    with frozen_clock(datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["date"] == "2026-10-05"


def test_client_cannot_choose_the_date(client, db_session, school):
    seed_student(db_session, school, admission_number="ADM-1")

    with frozen_clock(NOW):
        response = summary(client, admin_headers(db_session, school), date="2020-01-01")

    # The unknown `date` parameter is ignored; the server's local date wins.
    assert response.status_code == 200
    assert response.json()["date"] == "2026-10-04"


# ---------- cross-tenant isolation ----------


def test_today_never_leaks_another_school(client, db_session, school, school_b):
    seed_student(db_session, school, admission_number="A-1", first_name="Visible")
    seed_student(db_session, school_b, admission_number="B-1", first_name="Secret")

    with frozen_clock(NOW):
        response = today(client, admin_headers(db_session, school))

    assert response.status_code == 200
    assert "Secret" not in response.text
    assert response.json()["total"] == 1


def test_other_school_teacher_sees_only_their_school(client, db_session, school, school_b):
    seed_student(db_session, school, admission_number="A-1", first_name="Alpha")
    seed_student(db_session, school_b, admission_number="B-1", first_name="Bravo")

    with frozen_clock(NOW):
        body = today(client, teacher_headers(db_session, school_b)).json()

    assert body["total"] == 1
    assert body["items"][0]["student_name"] == "Bravo Khan"
    assert body["school_id"] == str(school_b.id)


def test_teacher_cannot_pass_another_schools_class_id(client, db_session, school, school_b):
    class_b = seed_class_named(db_session, school_b, "Grade 9", "A")
    seed_student(db_session, school_b, class_b, admission_number="B-1")

    with frozen_clock(NOW):
        response = today(
            client,
            teacher_headers(db_session, school),
            class_id=str(class_b.id),
        )

    assert response.status_code == 404


# ---------- input handling ----------


def test_search_treats_sql_metacharacters_as_plain_text(client, db_session, school):
    """A search term is data, never SQL. These students must still be found."""
    seed_student(db_session, school, admission_number="A-1", first_name="O'Brien")
    seed_student(db_session, school, admission_number="A-2", first_name="Ada")
    seed_student(db_session, school, admission_number="A-3", first_name="100%")

    injection = "Robert'); DROP TABLE students;--"
    seed_student(db_session, school, admission_number="A-4", first_name=injection)

    headers = admin_headers(db_session, school)
    with frozen_clock(NOW):
        for term, expected in (
            ("O'Brien", "O'Brien Khan"),
            ("100%", "100% Khan"),
            (injection, f"{injection} Khan"),
        ):
            body = today(client, headers, search=term).json()
            assert body["total"] == 1, term
            assert body["items"][0]["student_name"] == expected

        # A tautology must not return every student.
        assert today(client, headers, search="' OR '1'='1").json()["total"] == 0

        # The students table is still there.
        assert today(client, headers).json()["total"] == 4


def test_search_cannot_reach_another_school_through_wildcards(client, db_session, school, school_b):
    seed_student(db_session, school, admission_number="A-1", first_name="Alpha")
    seed_student(db_session, school_b, admission_number="B-1", first_name="Bravo")

    with frozen_clock(NOW):
        # % is a wildcard the caller controls, but the school filter still holds.
        body = today(client, teacher_headers(db_session, school_b), search="%").json()

    assert body["total"] == 1
    assert body["items"][0]["student_name"] == "Bravo Khan"


def test_blank_search_is_ignored(client, db_session, school):
    seed_student(db_session, school, admission_number="A-1", first_name="Alpha")
    seed_student(db_session, school, admission_number="A-2", first_name="Bravo")

    headers = admin_headers(db_session, school)
    with frozen_clock(NOW):
        assert today(client, headers, search="   ").json()["total"] == 2


def test_page_size_is_bounded(client, db_session, school):
    seed_student(db_session, school, admission_number="A-1")
    headers = admin_headers(db_session, school)

    with frozen_clock(NOW):
        assert today(client, headers, page_size=101).status_code == 422
        assert today(client, headers, page_size=100).status_code == 200
        assert today(client, headers, page=0).status_code == 422


def test_absent_totals_are_not_negative(client, db_session, school):
    """The reconciliation fallback must never invent counts beyond the total."""
    for index in range(3):
        seed_student(db_session, school, admission_number=f"A-{index}")

    with frozen_clock(NOW):
        body = summary(client, admin_headers(db_session, school)).json()

    assert body["absent"] == 3
    assert body["absent"] + body["present"] + body["completed"] == body["total_students"]
