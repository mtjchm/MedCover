"""Basic smoke tests to verify the app factory and routes are wired up."""


def test_app_creates_successfully(app):
    assert app is not None


def test_login_page_returns_200(client):
    response = client.get("/auth/login")
    assert response.status_code == 200


def test_unknown_route_returns_404(client):
    response = client.get("/nonexistent")
    assert response.status_code == 404


def test_app_is_in_testing_mode(app):
    assert app.config["TESTING"] is True
