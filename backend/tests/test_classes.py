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


def create_class(client, headers, school_id, name="Class 5", section="A"):
    return client.post(
        "/api/v1/classes",
        params={"school_id": str(school_id)},
        json={"name": name, "section": section, "academic_year": "2026"},
        headers=headers,
    )


# ---------- creation ----------


def test_school_admin_can_create_class(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    response = create_class(client, headers, school_a.id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Class 5"
    assert body["section"] == "A"
    assert body["school_id"] == str(school_a.id)


def test_teacher_cannot_create_class(client, db_session, school_a):
    response = create_class(client, teacher_headers(db_session, school_a), school_a.id)
    assert response.status_code == 403


def test_parent_cannot_create_class(client, db_session, school_a):
    response = create_class(client, parent_headers(db_session, school_a), school_a.id)
    assert response.status_code == 403


def test_duplicate_class_returns_409(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    assert create_class(client, headers, school_a.id).status_code == 201
    duplicate = create_class(client, headers, school_a.id)
    assert duplicate.status_code == 409


# ---------- listing ----------


def test_school_admin_can_list_classes(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    create_class(client, headers, school_a.id)
    response = client.get(
        "/api/v1/classes", params={"school_id": str(school_a.id)}, headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_teacher_can_list_classes(client, db_session, school_a, school_b):
    create_class(client, admin_headers(db_session, school_a, "admin-a"), school_a.id)
    create_class(
        client,
        admin_headers(db_session, school_b, "admin-b"),
        school_b.id,
        name="Class 9",
        section="B",
    )

    response = client.get("/api/v1/classes", headers=teacher_headers(db_session, school_a))
    assert response.status_code == 200
    rows = response.json()
    assert [r["school_id"] for r in rows] == [str(school_a.id)]


def test_parent_cannot_list_classes(client, db_session, school_a):
    response = client.get("/api/v1/classes", headers=parent_headers(db_session, school_a))
    assert response.status_code == 403


# ---------- cross-school isolation ----------


def test_admin_cannot_create_class_in_other_school(client, db_session, school_a, school_b):
    headers = admin_headers(db_session, school_a, "admin-a")
    response = create_class(client, headers, school_b.id)
    assert response.status_code == 403


def test_admin_cannot_read_other_school_class(client, db_session, school_a, school_b):
    created_b = create_class(
        client, admin_headers(db_session, school_b, "admin-b"), school_b.id
    ).json()

    response = client.get(
        f"/api/v1/classes/{created_b['id']}", headers=admin_headers(db_session, school_a, "admin-a")
    )
    assert response.status_code == 404


def test_admin_cannot_update_other_school_class(client, db_session, school_a, school_b):
    created_b = create_class(
        client, admin_headers(db_session, school_b, "admin-b"), school_b.id
    ).json()

    response = client.patch(
        f"/api/v1/classes/{created_b['id']}",
        json={"name": "Hijacked"},
        headers=admin_headers(db_session, school_a, "admin-a"),
    )
    assert response.status_code == 404


def test_admin_cannot_delete_other_school_class(client, db_session, school_a, school_b):
    created_b = create_class(
        client, admin_headers(db_session, school_b, "admin-b"), school_b.id
    ).json()

    response = client.delete(
        f"/api/v1/classes/{created_b['id']}",
        headers=admin_headers(db_session, school_a, "admin-a"),
    )
    assert response.status_code == 404


def test_listing_classes_never_leaks_other_school(client, db_session, school_a, school_b):
    create_class(client, admin_headers(db_session, school_b, "admin-b"), school_b.id, name="Secret Class")

    response = client.get("/api/v1/classes", headers=admin_headers(db_session, school_a, "admin-a"))
    assert response.status_code == 200
    assert all(row["name"] != "Secret Class" for row in response.json())


# ---------- update / delete ----------


def test_admin_can_update_class(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    created = create_class(client, headers, school_a.id).json()

    response = client.patch(
        f"/api/v1/classes/{created['id']}",
        json={"name": "Class 6", "section": "C"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Class 6"
    assert response.json()["section"] == "C"


def test_admin_can_delete_class(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    created = create_class(client, headers, school_a.id).json()

    response = client.delete(f"/api/v1/classes/{created['id']}", headers=headers)
    assert response.status_code == 204

    assert client.get(f"/api/v1/classes/{created['id']}", headers=headers).status_code == 404


def test_class_with_students_cannot_be_deleted(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    created = create_class(client, headers, school_a.id).json()

    student = client.post(
        "/api/v1/students",
        params={"school_id": str(school_a.id)},
        json={
            "admission_number": "ADM-1",
            "first_name": "Ayesha",
            "last_name": "Khan",
            "class_id": created["id"],
        },
        headers=headers,
    )
    assert student.status_code == 201

    response = client.delete(f"/api/v1/classes/{created['id']}", headers=headers)
    assert response.status_code == 409


def test_unknown_class_returns_404(client, db_session, school_a):
    headers = admin_headers(db_session, school_a)
    response = client.get(f"/api/v1/classes/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404