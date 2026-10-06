"""Day 4 API contract guarantees.

These assert the generated OpenAPI keeps the shape the mobile app codes
against: the four Day 4 read endpoints exist, expose the documented query
parameters, and that Day 4 adds no write surface anywhere.
"""

from backend.main import app

DAY4_ROUTES = {
    "/api/v1/attendance/summary",
    "/api/v1/attendance/today",
    "/api/v1/attendance/history",
    "/api/v1/students/{student_id}/attendance",
}

HISTORY_PARAMS = {"student_id", "start_date", "end_date", "page", "page_size"}
TODAY_PARAMS = {"class_id", "status", "search", "page", "page_size"}

WRITE_VERBS = {"post", "put", "patch", "delete"}


def _paths() -> dict:
    return app.openapi()["paths"]


def test_day4_routes_are_registered():
    paths = _paths()
    assert DAY4_ROUTES <= set(paths), f"missing: {DAY4_ROUTES - set(paths)}"


def test_day4_routes_are_read_only():
    """Attendance is written only by the Day 3 scanner."""
    paths = _paths()
    for path in DAY4_ROUTES:
        assert set(paths[path]) == {"get"}, f"{path} exposes {set(paths[path]) - {'get'}}"


def test_history_exposes_documented_parameters():
    params = {p["name"] for p in _paths()["/api/v1/attendance/history"]["get"]["parameters"]}
    assert HISTORY_PARAMS <= params, f"missing: {HISTORY_PARAMS - params}"


def test_today_exposes_documented_parameters():
    params = {p["name"] for p in _paths()["/api/v1/attendance/today"]["get"]["parameters"]}
    assert TODAY_PARAMS <= params, f"missing: {TODAY_PARAMS - params}"


def test_day4_adds_no_write_endpoint_under_attendance():
    """The Day 3 scan route stays the only writer."""
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


def test_day1_to_day3_routes_remain_available():
    """Day 4 must not remove anything the earlier days shipped."""
    paths = _paths()
    for path in (
        "/api/v1/schools",
        "/api/v1/classes",
        "/api/v1/students",
        "/api/v1/students/{student_id}",
        "/api/v1/students/{student_id}/qr",
        "/api/v1/me",
        "/api/v1/health",
    ):
        assert path in paths, f"Day 4 removed {path}"
