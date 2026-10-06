import re

import pytest

from backend.db.models import StudentQrCredential
from backend.services import qr_credentials
from tests.conftest import (
    auth,
    make_token,
    seed_school,
    seed_student,
    seed_user,
)

from backend.db.models import RoleEnum


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


def generate(client, headers, student_id):
    return client.post(f"/api/v1/students/{student_id}/qr", headers=headers)


# ---------- authorization ----------


def test_unauthenticated_generation_returns_401(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    assert generate(client, {}, student.id).status_code == 401


def test_parent_generation_returns_403(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    response = generate(client, parent_headers(db_session, school_a), student.id)
    assert response.status_code == 403


def test_teacher_generation_returns_403(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    response = generate(client, teacher_headers(db_session, school_a), student.id)
    assert response.status_code == 403


def test_admin_generation_succeeds(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    response = generate(client, admin_headers(db_session, school_a), student.id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["student_id"] == str(student.id)
    assert body["credential"]
    assert body["revoked_previous"] is False


def test_cross_school_generation_returns_404(client, db_session, school_a, school_b):
    """School B's admin cannot mint a credential for School A's student."""
    student = seed_student(db_session, school_a)
    response = generate(client, admin_headers(db_session, school_b, "admin-b"), student.id)
    assert response.status_code == 404


def test_generation_for_unknown_student_returns_404(client, db_session, school_a):
    response = generate(
        client, admin_headers(db_session, school_a), "00000000-0000-4000-8000-000000000000"
    )
    assert response.status_code == 404


# ---------- token properties ----------


def test_credential_is_opaque_and_random(client, db_session, school_a):
    """Two credentials must differ and contain no student/school information."""
    headers = admin_headers(db_session, school_a)
    first_student = seed_student(db_session, school_a, admission_number="ADM-1")
    second_student = seed_student(
        db_session, school_a, admission_number="ADM-2", first_name="Bilal"
    )

    first = generate(client, headers, first_student.id).json()["credential"]
    second = generate(client, headers, second_student.id).json()["credential"]

    assert first != second
    for token in (first, second):
        # URL-safe base64 of 32 random bytes => 43 characters.
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token), token


def test_credential_contains_no_student_pii(client, db_session, school_a):
    student = seed_student(
        db_session, school_a, admission_number="ADM-SECRET", first_name="Ayesha", last_name="Khan"
    )
    token = generate(client, admin_headers(db_session, school_a), student.id).json()["credential"]

    haystack = token.lower()
    for secret in (
        student.admission_number.lower(),
        "admission",
        student.first_name.lower(),
        student.last_name.lower(),
        "ayesha",
        "khan",
        str(student.id),
        school_a.name.lower(),
        school_a.slug,
    ):
        assert secret not in haystack, f"{secret!r} leaked into the QR credential"


def test_raw_token_is_not_stored_in_database(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    token = generate(client, admin_headers(db_session, school_a), student.id).json()["credential"]

    rows = db_session.query(StudentQrCredential).all()
    assert len(rows) == 1

    row = rows[0]
    # The plaintext must not appear anywhere in the row's stored values.
    assert token != row.token_hash
    assert token not in row.token_hash
    assert row.token_hash == qr_credentials.hash_credential(token)
    assert len(row.token_hash) == 64  # SHA-256 hex digest

    stored = " ".join(
        str(value) for value in vars(row).values() if isinstance(value, (str, int))
    )
    assert token not in stored


def test_hash_credential_is_stable_and_distinct(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    token = generate(client, admin_headers(db_session, school_a), student.id).json()["credential"]

    digest = qr_credentials.hash_credential(token)
    assert digest == qr_credentials.hash_credential(token)
    assert digest != qr_credentials.hash_credential(token + "x")
    assert digest != qr_credentials.hash_credential(token.upper())


def test_token_generator_uses_secure_entropy():
    tokens = {qr_credentials.generate_credential() for _ in range(200)}
    assert len(tokens) == 200, "credential generator produced a collision"
    assert all(len(t) == 43 for t in tokens)


# ---------- regeneration ----------


def test_regeneration_revokes_previous_credential(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)

    first_token = generate(client, headers, student.id).json()["credential"]

    second = generate(client, headers, student.id).json()
    assert second["revoked_previous"] is True
    assert second["credential"] != first_token

    rows = (
        db_session.query(StudentQrCredential)
        .filter(StudentQrCredential.student_id == student.id)
        .all()
    )
    assert len(rows) == 2, "historical credential should be retained"
    revoked = [r for r in rows if r.revoked_at is not None]
    active = [r for r in rows if r.revoked_at is None]
    assert len(revoked) == 1 and len(active) == 1


def test_regenerated_credential_invalidates_the_old_one(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)

    first_token = generate(client, headers, student.id).json()["credential"]
    generate(client, headers, student.id)

    scan = client.post(
        "/api/v1/attendance/scan",
        json={"credential": first_token},
        headers=teacher_headers(db_session, school_a),
    )
    assert scan.status_code == 404
    assert scan.json()["detail"] == "Invalid or inactive QR credential."


def test_only_one_active_credential_at_a_time(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)

    for _ in range(5):
        generate(client, headers, student.id)

    active = (
        db_session.query(StudentQrCredential)
        .filter(
            StudentQrCredential.student_id == student.id,
            StudentQrCredential.revoked_at.is_(None),
        )
        .all()
    )
    assert len(active) == 1


# ---------- status + explicit revocation ----------


def test_credential_status_reflects_state(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)

    before = client.get(f"/api/v1/students/{student.id}/qr", headers=headers)
    assert before.status_code == 200
    assert before.json()["has_active_credential"] is False
    # Day 6: no dates at all means the student never had a code.
    assert before.json()["created_at"] is None
    assert before.json()["last_revoked_at"] is None

    generate(client, headers, student.id)

    after = client.get(f"/api/v1/students/{student.id}/qr", headers=headers)
    assert after.json()["has_active_credential"] is True
    assert after.json()["created_at"] is not None
    assert after.json()["last_revoked_at"] is None


def test_revoked_credential_is_distinguishable_from_never_issued(
    client, db_session, school_a
):
    """The admin app shows Active / Revoked / Not generated, so the API has to
    be able to tell the last two apart."""
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)
    generate(client, headers, student.id)

    client.delete(f"/api/v1/students/{student.id}/qr", headers=headers)

    response = client.get(f"/api/v1/students/{student.id}/qr", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["has_active_credential"] is False
    # No active code, but one was issued and then revoked.
    assert body["created_at"] is None
    assert body["last_revoked_at"] is not None


def test_regenerating_clears_the_revoked_marker(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)
    generate(client, headers, student.id)
    client.delete(f"/api/v1/students/{student.id}/qr", headers=headers)

    generate(client, headers, student.id)

    body = client.get(f"/api/v1/students/{student.id}/qr", headers=headers).json()
    assert body["has_active_credential"] is True
    assert body["created_at"] is not None


def test_credential_status_still_never_exposes_the_token_hash(
    client, db_session, school_a
):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)
    generate(client, headers, student.id)

    stored = (
        db_session.query(StudentQrCredential)
        .filter(StudentQrCredential.student_id == student.id)
        .one()
    )
    body = client.get(f"/api/v1/students/{student.id}/qr", headers=headers).text

    assert "token_hash" not in body
    # The plaintext is disclosed once, at generation, and never again.
    assert '"credential":' not in body
    assert stored.token_hash not in body


def test_admin_can_revoke_credential(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)
    generate(client, headers, student.id)

    response = client.delete(f"/api/v1/students/{student.id}/qr", headers=headers)
    assert response.status_code == 204

    row = (
        db_session.query(StudentQrCredential)
        .filter(StudentQrCredential.student_id == student.id)
        .one()
    )
    assert row.revoked_at is not None


def test_revoking_without_active_credential_returns_404(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    response = client.delete(
        f"/api/v1/students/{student.id}/qr", headers=admin_headers(db_session, school_a)
    )
    assert response.status_code == 404


def test_revoke_requires_school_admin(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    generate(client, admin_headers(db_session, school_a), student.id)

    assert (
        client.delete(
            f"/api/v1/students/{student.id}/qr", headers=teacher_headers(db_session, school_a)
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/students/{student.id}/qr", headers=parent_headers(db_session, school_a)
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/students/{student.id}/qr", headers={}).status_code == 401


def test_revoked_credential_is_rejected_by_scanner(client, db_session, school_a):
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)
    token = generate(client, headers, student.id).json()["credential"]

    client.delete(f"/api/v1/students/{student.id}/qr", headers=headers)

    scan = client.post(
        "/api/v1/attendance/scan",
        json={"credential": token},
        headers=teacher_headers(db_session, school_a),
    )
    assert scan.status_code == 404
    assert scan.json()["detail"] == "Invalid or inactive QR credential."


def test_revocation_keeps_historical_row(client, db_session, school_a):
    """Revoking must not delete the audit trail."""
    student = seed_student(db_session, school_a)
    headers = admin_headers(db_session, school_a)
    generate(client, headers, student.id)
    client.delete(f"/api/v1/students/{student.id}/qr", headers=headers)

    rows = (
        db_session.query(StudentQrCredential)
        .filter(StudentQrCredential.student_id == student.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].revoked_at is not None


# ---------- cross-school credential usage ----------


def test_school_b_credential_cannot_be_generated_for_school_a_student(
    client, db_session, school_a, school_b
):
    student_a = seed_student(db_session, school_a, admission_number="ADM-A")
    response = generate(client, admin_headers(db_session, school_b, "admin-b"), student_a.id)
    assert response.status_code == 404
    assert (
        db_session.query(StudentQrCredential).count() == 0
    ), "no credential should have been created"


def test_credential_is_scoped_to_student_school(client, db_session, school_a, school_b):
    student = seed_student(db_session, school_b, admission_number="ADM-B")
    token = generate(client, admin_headers(db_session, school_b, "admin-b"), student.id).json()[
        "credential"
    ]

    row = (
        db_session.query(StudentQrCredential)
        .filter(StudentQrCredential.student_id == student.id)
        .one()
    )
    assert row.school_id == school_b.id

    # A School A scanner must not be able to use a School B credential.
    scan = client.post(
        "/api/v1/attendance/scan",
        json={"credential": token},
        headers=teacher_headers(db_session, school_a),
    )
    assert scan.status_code == 403
    assert scan.json()["detail"] == "This QR credential cannot be used at your school."