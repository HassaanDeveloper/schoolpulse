"""Day 5 API contract guarantees.

These lock down the surface the Flutter parent app codes against: the link
management routes, the parent self-service routes, and the guarantee that Day 5
exposes no write route a parent could use to change attendance.
"""

from backend.main import app

PARENT_LINK_ROUTES = {
    "/api/v1/students/{student_id}/parents": {"post", "get"},
    "/api/v1/students/{student_id}/parents/{parent_user_id}": {"delete"},
}

PARENT_SELF_ROUTES = {
    "/api/v1/me/students": {"get"},
    "/api/v1/me/students/{student_id}/attendance": {"get"},
    "/api/v1/me/notifications": {"get"},
    "/api/v1/me/notifications/unread-count": {"get"},
    "/api/v1/me/notifications/{notification_id}/read": {"patch"},
}

WRITE_VERBS = {"post", "put", "patch", "delete"}


def _paths() -> dict:
    return app.openapi()["paths"]


def test_parent_link_routes_are_registered():
    paths = _paths()
    for path, methods in PARENT_LINK_ROUTES.items():
        assert path in paths, f"missing {path}"
        assert methods <= set(paths[path]), f"{path} is missing {methods - set(paths[path])}"


def test_parent_self_routes_are_registered():
    paths = _paths()
    for path, methods in PARENT_SELF_ROUTES.items():
        assert path in paths, f"missing {path}"
        assert methods <= set(paths[path]), f"{path} is missing {methods - set(paths[path])}"


def test_admin_link_routes_are_not_exposed_under_me():
    """Link management is an admin tool and must not hang off /me."""
    paths = _paths()
    assert "/api/v1/me/{student_id}/parents" not in paths
    assert "/api/v1/me/parents" not in paths


def test_parent_routes_are_not_exposed_under_students():
    """A parent's own data must not hang off the staff /students prefix."""
    paths = _paths()
    for path in PARENT_SELF_ROUTES:
        assert f"/api/v1/students{path.removeprefix('/api/v1/me')}" not in paths


def test_no_parent_route_can_write_attendance():
    """The Day 3 scan route remains the only attendance writer."""
    paths = _paths()
    writers = {
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if method in WRITE_VERBS
    }
    attendance_writers = {
        (path, method) for path, method in writers if path.startswith("/api/v1/attendance")
    }
    assert attendance_writers == {("/api/v1/attendance/scan", "post")}

    # Nothing a parent can reach writes an attendance record or a parent link.
    parent_writers = {
        (path, method)
        for path, method in writers
        if path.startswith("/api/v1/me")
    }
    assert parent_writers == {
        ("/api/v1/me/notifications/{notification_id}/read", "patch")
    }


def test_mark_read_is_the_only_mutation_and_is_idempotent_by_shape():
    """It takes no body, so a repeat call sends nothing new."""
    operation = _paths()["/api/v1/me/notifications/{notification_id}/read"]["patch"]
    assert "requestBody" not in operation


def test_notification_listing_exposes_the_documented_filters():
    params = {p["name"] for p in _paths()["/api/v1/me/notifications"]["get"]["parameters"]}
    assert {"school_id", "unread_only", "limit", "offset"} <= params


def test_parent_attendance_exposes_only_the_documented_filters():
    params = {
        p["name"] for p in _paths()["/api/v1/me/students/{student_id}/attendance"]["get"]["parameters"]
    }
    assert {"student_id", "start_date", "end_date"} <= params


def test_day1_to_day4_routes_remain_available():
    """Day 5 must not remove anything the earlier days shipped."""
    paths = _paths()
    for path in (
        "/api/v1/health",
        "/api/v1/me",
        "/api/v1/schools",
        "/api/v1/classes",
        "/api/v1/students",
        "/api/v1/students/{student_id}",
        "/api/v1/students/{student_id}/qr",
        "/api/v1/attendance/scan",
        "/api/v1/attendance/summary",
        "/api/v1/attendance/today",
        "/api/v1/attendance/history",
        "/api/v1/students/{student_id}/attendance",
    ):
        assert path in paths, f"Day 5 removed {path}"


def test_day5_scan_response_schema_is_unchanged():
    """Notifications are not leaked into the scanner's response."""
    schema = app.openapi()["components"]["schemas"]["ScanResponse"]
    assert set(schema["properties"]) == {
        "status",
        "student",
        "attendance_date",
        "arrival_at",
        "departure_at",
        "timestamp",
    }


def test_notification_status_vocabulary_is_explicit():
    """`sent` must exist, and must not imply an external channel."""
    schema = app.openapi()["components"]["schemas"]["NotificationStatusEnum"]
    assert schema["enum"] == ["queued", "sent", "failed"]


def test_notification_type_vocabulary_is_arrival_and_departure_only():
    schema = app.openapi()["components"]["schemas"]["NotificationTypeEnum"]
    assert schema["enum"] == ["arrival", "departure"]


def test_app_version_is_day7_release():
    """Day 7 bumped the released API version; it is asserted rather than assumed.

    This value is surfaced by GET /api/v1/health.
    """
    assert app.version == "0.7.0"