"""Tests for authentication routes: login, logout, forgot-password, register."""
from app.extensions import db as _db
from app.models.role import Role
from app.models.user import UserAccount
from tests.conftest import _make_user, _login


class TestLoginPage:
    def test_login_page_loads(self, client):
        response = client.get("/auth/login")
        assert response.status_code == 200

    def test_login_page_contains_form(self, client):
        response = client.get("/auth/login")
        assert b"email" in response.data.lower()

    def test_login_redirects_to_dashboard(self, app, client):
        with app.app_context():
            _make_user("test@example.com", "Test User", Role.MEMBER)
        response = client.post(
            "/auth/login",
            data={"email": "test@example.com", "password": "testpass123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/dashboard" in response.headers["Location"]

    def test_login_wrong_password_stays_on_login(self, app, client):
        with app.app_context():
            _make_user("test@example.com", "Test User", Role.MEMBER)
        response = client.post(
            "/auth/login",
            data={"email": "test@example.com", "password": "wrongpassword"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == "/auth/login"
        assert "Nesprávný e-mail nebo heslo".encode() in response.data

    def test_login_unknown_email_stays_on_login(self, client):
        response = client.post(
            "/auth/login",
            data={"email": "nobody@example.com", "password": "testpass123"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_login_inactive_user_rejected(self, app, client):
        with app.app_context():
            role = _db.session.scalar(_db.select(Role).where(Role.name == Role.MEMBER))
            user = UserAccount(email="inactive@example.com", name="Inactive", is_active=False)
            user.set_password("testpass123")
            user.roles = [role]
            _db.session.add(user)
            _db.session.commit()
        response = client.post(
            "/auth/login",
            data={"email": "inactive@example.com", "password": "testpass123"},
            follow_redirects=True,
        )
        # Must stay on login page with activation warning
        assert response.request.path == "/auth/login"
        assert b"aktivaci" in response.data


class TestLogout:
    def test_logout_redirects_to_login(self, app, client):
        with app.app_context():
            _make_user("test@example.com", "Test User", Role.MEMBER)
        _login(client, "test@example.com")
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302

    def test_logout_without_login_redirects(self, client):
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302


class TestProtectedRoutes:
    def test_dashboard_requires_login(self, client):
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_events_requires_login(self, client):
        response = client.get("/events/", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_admin_requires_login(self, client):
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]


class TestForgotPassword:
    def test_forgot_password_page_loads(self, client):
        response = client.get("/auth/forgot-password")
        assert response.status_code == 200

    def test_forgot_password_with_unknown_email_does_not_error(self, client):
        """Security: must not reveal whether email exists."""
        response = client.post(
            "/auth/forgot-password",
            data={"email": "nobody@example.com"},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestOpenRedirectProtection:
    """The ?next= parameter on login must not redirect to external URLs."""

    def test_external_next_redirects_to_dashboard(self, app, client):
        with app.app_context():
            _make_user("test@example.com", "Test User", Role.MEMBER)
        response = client.post(
            "/auth/login?next=https://evil.example.com/steal",
            data={"email": "test@example.com", "password": "testpass123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["Location"]
        assert "evil.example.com" not in location
        assert "/dashboard" in location

    def test_protocol_relative_next_redirects_to_dashboard(self, app, client):
        with app.app_context():
            _make_user("test@example.com", "Test User", Role.MEMBER)
        response = client.post(
            "/auth/login?next=//evil.example.com/steal",
            data={"email": "test@example.com", "password": "testpass123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["Location"]
        assert "evil.example.com" not in location

    def test_same_origin_next_is_honoured(self, app, client):
        with app.app_context():
            _make_user("test@example.com", "Test User", Role.MEMBER)
        response = client.post(
            "/auth/login?next=/events/",
            data={"email": "test@example.com", "password": "testpass123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/events/" in response.headers["Location"]
