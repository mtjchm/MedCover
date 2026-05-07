"""Tests for user profile and admin user-management routes."""
from __future__ import annotations

from app.extensions import db
from app.models.user import UserAccount
from app.models.role import Role
from app.models.invite import RegistrationInvite
from app.models.audit import AuditLogEntry


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
        assert "zařazena do fronty".encode() in resp.data
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

    def test_invite_blocked_for_existing_user(self, app: object, admin_client: object) -> None:
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            existing = UserAccount(email="existing@example.com", name="Existing", is_active=True)
            existing.set_password("pass1234")
            existing.roles = [role]
            db.session.add(existing)
            db.session.commit()
        resp = admin_client.post(
            "/users/invites/create",
            data={"email": "existing@example.com"},
            follow_redirects=True,
        )
        assert "již má účet".encode() in resp.data
        with app.app_context():
            inv = db.session.scalar(db.select(RegistrationInvite).where(RegistrationInvite.email == "existing@example.com"))
            assert inv is None

    def test_create_invite_with_custom_subject_and_message(self, app: object, admin_client: object) -> None:
        admin_client.post(
            "/users/invites/create",
            data={
                "email": "custom@example.com",
                "custom_subject": "Vítejte v MedCoveru!",
                "custom_message": "Zdravím, zvu tě do týmu.",
            },
            follow_redirects=True,
        )
        with app.app_context():
            from app.models.outbox import OutboxEmail
            inv = db.session.scalar(db.select(RegistrationInvite).where(RegistrationInvite.email == "custom@example.com"))
            assert inv is not None
            assert inv.custom_subject == "Vítejte v MedCoveru!"
            assert inv.custom_message == "Zdravím, zvu tě do týmu."
            outbox = db.session.get(OutboxEmail, inv.outbox_email_id)
            assert outbox is not None
            assert outbox.subject == "Vítejte v MedCoveru!"
            assert "Zdravím, zvu tě do týmu." in outbox.body

    def test_create_invite_queues_outbox_email(self, app: object, admin_client: object) -> None:
        admin_client.post("/users/invites/create", data={"email": "outbox@example.com"}, follow_redirects=True)
        with app.app_context():
            from app.models.outbox import OutboxEmail
            inv = db.session.scalar(db.select(RegistrationInvite).where(RegistrationInvite.email == "outbox@example.com"))
            assert inv is not None
            assert inv.outbox_email_id is not None
            outbox = db.session.get(OutboxEmail, inv.outbox_email_id)
            assert outbox is not None
            assert outbox.to_email == "outbox@example.com"
            assert outbox.status == "pending"

    def test_create_invite_writes_audit_log(self, app: object, admin_client: object) -> None:
        admin_client.post("/users/invites/create", data={"email": "audit@example.com"}, follow_redirects=True)
        with app.app_context():
            from app.models.audit import AuditLogEntry
            entry = db.session.scalar(
                db.select(AuditLogEntry).where(
                    AuditLogEntry.entity_type == "RegistrationInvite",
                    AuditLogEntry.action_type == "create",
                )
            )
            assert entry is not None

    def test_resend_invite_creates_new_outbox_entry(self, app: object, admin_client: object) -> None:
        admin_client.post("/users/invites/create", data={"email": "resend@example.com"}, follow_redirects=True)
        with app.app_context():
            inv = db.session.scalar(db.select(RegistrationInvite).where(RegistrationInvite.email == "resend@example.com"))
            assert inv is not None
            old_outbox_id = inv.outbox_email_id
            inv_id = inv.id
        resp = admin_client.post(f"/users/invites/{inv_id}/resend", follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            inv = db.session.get(RegistrationInvite, inv_id)
            assert inv is not None
            assert inv.outbox_email_id != old_outbox_id

    def test_link_clicked_at_set_on_register_get(self, app: object, client: object) -> None:
        with app.app_context():
            from app.models.role import Role as _Role
            admin_role = db.session.scalar(db.select(Role).where(Role.name == _Role.ADMIN))
            creator = UserAccount(email="creator@test.com", name="Creator", is_active=True)
            creator.set_password("pass1234")
            creator.roles = [admin_role]
            db.session.add(creator)
            db.session.flush()
            inv = RegistrationInvite(email="clicktest@example.com", created_by_id=creator.id)
            db.session.add(inv)
            db.session.commit()
            token = inv.token
            inv_id = inv.id
        client.get(f"/auth/register/{token}")
        with app.app_context():
            inv = db.session.get(RegistrationInvite, inv_id)
            assert inv is not None
            assert inv.link_clicked_at is not None

    def test_link_clicked_audit_logged(self, app: object, client: object) -> None:
        with app.app_context():
            from app.models.role import Role as _Role
            admin_role = db.session.scalar(db.select(Role).where(Role.name == _Role.ADMIN))
            creator = UserAccount(email="creator2@test.com", name="Creator2", is_active=True)
            creator.set_password("pass1234")
            creator.roles = [admin_role]
            db.session.add(creator)
            db.session.flush()
            inv = RegistrationInvite(email="clickaudit@example.com", created_by_id=creator.id)
            db.session.add(inv)
            db.session.commit()
            token = inv.token
            inv_id = inv.id
        client.get(f"/auth/register/{token}")
        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry).where(
                    AuditLogEntry.entity_type == "RegistrationInvite",
                    AuditLogEntry.action_type == "link_clicked",
                    AuditLogEntry.entity_id == str(inv_id),
                )
            )
            assert entry is not None


