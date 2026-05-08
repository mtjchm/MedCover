"""Tests for Master Event CRUD: list, create, detail, edit, archive."""
from __future__ import annotations

from app.extensions import db
from app.models.master_event import MasterEvent
from app.models.audit import AuditLogEntry


def _make_me(name: str = "Test ME", **kwargs) -> MasterEvent:
    """Create and persist a MasterEvent in the current context."""
    me = MasterEvent(name=name, **kwargs)
    db.session.add(me)
    db.session.commit()
    return me


# ── List ──────────────────────────────────────────────────────────────────────


class TestMasterEventList:
    def test_list_requires_login(self, client):
        response = client.get("/master-events/", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_member_can_view_list(self, member_client):
        response = member_client.get("/master-events/")
        assert response.status_code == 200

    def test_admin_can_view_list(self, admin_client):
        response = admin_client.get("/master-events/")
        assert response.status_code == 200

    def test_list_shows_active_master_events(self, app, admin_client):
        with app.app_context():
            _make_me("Viditelná ME")
        response = admin_client.get("/master-events/")
        assert "Viditelná ME".encode() in response.data

    def test_list_hides_archived_by_default(self, app, admin_client):
        with app.app_context():
            _make_me("Archivovaná ME", archived=True)
        response = admin_client.get("/master-events/")
        assert "Archivovaná ME".encode() not in response.data

    def test_list_shows_archived_when_requested(self, app, admin_client):
        with app.app_context():
            _make_me("Archivovaná ME", archived=True)
        response = admin_client.get("/master-events/?archived=1")
        assert "Archivovaná ME".encode() in response.data


# ── Create ────────────────────────────────────────────────────────────────────


class TestMasterEventCreate:
    def test_create_page_loads_for_admin(self, admin_client):
        response = admin_client.get("/master-events/create")
        assert response.status_code == 200

    def test_create_page_forbidden_for_member(self, member_client):
        response = member_client.get("/master-events/create")
        assert response.status_code == 403

    def test_admin_can_create_master_event(self, app, admin_client):
        response = admin_client.post(
            "/master-events/create",
            data={"name": "Nová ME", "description": "Popis"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            me = db.session.scalar(db.select(MasterEvent).where(MasterEvent.name == "Nová ME"))
            assert me is not None
            assert me.description == "Popis"

    def test_create_missing_name_rejected(self, app, admin_client):
        response = admin_client.post(
            "/master-events/create",
            data={"name": ""},
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            # Only the general ME may exist (seeded); no new one
            count = db.session.scalar(
                db.select(db.func.count()).select_from(MasterEvent).where(MasterEvent.is_general == False)  # noqa: E712
            )
            assert count == 0

    def test_create_duplicate_name_rejected(self, app, admin_client):
        with app.app_context():
            _make_me("Duplicitní ME")
        response = admin_client.post(
            "/master-events/create",
            data={"name": "Duplicitní ME"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(MasterEvent).where(MasterEvent.name == "Duplicitní ME")
            )
            assert count == 1  # No second one created

    def test_create_writes_audit_log(self, app, admin_client):
        admin_client.post(
            "/master-events/create",
            data={"name": "ME s auditom"},
            follow_redirects=True,
        )
        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "MasterEvent")
                .where(AuditLogEntry.action_type == "create")
            )
            assert entry is not None
            assert "ME s auditom" in entry.summary


# ── Detail ────────────────────────────────────────────────────────────────────


class TestMasterEventDetail:
    def test_detail_requires_login(self, app, client):
        with app.app_context():
            me = _make_me("Detail ME")
            me_id = me.id
        response = client.get(f"/master-events/{me_id}", follow_redirects=False)
        assert response.status_code == 302

    def test_member_can_view_detail(self, app, member_client):
        with app.app_context():
            me = _make_me("Detail ME")
            me_id = me.id
        response = member_client.get(f"/master-events/{me_id}")
        assert response.status_code == 200

    def test_detail_shows_name(self, app, admin_client):
        with app.app_context():
            me = _make_me("Zobrazená ME")
            me_id = me.id
        response = admin_client.get(f"/master-events/{me_id}")
        assert "Zobrazená ME".encode() in response.data

    def test_detail_404_for_missing(self, admin_client):
        response = admin_client.get("/master-events/999999")
        assert response.status_code == 404


# ── Edit ──────────────────────────────────────────────────────────────────────


class TestMasterEventEdit:
    def test_edit_page_loads_for_admin(self, app, admin_client):
        with app.app_context():
            me = _make_me("Editovatelná ME")
            me_id = me.id
        response = admin_client.get(f"/master-events/{me_id}/edit")
        assert response.status_code == 200

    def test_edit_page_forbidden_for_member(self, app, member_client):
        with app.app_context():
            me = _make_me("Editovatelná ME")
            me_id = me.id
        response = member_client.get(f"/master-events/{me_id}/edit")
        assert response.status_code == 403

    def test_admin_can_edit_master_event(self, app, admin_client):
        with app.app_context():
            me = _make_me("Původní název")
            me_id = me.id
            version = me.version

        response = admin_client.post(
            f"/master-events/{me_id}/edit",
            data={"name": "Nový název", "version": str(version)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            updated = db.session.get(MasterEvent, me_id)
            assert updated.name == "Nový název"

    def test_edit_missing_name_rejected(self, app, admin_client):
        with app.app_context():
            me = _make_me("Původní název")
            me_id = me.id
            version = me.version

        admin_client.post(
            f"/master-events/{me_id}/edit",
            data={"name": "", "version": str(version)},
            follow_redirects=True,
        )
        with app.app_context():
            unchanged = db.session.get(MasterEvent, me_id)
            assert unchanged.name == "Původní název"

    def test_edit_stale_version_rejected(self, app, admin_client):
        with app.app_context():
            me = _make_me("Původní název")
            me_id = me.id

        response = admin_client.post(
            f"/master-events/{me_id}/edit",
            data={"name": "Nový název", "version": "999"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "mezitím změněn".encode() in response.data
        with app.app_context():
            unchanged = db.session.get(MasterEvent, me_id)
            assert unchanged.name == "Původní název"

    def test_edit_writes_audit_log(self, app, admin_client):
        with app.app_context():
            me = _make_me("Původní název")
            me_id = me.id
            version = me.version

        admin_client.post(
            f"/master-events/{me_id}/edit",
            data={"name": "Přejmenovaná ME", "version": str(version)},
            follow_redirects=True,
        )
        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "MasterEvent")
                .where(AuditLogEntry.action_type == "edit")
                .where(AuditLogEntry.entity_id == str(me_id))
            )
            assert entry is not None

    def test_edit_404_for_missing(self, admin_client):
        response = admin_client.get("/master-events/999999/edit")
        assert response.status_code == 404


# ── Archive / Unarchive ───────────────────────────────────────────────────────


class TestMasterEventArchive:
    def test_admin_can_archive(self, app, admin_client):
        with app.app_context():
            me = _make_me("Archivovatelná ME")
            me_id = me.id

        response = admin_client.post(f"/master-events/{me_id}/archive", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            updated = db.session.get(MasterEvent, me_id)
            assert updated.archived is True

    def test_member_cannot_archive(self, app, member_client):
        with app.app_context():
            me = _make_me("Archivovatelná ME")
            me_id = me.id
        response = member_client.post(f"/master-events/{me_id}/archive")
        assert response.status_code == 403

    def test_cannot_archive_general_master_event(self, app, admin_client):
        with app.app_context():
            me = _make_me("Výchozí ME", is_general=True)
            me_id = me.id

        response = admin_client.post(f"/master-events/{me_id}/archive", follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            unchanged = db.session.get(MasterEvent, me_id)
            assert unchanged.archived is False

    def test_admin_can_unarchive(self, app, admin_client):
        with app.app_context():
            me = _make_me("Archivovaná ME", archived=True)
            me_id = me.id

        response = admin_client.post(f"/master-events/{me_id}/unarchive", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            updated = db.session.get(MasterEvent, me_id)
            assert updated.archived is False

    def test_member_cannot_unarchive(self, app, member_client):
        with app.app_context():
            me = _make_me("Archivovaná ME", archived=True)
            me_id = me.id
        response = member_client.post(f"/master-events/{me_id}/unarchive")
        assert response.status_code == 403

    def test_archive_writes_audit_log(self, app, admin_client):
        with app.app_context():
            me = _make_me("Archivovatelná ME")
            me_id = me.id

        admin_client.post(f"/master-events/{me_id}/archive", follow_redirects=True)
        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "MasterEvent")
                .where(AuditLogEntry.action_type == "archive")
                .where(AuditLogEntry.entity_id == str(me_id))
            )
            assert entry is not None
