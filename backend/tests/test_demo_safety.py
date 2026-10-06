"""Day 7: the demo tooling must not create a production backdoor.

The demonstration script is a local tool, not an endpoint. These tests pin that
distinction so a future change cannot quietly turn it into a public route.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

from tests.conftest import client  # noqa: F401  (fixture-provided, needs a database)

# Any path that would let an unauthenticated caller create data, mint an
# account or bypass authorization.
FORBIDDEN_FRAGMENTS = (
    "seed",
    "demo",
    "create-admin",
    "without-auth",
    "noauth",
    "bootstrap",
    "signup",
    "sign-up",
    "register",
    "magic",
    "backdoor",
    "test-login",
)


def test_no_public_seed_or_demo_endpoint_exists():
    schema = app.openapi()
    offenders = [
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        for method in operations
        if any(fragment in path.lower() for fragment in FORBIDDEN_FRAGMENTS)
    ]
    assert offenders == [], f"unexpected public demo/seed routes: {offenders}"


def test_demo_script_is_not_importable_as_a_router():
    """prepare_demo.py is a script; it must never register HTTP routes."""
    import prepare_demo

    assert not hasattr(prepare_demo, "router")
    assert not hasattr(prepare_demo, "app")


def test_no_unauthenticated_write_endpoint_exists(client):
    """Every state-changing route must require authentication.

    A request with no Authorization header is sent to each mutating path. Any
    2xx answer means data could be created without a token.
    """
    schema = app.openapi()
    # Paths whose first segment is a uuid are per-record routes; a bare path is
    # the collection. Both are probed so a missing dependency cannot hide.
    probes = []
    for path, operations in schema["paths"].items():
        for method in operations:
            if method in ("post", "put", "patch", "delete"):
                probes.append((method, path))

    accepted = []
    for method, path in probes:
        concrete = path
        if "{" in concrete:
            concrete = concrete.split("{")[0] + "00000000-0000-0000-0000-000000000000"
        response = client.request(method, concrete, json={})
        if response.status_code < 400:
            accepted.append(f"{method.upper()} {path} -> {response.status_code}")

    assert accepted == [], f"unauthenticated writes accepted: {accepted}"


def test_health_is_the_only_route_needing_no_token(client):
    """The uptime probe must stay open; nothing else should."""
    ok = []
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            concrete = path
            if "{" in concrete:
                continue
            response = client.request(method, concrete, json={})
            if response.status_code < 400:
                ok.append(f"{method.upper()} {path}")

    assert "/api/v1/health" in ok[0] or ok == ["GET /api/v1/health"], ok


def test_schools_creation_requires_a_token(client):
    response = client.post("/api/v1/schools", json={"name": "Rogue School"})
    assert response.status_code in (401, 403, 422)


def test_scan_requires_a_token(client):
    response = client.post(
        "/api/v1/attendance/scan", json={"credential": "anything"}
    )
    assert response.status_code == 401


def test_attendance_scan_ignores_a_student_id_in_the_body(client):
    """The scanner must never trust a student id from the client."""
    response = client.post(
        "/api/v1/attendance/scan",
        json={"credential": "opaque", "student_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "script_name", ["prepare_demo.py", "check_migration.py"]
)
def test_demo_scripts_live_outside_the_package(script_name):
    """Local tooling sits next to the app, not inside the importable package."""
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[1] / "src" / "backend"
    assert not (package / script_name).exists()


def test_prepare_demo_refuses_a_hosted_database_without_confirmation():
    import prepare_demo

    with pytest.raises(SystemExit) as excinfo:
        prepare_demo.require_demo_database(
            "postgresql://user:pw@db.example.supabase.co:5432/postgres", False
        )
    assert "local development tool" in str(excinfo.value)


def test_prepare_demo_refuses_a_mismatched_database_confirmation():
    import prepare_demo

    with pytest.raises(SystemExit) as excinfo:
        prepare_demo.confirm_database_name(
            "postgresql://user:pw@db.example.supabase.co:5432/schoolpulse",
            "some_other_database",
        )
    assert "does not appear in the DATABASE_URL" in str(excinfo.value)


def test_prepare_demo_allows_local_sqlite():
    import prepare_demo

    # Must not raise.
    prepare_demo.require_demo_database("sqlite:///./demo.db", False)


def test_demo_dataset_is_fictional():
    """No real child's identifying detail is written by the tooling."""
    import prepare_demo

    assert prepare_demo.DEMO_STUDENT_FIRST == "Ali"
    assert prepare_demo.DEMO_STUDENT_LAST == "Khan"
    for email in (
        prepare_demo.DEMO_ADMIN_EMAIL,
        prepare_demo.DEMO_TEACHER_EMAIL,
        prepare_demo.DEMO_PARENT_EMAIL,
    ):
        assert email.endswith("@example.test")
    # No phone numbers or postal addresses anywhere in the demo constants.
    joined = " ".join(
        str(value) for value in vars(prepare_demo).values() if isinstance(value, str)
    )
    assert "+92" not in joined
    assert "Street" not in joined and "Road" not in joined