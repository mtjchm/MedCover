"""Tests for the notification catalog and toggle route (/admin/notifications/)."""
from __future__ import annotations

import re

from app.extensions import db
from app.mail import NOTIFICATION_CATALOG, _is_notify_enabled
from app.models.settings import AppSettings, get_settings


def _get_csrf(client) -> str:
    resp = client.get("/admin/notifications/")
    m = re.search(rb'name="csrf_token" value="([^"]+)"', resp.data)
    return m.group(1).decode() if m else ""


# ── Catalog structure ─────────────────────────────────────────────────────────


class TestNotificationCatalog:
    def test_catalog_is_nonempty(self):
        assert len(NOTIFICATION_CATALOG) > 0

    def test_all_entries_have_required_keys(self):
        required = {"code", "settings_field", "name_cs", "description_cs",
                    "trigger_cs", "recipient_cs", "templates", "always_on"}
        for entry in NOTIFICATION_CATALOG:
            assert required.issubset(entry.keys()), f"Missing keys in {entry}"

    def test_always_on_entries_have_no_settings_field(self):
        for entry in NOTIFICATION_CATALOG:
            if entry["always_on"]:
                assert entry["settings_field"] is None, (
                    f"always_on entry {entry['code']} must have settings_field=None"
                )

    def test_togglable_entries_have_settings_field(self):
        for entry in NOTIFICATION_CATALOG:
            if not entry["always_on"]:
                assert entry["settings_field"] is not None, (
                    f"togglable entry {entry['code']} must have a settings_field"
                )

    def test_known_codes_present(self):
        codes = {e["code"] for e in NOTIFICATION_CATALOG}
        expected = {
            "assignment_confirmed", "assignment_released",
            "event_published", "assignments_opened", "event_cancelled",
            "unfilled_reminder", "debriefing_invitation",
            "account_activated", "auth", "admin_digest",
        }
        assert expected.issubset(codes)


# ── GET ───────────────────────────────────────────────────────────────────────


class TestNotificationsGet:
    def test_admin_can_view(self, admin_client):
        resp = admin_client.get("/admin/notifications/")
        assert resp.status_code == 200
        assert "E-mailová oznámení".encode() in resp.data

    def test_non_admin_forbidden(self, client):
        resp = client.get("/admin/notifications/")
        assert resp.status_code in (302, 403)

    def test_catalog_codes_rendered(self, admin_client):
        resp = admin_client.get("/admin/notifications/")
        for entry in NOTIFICATION_CATALOG:
            assert entry["code"].encode() in resp.data

    def test_always_on_badge_rendered(self, admin_client):
        resp = admin_client.get("/admin/notifications/")
        assert "Vždy".encode() in resp.data


# ── POST (toggle) ─────────────────────────────────────────────────────────────


class TestNotificationsToggle:
    def test_disable_assignment_notifications(self, app, admin_client):
        csrf = _get_csrf(admin_client)
        # POST without notify_assignment → it should be set to False
        resp = admin_client.post(
            "/admin/notifications/",
            data={
                "csrf_token": csrf,
                "notify_event_lifecycle": "on",
                "notify_event_cancelled": "on",
                "notify_unfilled_reminder": "on",
                "notify_debriefing": "on",
                # notify_assignment intentionally omitted
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            settings = db.session.get(AppSettings, 1)
            assert settings.notify_assignment is False
            assert settings.notify_event_lifecycle is True

    def test_enable_all_succeeds(self, app, admin_client):
        csrf = _get_csrf(admin_client)
        resp = admin_client.post(
            "/admin/notifications/",
            data={
                "csrf_token": csrf,
                "notify_assignment": "on",
                "notify_event_lifecycle": "on",
                "notify_event_cancelled": "on",
                "notify_unfilled_reminder": "on",
                "notify_debriefing": "on",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            settings = db.session.get(AppSettings, 1)
            assert settings.notify_assignment is True
            assert settings.notify_debriefing is True

    def test_save_flashes_success(self, admin_client):
        csrf = _get_csrf(admin_client)
        resp = admin_client.post(
            "/admin/notifications/",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert "Nastavení oznámení bylo uloženo".encode() in resp.data

    def test_toggle_creates_audit_log(self, app, admin_client):
        from app.models.audit import AuditLogEntry
        csrf = _get_csrf(admin_client)
        admin_client.post(
            "/admin/notifications/",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        with app.app_context():
            entry = db.session.scalars(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "AppSettings")
                .order_by(AuditLogEntry.id.desc())
                .limit(1)
            ).first()
            assert entry is not None
            assert "oznámení" in entry.summary.lower()


# ── _is_notify_enabled helper ─────────────────────────────────────────────────


class TestIsNotifyEnabled:
    def test_returns_true_when_enabled(self, app):
        with app.app_context():
            settings = get_settings()
            settings.notify_assignment = True
            db.session.commit()
            assert _is_notify_enabled("notify_assignment") is True

    def test_returns_false_when_disabled(self, app):
        with app.app_context():
            settings = get_settings()
            settings.notify_assignment = False
            db.session.commit()
            assert _is_notify_enabled("notify_assignment") is False

    def test_unknown_field_defaults_true(self, app):
        with app.app_context():
            assert _is_notify_enabled("notify_nonexistent_field") is True
