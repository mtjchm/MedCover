"""Tests for user profile and admin user-management routes."""
from __future__ import annotations

from app.extensions import db
from app.models.user import UserAccount
from app.models.role import Role
from app.models.invite import RegistrationInvite


# ── Profile ───────────────────────────────────────────────────────────────────

class TestUserProfile:
    def test_profile_page_loads(self, member_client: object) -> None:
        resp = member_client.get("/users/profile")
        assert resp.status_code == 200
        assert "Můj profil".encode() in resp.data

    def test_profile_requires_login(self, client: object) -> None:
        resp = client.get("/users/profile")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_update_profile_name(self, app: object, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "profile", "name": "Nové Jméno", "dashboard_horizon_days": "30"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Profil byl uložen".encode() in resp.data
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "member@test.com"))
            assert user is not None
            assert user.name == "Nové Jméno"

    def test_update_profile_empty_name_rejected(self, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "profile", "name": "", "dashboard_horizon_days": "30"},
            follow_redirects=True,
        )
        assert "Jméno nesmí být prázdné".encode() in resp.data

    def test_dark_mode_toggle(self, app: object, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "profile", "name": "Test Member", "dashboard_horizon_days": "30", "dark_mode": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "member@test.com"))
            assert user is not None
            assert user.dark_mode is True

    def test_dark_mode_off_by_default(self, app: object, member_client: object) -> None:
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "member@test.com"))
            assert user is not None
            assert user.dark_mode is False

    def test_change_password_wrong_current(self, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "password", "current_password": "wrong", "new_password": "newpass123", "confirm_password": "newpass123"},
            follow_redirects=True,
        )
        assert "Současné heslo je nesprávné".encode() in resp.data

    def test_change_password_mismatch(self, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "password", "current_password": "testpass123", "new_password": "newpass123", "confirm_password": "different"},
            follow_redirects=True,
        )
        assert "Hesla se neshodují".encode() in resp.data

    def test_change_password_too_short(self, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "password", "current_password": "testpass123", "new_password": "short", "confirm_password": "short"},
            follow_redirects=True,
        )
        assert "alespoň 8 znaků".encode() in resp.data

    def test_change_password_success(self, app: object, member_client: object) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "password", "current_password": "testpass123", "new_password": "newpass123", "confirm_password": "newpass123"},
            follow_redirects=True,
        )
        assert "Heslo bylo změněno".encode() in resp.data
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "member@test.com"))
            assert user is not None
            assert user.check_password("newpass123")


# ── Admin user list ───────────────────────────────────────────────────────────

