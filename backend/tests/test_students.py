import uuid

import pytest

from backend.db.models import RoleEnum
from tests.conftest import auth, make_token, seed_school, seed_user


@pytest.fixture()
def school_a(db_session):
    return seed_school(db_session, "School A")


@pytest.fixture()
def school_b(db_session):
    return seed_school(db_session, "School B")


def admin_headers(db, school, user_id="admin-a"):
    seed_user(db, user_id, RoleEnum.school_admin, school)
    return auth(make_token(user_id))


def teacher_headers(db, school, user_id="teacher-a"):
    seed_user(db, user_id, RoleEnum.teacher, school)
    return auth(make_token(user_id))


def parent_headers(db, school, user_id="parent-a"):
    seed_user(db, user_id, RoleEnum.parent, school)
    return auth(make_token(user_id))


def make_class(client, headers, school_id, name="Class 5", section="A"):
    response = client.post(
        "/api/v1/classes",
        params={"school_id": str(school_id)},
        json={"name": name, "section": section, "academic_year": "2026"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_student(client, headers, school_id, class_id, admission_number="ADM-001", **extra):
    payload = {
        "admission_number": admission_number,
        "first_name": "Ayesha",
        "last_name": "Khan",
        "class_id": str(class_id),
        **extra,
    }
    return client.post(
        "/api/v1/students",
        params={"school_id": str(school_id)},
        json=payload,
        headers=headers,
    )


# ---------- create ----------


def test_admin_can_create_student(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)

    response = make_student(client, headers, school_a.id, class_a["id"], "ADM-100")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["first_name"] == "Ayesha"
    assert body["status"] == "active"
    assert body["school_id"] == str(school_a.id)
    assert body["class_id"] == class_a["id"]


def test_teacher_cannot_create_student(client, db_session, school_a):
    headers = teacher_headers(db_session, school_a)
    class_a = make_class(client, admin_headers(db_session, school_a), school_a.id)
    response = make_student(client, headers, school_a.id, class_a["id"])
    assert response.status_code == 403


def test_parent_cannot_create_student(client, db_session, school_a):
    headers = parent_headers(db_session, school_a)
    class_a = make_class(client, admin_headers(db_session, school_a), school_a.id)
    response = make_student(client, headers, school_a.id, class_a["id"])
    assert response.status_code == 403


def test_missing_names_are_rejected(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)

    response = client.post(
        "/api/v1/students",
        params={"school_id": str(school_a.id)},
        json={"admission_number": "ADM-1", "first_name": "", "last_name": "Khan", "class_id": class_a["id"]},
        headers=headers,
    )
    assert response.status_code == 422


def test_invalid_date_of_birth_is_rejected(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    response = make_student(
        client, headers, school_a.id, class_a["id"], "ADM-1", date_of_birth="03/10/2026"
    )
    assert response.status_code == 422


def test_invalid_status_is_rejected(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    response = make_student(client, headers, school_a.id, class_a["id"], "ADM-1", status="expelled")
    assert response.status_code == 422


def test_unknown_class_is_rejected(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    response = make_student(client, headers, school_a.id, uuid.uuid4(), "ADM-1")
    assert response.status_code == 404


# ---------- cross-school validation ----------


def test_cross_school_class_assignment_is_rejected(client, db_session, school_a, school_b):
    headers_a = admin_headers(db_session, school_a, "admin-a")
    class_b = make_class(client, admin_headers(db_session, school_b, "admin-b"), school_b.id)

    response = make_student(client, headers_a, school_a.id, class_b["id"], "ADM-200")
    assert response.status_code == 422
    assert "does not belong" in response.json()["detail"]


def test_duplicate_admission_number_in_same_school_returns_409(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)

    assert make_student(client, headers, school_a.id, class_a["id"], "ADM-DUP").status_code == 201
    assert make_student(client, headers, school_a.id, class_a["id"], "ADM-DUP").status_code == 409


def test_same_admission_number_allowed_in_different_schools(client, db_session, school_a, school_b):
    headers_a = admin_headers(db_session, school_a, "admin-a")
    class_a = make_class(client, headers_a, school_a.id)

    headers_b = admin_headers(db_session, school_b, "admin-b")
    class_b = make_class(client, headers_b, school_b.id)

    assert make_student(client, headers_a, school_a.id, class_a["id"], "ADM-SAME").status_code == 201
    assert make_student(client, headers_b, school_b.id, class_b["id"], "ADM-SAME").status_code == 201


# ---------- listing, pagination, search ----------


def test_admin_can_list_students(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    make_student(client, headers, school_a.id, class_a["id"], "ADM-1")

    response = client.get(
        "/api/v1/students", params={"school_id": str(school_a.id)}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_teacher_can_list_students(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    make_student(client, headers, school_a.id, class_a["id"], "ADM-1")

    response = client.get("/api/v1/students", headers=teacher_headers(db_session, school_a))
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_parent_cannot_list_students(client, db_session, school_a):
    response = client.get("/api/v1/students", headers=parent_headers(db_session, school_a))
    assert response.status_code == 403


def test_pagination_is_enforced(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    for i in range(5):
        make_student(client, headers, school_a.id, class_a["id"], f"ADM-{i}")

    response = client.get(
        "/api/v1/students",
        params={"school_id": str(school_a.id), "page": 1, "page_size": 2},
        headers=headers,
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["total"] == 5
    assert response.json()["page"] == 1


def test_page_size_above_limit_is_rejected(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    response = client.get(
        "/api/v1/students",
        params={"school_id": str(school_a.id), "page_size": 500},
        headers=headers,
    )
    assert response.status_code == 422


def test_search_filters_students(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    make_student(client, headers, school_a.id, class_a["id"], "ADM-1", first_name="Ayesha")
    make_student(client, headers, school_a.id, class_a["id"], "ADM-2", first_name="Bilal")

    response = client.get(
        "/api/v1/students",
        params={"school_id": str(school_a.id), "search": "Bilal"},
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["first_name"] == "Bilal"


# ---------- cross-school isolation ----------


def test_listing_never_leaks_other_school_students(client, db_session, school_a, school_b):
    headers_b = admin_headers(db_session, school_b, "admin-b")
    class_b = make_class(client, headers_b, school_b.id)
    make_student(client, headers_b, school_b.id, class_b["id"], "ADM-B1", first_name="Secret")

    response = client.get("/api/v1/students", headers=admin_headers(db_session, school_a, "admin-a"))
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_cannot_read_other_school_student(client, db_session, school_a, school_b):
    headers_b = admin_headers(db_session, school_b, "admin-b")
    class_b = make_class(client, headers_b, school_b.id)
    student_b = make_student(client, headers_b, school_b.id, class_b["id"], "ADM-B1").json()

    response = client.get(
        f"/api/v1/students/{student_b['id']}",
        headers=admin_headers(db_session, school_a, "admin-a"),
    )
    assert response.status_code == 404


def test_cannot_update_other_school_student(client, db_session, school_a, school_b):
    headers_b = admin_headers(db_session, school_b, "admin-b")
    class_b = make_class(client, headers_b, school_b.id)
    student_b = make_student(client, headers_b, school_b.id, class_b["id"], "ADM-B1").json()

    response = client.patch(
        f"/api/v1/students/{student_b['id']}",
        json={"first_name": "Hijacked"},
        headers=admin_headers(db_session, school_a, "admin-a"),
    )
    assert response.status_code == 404


def test_cannot_deactivate_other_school_student(client, db_session, school_a, school_b):
    headers_b = admin_headers(db_session, school_b, "admin-b")
    class_b = make_class(client, headers_b, school_b.id)
    student_b = make_student(client, headers_b, school_b.id, class_b["id"], "ADM-B1").json()

    response = client.delete(
        f"/api/v1/students/{student_b['id']}",
        headers=admin_headers(db_session, school_a, "admin-a"),
    )
    assert response.status_code == 404

    unchanged = client.get(
        f"/api/v1/students/{student_b['id']}", headers=headers_b
    )
    assert unchanged.json()["status"] == "active"


def test_client_supplied_school_id_cannot_bypass_authorization(client, db_session, school_a, school_b):
    headers_a = admin_headers(db_session, school_a, "admin-a")
    class_b = make_class(client, admin_headers(db_session, school_b, "admin-b"), school_b.id)

    response = client.post(
        "/api/v1/students",
        params={"school_id": str(school_b.id)},
        json={
            "admission_number": "ADM-X",
            "first_name": "Mallory",
            "last_name": "Malone",
            "class_id": class_b["id"],
        },
        headers=headers_a,
    )
    assert response.status_code == 403


# ---------- update / deactivate ----------


def test_admin_can_update_student(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    student = make_student(client, headers, school_a.id, class_a["id"], "ADM-1").json()

    response = client.patch(
        f"/api/v1/students/{student['id']}",
        json={"first_name": "Ayesha", "last_name": "Ahmed"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["last_name"] == "Ahmed"


def test_admin_can_move_student_to_another_class_in_same_school(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    class_b = make_class(client, headers, school_a.id, name="Class 5", section="B")
    student = make_student(client, headers, school_a.id, class_a["id"], "ADM-1").json()

    response = client.patch(
        f"/api/v1/students/{student['id']}",
        json={"class_id": class_b["id"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["class_id"] == class_b["id"]


def test_update_to_class_in_other_school_is_rejected(client, db_session, school_a, school_b):
    headers_a = admin_headers(db_session, school_a, "admin-a")
    class_a = make_class(client, headers_a, school_a.id)
    student_a = make_student(client, headers_a, school_a.id, class_a["id"], "ADM-1").json()

    class_b = make_class(client, admin_headers(db_session, school_b, "admin-b"), school_b.id)
    response = client.patch(
        f"/api/v1/students/{student_a['id']}",
        json={"class_id": class_b["id"]},
        headers=headers_a,
    )
    assert response.status_code == 422


def test_admin_can_deactivate_student(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    student = make_student(client, headers, school_a.id, class_a["id"], "ADM-1").json()

    response = client.delete(f"/api/v1/students/{student['id']}", headers=headers)
    assert response.status_code == 204

    after = client.get(f"/api/v1/students/{student['id']}", headers=headers)
    assert after.status_code == 200
    assert after.json()["status"] == "inactive"


def test_teacher_cannot_deactivate_student(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    class_a = make_class(client, headers, school_a.id)
    student = make_student(client, headers, school_a.id, class_a["id"], "ADM-1").json()

    response = client.delete(
        f"/api/v1/students/{student['id']}", headers=teacher_headers(db_session, school_a)
    )
    assert response.status_code == 403