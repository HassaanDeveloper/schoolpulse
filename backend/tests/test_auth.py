from tests.conftest import auth, make_token

PROTECTED = [
    ("get", "/api/v1/me"),
    ("post", "/api/v1/schools"),
    ("post", "/api/v1/classes"),
    ("get", "/api/v1/classes"),
    ("get", "/api/v1/students"),
    ("post", "/api/v1/students"),
]


def test_missing_token_returns_401(client):
    for method, path in PROTECTED:
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_invalid_token_returns_401(client):
    for method, path in PROTECTED:
        response = client.request(method, path, headers=auth("not-a-real-jwt"))
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_malformed_bearer_header_returns_401(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer"})
    assert response.status_code == 401


def test_token_signed_with_wrong_secret_returns_401(client):
    from jose import jwt

    forged = jwt.encode(
        {"sub": "attacker", "aud": "authenticated", "exp": 9999999999},
        "wrong-secret",
        algorithm="HS256",
    )
    response = client.get("/api/v1/me", headers=auth(forged))
    assert response.status_code == 401


def test_expired_token_returns_401(client):
    from jose import jwt

    expired = jwt.encode(
        {"sub": "user-1", "aud": "authenticated", "exp": 1},
        "test-secret-for-signing-tokens",
        algorithm="HS256",
    )
    response = client.get("/api/v1/me", headers=auth(expired))
    assert response.status_code == 401


def test_valid_token_reaches_protected_endpoint(client):
    token = make_token("user-1", "admin@school.pk")
    response = client.get("/api/v1/me", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-1"


def test_health_endpoint_requires_no_auth(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "schoolpulse-api"}