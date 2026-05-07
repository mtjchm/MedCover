"""Tests for event model unit tests (no HTTP, pure model logic)."""
from app.models.event import EventStatus


class TestEventStatusValues:
    def test_draft_value(self):
        assert EventStatus.DRAFT.value == "Koncept"

    def test_published_value(self):
        assert EventStatus.PUBLISHED.value == "Zveřejněná"

    def test_assignments_open_value(self):
        assert EventStatus.ASSIGNMENTS_OPEN.value == "Přihlášky otevřeny"

    def test_assignments_closed_value(self):
        assert EventStatus.ASSIGNMENTS_CLOSED.value == "Přihlášky uzavřeny"

    def test_completed_value(self):
        assert EventStatus.COMPLETED.value == "Dokončena"

    def test_cancelled_value(self):
        assert EventStatus.CANCELLED.value == "Zrušena"


class TestUserPermissions:
    def test_has_permission_returns_true_for_admin(self, app):
        from app.extensions import db
        from app.models.role import Role
        from app.models.user import UserAccount
        from tests.conftest import _make_user

        with app.app_context():
            _make_user("admin@test.com", "Admin", Role.ADMIN)
            # Reload user in same context to test permissions
            loaded = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            assert loaded.has_permission("event.create") is True

    def test_has_permission_returns_false_for_viewer(self, app):
        from app.extensions import db
        from app.models.role import Role
        from app.models.user import UserAccount
        from tests.conftest import _make_user

        with app.app_context():
            _make_user("viewer@test.com", "Viewer", Role.VIEWER)
            loaded = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "viewer@test.com"))
            assert loaded.has_permission("event.create") is False

    def test_has_any_permission(self, app):
        from app.extensions import db
        from app.models.role import Role
        from app.models.user import UserAccount
        from tests.conftest import _make_user

        with app.app_context():
            _make_user("admin@test.com", "Admin", Role.ADMIN)
            loaded = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            assert loaded.has_any_permission("event.create", "nonexistent.perm") is True

    def test_has_any_permission_all_missing(self, app):
        from app.extensions import db
        from app.models.role import Role
        from app.models.user import UserAccount
        from tests.conftest import _make_user

        with app.app_context():
            _make_user("viewer@test.com", "Viewer", Role.VIEWER)
            loaded = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "viewer@test.com"))
            assert loaded.has_any_permission("event.create", "event.edit") is False
