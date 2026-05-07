"""Tests for the /health endpoint."""


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_json(client):
    response = client.get("/health")
    data = response.get_json()
    assert data is not None
    assert "status" in data


def test_health_accessible_without_login(client):
    """Health endpoint must work without authentication (used by Docker healthcheck)."""
    response = client.get("/health")
    assert response.status_code in (200, 503)


def test_health_db_ok_returns_ok_status(client):
    response = client.get("/health")
    data = response.get_json()
    # In a test environment with a working DB, status should be 'ok'
    assert data["status"] == "ok"