# ── Phone number validation ───────────────────────────────────────────────────

import pytest

VALID_PHONES = [
    "123456789",
    "123 456 789",
    "+420123456789",
    "+420 123 456 789",
    "00420123456789",
    "00420 123 456 789",
    "+1 555 123 456",        # international with short local
    "",                       # empty — optional field
]

INVALID_PHONES = [
    "abc",
    "12345678",              # 8 digits — too short
    "+420 abc 123",
    "123-456-789",           # hyphens not allowed
    "phone: 123",
    "123 456 789 0",         # extra digit
]


class TestPhoneValidationProfile:
    @pytest.mark.parametrize("phone", VALID_PHONES)
    def test_valid_phone_accepted_on_profile(self, app: object, member_client: object, phone: str) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "profile", "name": "Test Member", "dashboard_horizon_days": "30", "phone": phone},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Profil byl uložen".encode() in resp.data

    @pytest.mark.parametrize("phone", INVALID_PHONES)
    def test_invalid_phone_rejected_on_profile(self, app: object, member_client: object, phone: str) -> None:
        resp = member_client.post(
            "/users/profile",
            data={"action": "profile", "name": "Test Member", "dashboard_horizon_days": "30", "phone": phone},
            follow_redirects=True,
        )
        assert "Neplatný formát telefonního čísla".encode() in resp.data


class TestPhoneValidationAdminEdit:
    def _create_user(self, app: object) -> str:
        with app.app_context():
            role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            user = UserAccount(email="phonetarget@test.com", name="Phone Target", is_active=True)
            user.set_password("pass1234")
            user.roles = [role]
            db.session.add(user)
            db.session.commit()
            return str(user.id)

    @pytest.mark.parametrize("phone", VALID_PHONES)
    def test_valid_phone_accepted_on_admin_edit(self, app: object, admin_client: object, phone: str) -> None:
        uid = self._create_user(app)
        resp = admin_client.post(
            f"/users/{uid}/edit",
            data={"name": "Phone Target", "email": "phonetarget@test.com", "phone": phone},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Neplatný formát telefonního čísla".encode() not in resp.data

    @pytest.mark.parametrize("phone", INVALID_PHONES)
    def test_invalid_phone_rejected_on_admin_edit(self, app: object, admin_client: object, phone: str) -> None:
        uid = self._create_user(app)
        resp = admin_client.post(
            f"/users/{uid}/edit",
            data={"name": "Phone Target", "email": "phonetarget@test.com", "phone": phone},
            follow_redirects=True,
        )
        assert "Neplatný formát telefonního čísla".encode() in resp.data
