"""Day 6: the admin console needs to find an existing parent account.

The mobile parent-linking screen has to offer an administrator a way to choose
a guardian, but `POST /students/{id}/parents` needs a `user_id`. `GET /parents`
is the smallest safe answer: a read-only directory of accounts that already hold
a `parent` membership in the caller's own school.

These tests treat it as a security surface, because that is what it is: it is
the one route that enumerates people.
"""

import pytest

from backend.db.models import RoleEnum
from tests.conftest import auth, make_token, seed_school, seed_user

DIRECTORY_URL = "/api/v1/parents"


@pytest.fixture()
def school(db_session):
    return seed_school(db_session, "Directory School")


@pytest.fixture()
def other_school(db_session):
    return seed_school(db_session, "Rival School")


def _seed_parent(db, school, auth_user_id, email, full_name):
    profile = seed_user(db, auth_user_id, RoleEnum.parent, school, email=email)
    profile.full_name = full_name
    db.commit()
    db.refresh(profile)
    return profile


def test_admin_lists_the_parent_accounts_of_their_school(client, db_session, school):
    _seed_parent(db_session, school, "parent-1", "ahmed@example.com", "Ahmed Khan")
    _seed_parent(db_session, school, "parent-2", "sara@example.com", "Sara Khan")
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)
    # A teacher at the same school is staff, not a linkable guardian.
    seed_user(db_session, "teacher-1", RoleEnum.teacher, school)

    response = client.get(
        DIRECTORY_URL,
        headers=auth(make_token("admin-1")),
    )

    assert response.status_code == 200
    body = response.json()
    names = sorted(entry["full_name"] for entry in body["parents"])
    assert names == ["Ahmed Khan", "Sara Khan"]
    assert {entry["email"] for entry in body["parents"]} == {
        "ahmed@example.com",
        "sara@example.com",
    }
    # Only the id, a name and an email: no children, no attendance, no tokens.
    assert set(body["parents"][0]) == {"user_id", "full_name", "email"}


def test_directory_never_shows_parents_of_another_school(
    client, db_session, school, other_school
):
    _seed_parent(db_session, school, "parent-1", "ahmed@example.com", "Ahmed Khan")
    _seed_parent(db_session, other_school, "outsider-1", "outsider@example.com", "Outsider")
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)

    response = client.get(DIRECTORY_URL, headers=auth(make_token("admin-1")))

    assert response.status_code == 200
    emails = {entry["email"] for entry in response.json()["parents"]}
    assert emails == {"ahmed@example.com"}


def test_admin_of_another_school_is_told_the_school_does_not_exist(
    client, db_session, school, other_school
):
    _seed_parent(db_session, other_school, "outsider-1", "outsider@example.com", "Outsider")
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)

    response = client.get(
        f"{DIRECTORY_URL}?school_id={other_school.id}",
        headers=auth(make_token("admin-1")),
    )

    # 404 rather than 403: an admin must not be able to confirm that another
    # school's id exists.
    assert response.status_code == 404


def test_a_parent_linked_at_two_schools_appears_under_each_school(
    client, db_session, school, other_school
):
    profile = _seed_parent(db_session, school, "parent-1", "ahmed@example.com", "Ahmed Khan")
    # Same account, a second parent membership.
    seed_user(db_session, "parent-1", RoleEnum.parent, other_school)
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)
    seed_user(db_session, "admin-2", RoleEnum.school_admin, other_school)

    mine = client.get(DIRECTORY_URL, headers=auth(make_token("admin-1")))
    theirs = client.get(DIRECTORY_URL, headers=auth(make_token("admin-2")))

    assert mine.status_code == 200
    assert theirs.status_code == 200
    assert [entry["user_id"] for entry in mine.json()["parents"]] == [str(profile.id)]
    assert [entry["user_id"] for entry in theirs.json()["parents"]] == [str(profile.id)]


def test_search_filters_by_name_and_by_email(client, db_session, school):
    _seed_parent(db_session, school, "parent-1", "ahmed@example.com", "Ahmed Khan")
    _seed_parent(db_session, school, "parent-2", "sara@example.com", "Sara Khan")
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)

    by_name = client.get(
        f"{DIRECTORY_URL}?search=ahmed",
        headers=auth(make_token("admin-1")),
    )
    by_email = client.get(
        f"{DIRECTORY_URL}?search=SARA@EXAMPLE",
        headers=auth(make_token("admin-1")),
    )
    no_match = client.get(
        f"{DIRECTORY_URL}?search=nobody",
        headers=auth(make_token("admin-1")),
    )

    assert [entry["full_name"] for entry in by_name.json()["parents"]] == ["Ahmed Khan"]
    # The email match is case-insensitive.
    assert [entry["full_name"] for entry in by_email.json()["parents"]] == ["Sara Khan"]
    assert no_match.json()["parents"] == []


def test_a_teacher_cannot_browse_parent_accounts(client, db_session, school):
    _seed_parent(db_session, school, "parent-1", "ahmed@example.com", "Ahmed Khan")
    seed_user(db_session, "teacher-1", RoleEnum.teacher, school)

    response = client.get(DIRECTORY_URL, headers=auth(make_token("teacher-1")))

    assert response.status_code == 403


def test_a_parent_cannot_browse_parent_accounts(client, db_session, school):
    seed_user(db_session, "parent-1", RoleEnum.parent, school)
    seed_user(db_session, "parent-2", RoleEnum.parent, school)

    response = client.get(DIRECTORY_URL, headers=auth(make_token("parent-1")))

    assert response.status_code == 403


def test_the_directory_requires_a_token(client, db_session, school):
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)

    assert client.get(DIRECTORY_URL).status_code == 401


def test_an_admin_of_several_schools_is_asked_to_choose(client, db_session, school, other_school):
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)
    seed_user(db_session, "admin-1", RoleEnum.school_admin, other_school)

    ambiguous = client.get(DIRECTORY_URL, headers=auth(make_token("admin-1")))
    chosen = client.get(
        f"{DIRECTORY_URL}?school_id={school.id}",
        headers=auth(make_token("admin-1")),
    )

    assert ambiguous.status_code == 400
    assert chosen.status_code == 200


def test_the_directory_is_read_only(client, db_session, school):
    """No route may create a parent account through this surface."""
    from backend.main import app

    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)
    headers = auth(make_token("admin-1"))

    assert client.post(DIRECTORY_URL, json={}, headers=headers).status_code == 405
    assert client.delete(DIRECTORY_URL, headers=headers).status_code == 405
    # A supplied school_id in the body is ignored; the query parameter decides.
    assert "post" not in app.openapi()["paths"][DIRECTORY_URL]


def test_the_directory_ignores_a_school_id_in_the_body(client, db_session, school, other_school):
    _seed_parent(db_session, school, "parent-1", "ahmed@example.com", "Ahmed Khan")
    _seed_parent(db_session, other_school, "outsider-1", "outsider@example.com", "Outsider")
    seed_user(db_session, "admin-1", RoleEnum.school_admin, school)

    response = client.get(
        f"{DIRECTORY_URL}?school_id={school.id}",
        headers=auth(make_token("admin-1")),
    )

    assert "outsider@example.com" not in response.text
