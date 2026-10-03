import uuid

from backend.db.models import RoleEnum
from tests.conftest import auth, make_token, seed_school, seed_user


def test_creator_becomes_school_admin(client, db_session):
    token = make_token("founder-1", "founder@school.pk")
    response = client.post(
        "/api/v1/schools",
        json={"name": "Crescent Public School", "admin_name": "Ali Khan"},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Crescent Public School"
    assert body["slug"] == "crescent-public-school"

    me = client.get("/api/v1/me", headers=auth(token))
    assert me.status_code == 200
    memberships = me.json()["memberships"]
    assert len(memberships) == 1
    assert memberships[0]["role"] == "school_admin"
    assert memberships[0]["school_id"] == body["id"]
    assert me.json()["user"]["full_name"] == "Ali Khan"


def test_school_slug_is_unique(client, db_session):
    token = make_token("founder-1")
    first = client.post("/api/v1/schools", json={"name": "Sunrise School"}, headers=auth(token))
    second = client.post("/api/v1/schools", json={"name": "Sunrise School"}, headers=auth(token))
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["slug"] != second.json()["slug"]


def test_school_name_is_validated(client):
    token = make_token("founder-1")
    response = client.post("/api/v1/schools", json={"name": "A"}, headers=auth(token))
    assert response.status_code == 422


def test_me_without_profile_returns_empty_memberships(client):
    token = make_token("nobody-1", "nobody@example.com")
    response = client.get("/api/v1/me", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == "nobody-1"
    assert body["memberships"] == []


def test_me_lists_all_memberships(client, db_session):
    school_a = seed_school(db_session, "School A")
    school_b = seed_school(db_session, "School B")
    seed_user(db_session, "multi-1", RoleEnum.teacher, school_a)
    seed_user(db_session, "multi-1", RoleEnum.parent, school_b)

    token = make_token("multi-1")
    response = client.get("/api/v1/me", headers=auth(token))
    assert response.status_code == 200
    roles = sorted(m["role"] for m in response.json()["memberships"])
    assert roles == ["parent", "teacher"]


def test_user_without_membership_cannot_create_classes(client):
    token = make_token("founder-1")
    school = client.post("/api/v1/schools", json={"name": "New School"}, headers=auth(token)).json()

    other = make_token("stranger-1")
    response = client.post(
        "/api/v1/classes",
        params={"school_id": school["id"]},
        json={"name": "Class 5", "section": "A"},
        headers=auth(other),
    )
    assert response.status_code == 403