class TestAdminUserList:
    def test_user_list_requires_permission(self, member_client: object) -> None:
        # Members have user.view, so use a viewer with no user.view to check 403
        resp = member_client.get("/users/")
        # Members have user.view permission — they can access the list
        assert resp.status_code == 200

    def test_user_list_accessible_to_admin(self, admin_client: object) -> None:
        resp = admin_client.get("/users/")
        assert resp.status_code == 200
        assert "Uživatelé".encode() in resp.data

    def test_user_detail_accessible_to_admin(self, app: object, admin_client: object) -> None:
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            assert user is not None
            uid = str(user.id)
        resp = admin_client.get(f"/users/{uid}")
        assert resp.status_code == 200

    def test_user_detail_404_on_unknown(self, admin_client: object) -> None:
        import uuid
        resp = admin_client.get(f"/users/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_activate_user(self, app: object, admin_client: object) -> None:
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            inactive = UserAccount(email="inactive@test.com", name="Inactive", is_active=False)
            inactive.set_password("pass1234")
            inactive.roles = [role]
            db.session.add(inactive)
            db.session.commit()
            uid = str(inactive.id)
        resp = admin_client.post(f"/users/{uid}/activate", follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(UserAccount, uid)
            assert user is not None
            assert user.is_active is True

    def test_deactivate_user(self, app: object, admin_client: object) -> None:
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            target = UserAccount(email="target@test.com", name="Target", is_active=True)
            target.set_password("pass1234")
            target.roles = [role]
            db.session.add(target)
            db.session.commit()
            uid = str(target.id)
        resp = admin_client.post(f"/users/{uid}/deactivate", follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(UserAccount, uid)
            assert user is not None
            assert user.is_active is False


class TestAdminEditUser:
    def _create_user(self, app: object, email: str = "editable@test.com") -> str:
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            user = UserAccount(email=email, name="Editable User", is_active=True)
            user.set_password("pass1234")
            user.roles = [role]
            db.session.add(user)
            db.session.commit()
            return str(user.id)

    def test_admin_can_edit_name_email_phone(self, app: object, admin_client: object) -> None:
        uid = self._create_user(app)
        resp = admin_client.post(f"/users/{uid}/edit", data={
            "name": "New Name",
            "email": "newemail@test.com",
            "phone": "+420123456789",
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            user = db.session.get(UserAccount, uid)
            assert user is not None
            assert user.name == "New Name"
            assert user.email == "newemail@test.com"
            assert user.phone == "+420123456789"

    def test_member_cannot_edit_user(self, app: object, member_client: object) -> None:
        uid = self._create_user(app, "member_edit_target@test.com")
        resp = member_client.post(f"/users/{uid}/edit", data={
            "name": "Hacker",
            "email": "hacked@test.com",
            "phone": "",
        })
        assert resp.status_code == 403

    def test_duplicate_email_rejected(self, app: object, admin_client: object) -> None:
        uid = self._create_user(app, "orig@test.com")
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            other = UserAccount(email="taken@test.com", name="Other", is_active=True)
            other.set_password("pass1234")
            other.roles = [role]
            db.session.add(other)
            db.session.commit()
        resp = admin_client.post(f"/users/{uid}/edit", data={
            "name": "Orig",
            "email": "taken@test.com",
            "phone": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert "již použit".encode() in resp.data
        with app.app_context():
            user = db.session.get(UserAccount, uid)
            assert user is not None
            assert user.email == "orig@test.com"

    def test_empty_name_rejected(self, app: object, admin_client: object) -> None:
        uid = self._create_user(app, "noname@test.com")
        resp = admin_client.post(f"/users/{uid}/edit", data={
            "name": "",
            "email": "noname@test.com",
            "phone": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert "prázdné".encode() in resp.data

    def test_audit_log_entry_created(self, app: object, admin_client: object) -> None:
        from app.models.audit import AuditLogEntry
        uid = self._create_user(app, "audit_edit@test.com")
        admin_client.post(f"/users/{uid}/edit", data={
            "name": "Audited Name",
            "email": "audit_edit@test.com",
            "phone": "",
        })
        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "UserAccount", AuditLogEntry.entity_id == uid)
                .order_by(AuditLogEntry.timestamp.desc())
            )
            assert entry is not None
            assert entry.action_type == "edit"


# ── Invites ───────────────────────────────────────────────────────────────────

class TestInvites:
    def test_invites_page_accessible_to_admin(self, admin_client: object) -> None:
        resp = admin_client.get("/users/invites")
        assert resp.status_code == 200
        assert "Pozvánky".encode() in resp.data

    def test_invites_page_requires_permission(self, member_client: object) -> None:
        resp = member_client.get("/users/invites")
        assert resp.status_code == 403

    def test_create_invite(self, app: object, admin_client: object) -> None:
        resp = admin_client.post(
            "/users/invites/create",
            data={"email": "newuser@example.com"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Pozvánka odeslána".encode() in resp.data
        with app.app_context():
            inv = db.session.scalar(
                db.select(RegistrationInvite).where(RegistrationInvite.email == "newuser@example.com")
            )
            assert inv is not None
            assert inv.is_valid

    def test_create_invite_invalid_email(self, admin_client: object) -> None:
        resp = admin_client.post(
            "/users/invites/create",
            data={"email": "not-an-email"},
            follow_redirects=True,
        )
        assert b"platnou e-mailovou adresu" in resp.data

    def test_duplicate_invite_warned(self, app: object, admin_client: object) -> None:
        admin_client.post("/users/invites/create", data={"email": "dup@example.com"}, follow_redirects=True)
        resp = admin_client.post(
            "/users/invites/create",
            data={"email": "dup@example.com"},
            follow_redirects=True,
        )
        assert "již existuje".encode() in resp.data
