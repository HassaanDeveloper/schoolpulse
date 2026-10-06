from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "schoolpulse-api",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database_configured": response.json()["database_configured"],
    }
