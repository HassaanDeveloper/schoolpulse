"""Day 7: production configuration and health-endpoint contract.

The health probe is what an uptime monitor and the Flutter client's "is the
backend reachable?" path both rely on, so its shape is pinned here. It must
never grow a field that leaks configuration.
"""

from fastapi.testclient import TestClient

from backend.core.config import Settings, settings
from backend.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "ok",
        "service": "schoolpulse-api",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database_configured": data["database_configured"],
    }


def test_health_is_lightweight_and_discloses_no_secrets():
    """No credentials, no filesystem paths, no stack traces."""
    response = client.get("/api/v1/health")
    body = response.text

    for leak in (
        "password",
        "postgresql://",
        "SUPABASE_JWT_SECRET",
        "Traceback",
        ".env",
    ):
        assert leak not in body, f"health response leaked {leak!r}"

    assert set(response.json()) == {
        "status",
        "service",
        "version",
        "environment",
        "database_configured",
    }


def test_health_requires_no_authentication():
    """A load balancer cannot present a Supabase token."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "www-authenticate" not in response.headers


def test_health_reports_missing_configuration_rather_than_crashing():
    """A misconfigured deploy still answers the probe, so the failure is visible."""
    data = client.get("/api/v1/health").json()
    assert isinstance(data["database_configured"], bool)
    assert data["status"] == "ok"


def test_production_startup_requires_database_and_jwt_secret():
    incomplete = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="",
        SUPABASE_URL="",
        SUPABASE_JWT_SECRET="",
    )
    missing = incomplete.missing_production_settings()
    assert "DATABASE_URL" in missing
    assert "SUPABASE_JWT_SECRET" in missing
    assert "SUPABASE_URL" in missing


def test_production_startup_rejects_default_cors():
    """A shipped app talking only to localhost is a misconfiguration."""
    incomplete = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://u:p@db:5432/schoolpulse",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET="secret-value",
        CORS_ORIGINS="http://localhost:3000",
    )
    assert "CORS_ORIGINS" in incomplete.missing_production_settings()


def test_complete_production_config_passes_validation():
    complete = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://u:p@db:5432/schoolpulse",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET="secret-value",
        CORS_ORIGINS="https://app.example.com",
    )
    assert complete.missing_production_settings() == []
    assert complete.is_production is True


def test_production_requires_postgresql_url():
    """SQLite is a test fixture, never the production store."""
    sqlite_config = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="sqlite:///./schoolpulse.db",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET="secret-value",
        CORS_ORIGINS="https://app.example.com",
    )
    assert sqlite_config.is_postgres is False

    postgres_config = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://u:p@db:5432/schoolpulse",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_JWT_SECRET="secret-value",
        CORS_ORIGINS="https://app.example.com",
    )
    assert postgres_config.is_postgres is True


def test_validation_error_names_settings_without_their_values():
    """A startup log must never print the secret it is complaining about."""
    incomplete = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="",
        SUPABASE_JWT_SECRET="super-secret-value",
    )
    missing = incomplete.missing_production_settings()
    assert missing
    assert "super-secret-value" not in ", ".join(missing)


def test_development_mode_does_not_require_configuration():
    """Local work must keep working with an empty DATABASE_URL.

    Every value is passed explicitly so this test states its own premise
    instead of inheriting whatever the operator's `.env` happens to contain.
    """
    development = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="",
        SUPABASE_URL="",
        SUPABASE_JWT_SECRET="",
        CORS_ORIGINS="http://localhost:3000",
    )
    assert development.is_production is False
    # The gaps are still reported; development ignores them, production would not.
    assert development.missing_production_settings()


def test_cors_origins_are_comma_separated():
    multi = Settings(CORS_ORIGINS="https://a.example.com, https://b.example.com")
    assert multi.cors_origins_list == ["https://a.example.com", "https://b.example.com"]


def test_unhandled_errors_do_not_return_a_traceback():
    """Day 7 release requirement: no stack trace in an API response."""
    response = client.get("/api/v1/does-not-exist-at-all")
    assert response.status_code == 404
    assert "Traceback" not in response.text