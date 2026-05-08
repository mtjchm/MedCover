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
    """Health endpoint must return 200 without authentication (Docker healthcheck)."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_has_no_detail_key_when_ok(client):
    """A healthy response should not include an error detail field."""
    response = client.get("/health")
    data = response.get_json()
    assert "detail" not in data


def test_health_db_ok_returns_ok_status(client):
    response = client.get("/health")
    data = response.get_json()
    # In a test environment with a working DB, status should be 'ok'
    assert data["status"] == "ok"
