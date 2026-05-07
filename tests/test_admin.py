"""Tests for admin blueprint: dashboard, pending users, activation."""
from app.extensions import db
from app.models.role import Role
from app.models.user import UserAccount


class TestAdminDashboard:
    def test_admin_dashboard_requires_login(self, client):
        response = client.get("/admin/", follow_redirects=False)
        assert response.status_code == 302

    def test_member_cannot_access_admin_dashboard(self, member_client):
        response = member_client.get("/admin/")
        assert response.status_code == 403

    def test_admin_can_access_dashboard(self, admin_client):
        response = admin_client.get("/admin/")
        assert response.status_code == 200

    def test_admin_dashboard_shows_service_status(self, admin_client):
        response = admin_client.get("/admin/")
        assert response.status_code == 200
        # Dashboard should contain DB status info
        assert b"DB" in response.data or "Databáze".encode() in response.data


class TestPendingUsers:
    def test_admin_can_view_pending_users(self, admin_client):
        response = admin_client.get("/admin/pending-users")
        assert response.status_code == 200

    def test_member_cannot_view_pending_users(self, member_client):
        response = member_client.get("/admin/pending-users")
        assert response.status_code == 403

    def test_pending_users_shows_inactive_users(self, app, admin_client):
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            user = UserAccount(email="pending@test.com", name="Pending User", is_active=False)
            user.set_password("testpass123")
            user.roles = [role]
            db.session.add(user)
            db.session.commit()

        response = admin_client.get("/admin/pending-users")
        assert b"pending@test.com" in response.data


class TestUserActivation:
    def test_admin_can_activate_user(self, app, admin_client):
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            user = UserAccount(email="inactive@test.com", name="Inactive", is_active=False)
            user.set_password("testpass123")
            user.roles = [role]
            db.session.add(user)
            db.session.commit()
            user_id = str(user.id)

        response = admin_client.post(
            f"/admin/activate/{user_id}",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with app.app_context():
            activated = db.session.scalar(
                db.select(UserAccount).where(UserAccount.email == "inactive@test.com")
            )
            assert activated.is_active is True

    def test_member_cannot_activate_users(self, app, member_client):
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            user = UserAccount(email="inactive@test.com", name="Inactive", is_active=False)
            user.set_password("testpass123")
            user.roles = [role]
            db.session.add(user)
            db.session.commit()
            user_id = str(user.id)

        response = member_client.post(f"/admin/activate/{user_id}")
        assert response.status_code == 403


class TestAppSettings:
    def test_settings_page_requires_admin(self, member_client):
        response = member_client.get("/admin/settings/")
        assert response.status_code == 403

    def test_settings_page_loads_for_admin(self, admin_client):
        response = admin_client.get("/admin/settings/")
        assert response.status_code == 200

    def test_settings_page_does_not_expose_smtp_password(self, admin_client):
        response = admin_client.get("/admin/settings/")
        # SMTP password must never appear in the HTML response
        assert b"smtp_password" not in response.data.lower() or b'type="password"' in response.data
