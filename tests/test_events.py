"""Tests for event CRUD and lifecycle transitions."""
from app.extensions import db
from app.models.event import Event, EventStatus
from app.models.master_event import MasterEvent
from app.models.audit import AuditLogEntry


def _make_master_event(app) -> int:
    """Create a master event and return its ID."""
    with app.app_context():
        me = MasterEvent(name="Test ME")
        db.session.add(me)
        db.session.commit()
        return me.id


def _event_form_data(master_event_id: int, name: str = "Test Event") -> dict:
    return {
        "name": name,
        "master_event_id": str(master_event_id),
        "start_datetime": "2030-06-01T10:00",
        "end_datetime": "2030-06-01T18:00",
        "spot_count": "0",
    }


class TestEventListPermissions:
    def test_event_list_requires_login(self, client):
        response = client.get("/events/", follow_redirects=False)
        assert response.status_code == 302

    def test_event_list_accessible_for_member(self, member_client):
        response = member_client.get("/events/")
        assert response.status_code == 200

    def test_event_list_accessible_for_admin(self, admin_client):
        response = admin_client.get("/events/")
        assert response.status_code == 200


class TestEventCreate:
    def test_create_page_loads_for_admin(self, admin_client):
        response = admin_client.get("/events/create")
        assert response.status_code == 200

    def test_create_page_forbidden_for_member(self, member_client):
        response = member_client.get("/events/create")
        assert response.status_code == 403

    def test_admin_can_create_event(self, app, admin_client):
        me_id = _make_master_event(app)
        response = admin_client.post(
            "/events/create",
            data=_event_form_data(me_id),
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            assert event is not None
            assert event.status == EventStatus.DRAFT

    def test_create_event_missing_name_returns_error(self, app, admin_client):
        me_id = _make_master_event(app)
        data = _event_form_data(me_id)
        data["name"] = ""
        response = admin_client.post(
            "/events/create",
            data=data,
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            count = db.session.scalar(db.select(db.func.count()).select_from(Event))
            assert count == 0


class TestEventDetail:
    def test_event_detail_loads(self, app, admin_client):
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            event_id = event.id
        response = admin_client.get(f"/events/{event_id}")
        assert response.status_code == 200


class TestEventLifecycle:
    def _create_event(self, app, admin_client):
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            return event.id

    def test_draft_to_published(self, app, admin_client):
        event_id = self._create_event(app, admin_client)
        response = admin_client.post(
            f"/events/{event_id}/transition",
            data={"target_status": "Zveřejněná"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.status == EventStatus.PUBLISHED

    def test_cannot_skip_status(self, app, admin_client):
        event_id = self._create_event(app, admin_client)
        # Try to jump from DRAFT directly to ASSIGNMENTS_OPEN (not allowed)
        admin_client.post(
            f"/events/{event_id}/transition",
            data={"target_status": "Přihlášky otevřeny"},
            follow_redirects=True,
        )
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.status == EventStatus.DRAFT

    def test_cancel_archives_event(self, app, admin_client):
        event_id = self._create_event(app, admin_client)
        admin_client.post(f"/events/{event_id}/cancel", follow_redirects=True)
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.status == EventStatus.CANCELLED
            assert event.archived is True

    def test_restore_unarchives_event(self, app, admin_client):
        event_id = self._create_event(app, admin_client)
        admin_client.post(f"/events/{event_id}/cancel", follow_redirects=True)
        admin_client.post(f"/events/{event_id}/restore", follow_redirects=True)
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.archived is False

    def test_member_cannot_cancel(self, app, member_client):
        """Create event directly in DB (avoids shared-client conflict) then test permission."""
        with app.app_context():
            from app.models.role import Role
            from app.models.user import UserAccount
            from datetime import datetime, timezone
            me = MasterEvent(name="ME for cancel test")
            db.session.add(me)
            db.session.flush()
            creator_role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
            creator = UserAccount(email="creator_cancel@test.com", name="Creator", is_active=True)
            creator.set_password("testpass123")
            creator.roles = [creator_role]
            db.session.add(creator)
            db.session.flush()
            event = Event(
                name="Cancel Test Event",
                master_event_id=me.id,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
                created_by_id=creator.id,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

        response = member_client.post(f"/events/{event_id}/cancel", follow_redirects=False)
        assert response.status_code == 403


class TestEventEdit:
    def test_admin_can_edit_event(self, app, admin_client):
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            event_id = event.id
            version = event.version

        response = admin_client.post(
            f"/events/{event_id}/edit",
            data={
                **_event_form_data(me_id, name="Updated Event"),
                "version": str(version),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.name == "Updated Event"

    def test_member_cannot_edit_event(self, app, member_client):
        """Create event directly in DB then test member cannot access edit page."""
        with app.app_context():
            from app.models.role import Role
            from app.models.user import UserAccount
            from datetime import datetime, timezone
            me = MasterEvent(name="ME for edit test")
            db.session.add(me)
            db.session.flush()
            creator_role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
            creator = UserAccount(email="creator_edit@test.com", name="Creator", is_active=True)
            creator.set_password("testpass123")
            creator.roles = [creator_role]
            db.session.add(creator)
            db.session.flush()
            event = Event(
                name="Edit Test Event",
                master_event_id=me.id,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
                created_by_id=creator.id,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

        response = member_client.get(f"/events/{event_id}/edit")
        assert response.status_code == 403


class TestCalendarFeed:
    def test_feed_requires_login(self, client):
        response = client.get("/events/feed", follow_redirects=False)
        assert response.status_code == 302

    def test_feed_returns_json(self, admin_client):
        response = admin_client.get("/events/feed")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_feed_excludes_archived_events_by_default(self, app, admin_client):
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            event_id = event.id
        # Cancel (archives) the event
        admin_client.post(f"/events/{event_id}/cancel", follow_redirects=True)
        # Feed should not include archived events by default
        feed_data = admin_client.get("/events/feed").get_json()
        titles = [e.get("title", "") for e in feed_data]
        assert not any("Test Event" in t for t in titles)


class TestAuditChangeTracking:
    """Verify audit log captures before/after changes in {field: [old, new]} format."""

    def test_event_edit_records_changes(self, app, admin_client):
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            event_id = event.id
            version = event.version

        admin_client.post(
            f"/events/{event_id}/edit",
            data={
                **_event_form_data(me_id, name="Renamed Event"),
                "version": str(version),
            },
            follow_redirects=False,
        )

        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "Event")
                .where(AuditLogEntry.action_type == "edit")
                .where(AuditLogEntry.entity_id == str(event_id))
                .order_by(AuditLogEntry.id.desc())
            )
            assert entry is not None
            assert entry.changes_json is not None
            # Must use {field: [old, new]} format
            assert "name" in entry.changes_json
            assert entry.changes_json["name"] == ["Test Event", "Renamed Event"]

    def test_event_edit_no_change_produces_empty_changes(self, app, admin_client):
        """When nothing changes, changes_json should be None or empty dict."""
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            event_id = event.id
            version = event.version

        admin_client.post(
            f"/events/{event_id}/edit",
            data={
                **_event_form_data(me_id, name="Test Event"),
                "version": str(version),
            },
            follow_redirects=False,
        )

        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "Event")
                .where(AuditLogEntry.action_type == "edit")
                .where(AuditLogEntry.entity_id == str(event_id))
                .order_by(AuditLogEntry.id.desc())
            )
            assert entry is not None
            # No fields changed → changes_json should be None or {}
            assert not entry.changes_json

    def test_create_event_end_before_start_rejected(self, app, admin_client):
        me_id = _make_master_event(app)
        data = _event_form_data(me_id)
        # Swap: end is before start
        data["start_datetime"] = "2030-06-01T18:00"
        data["end_datetime"] = "2030-06-01T10:00"
        response = admin_client.post(
            "/events/create",
            data=data,
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            count = db.session.scalar(db.select(db.func.count()).select_from(Event))
            assert count == 0

    def test_create_event_equal_start_end_rejected(self, app, admin_client):
        me_id = _make_master_event(app)
        data = _event_form_data(me_id)
        data["start_datetime"] = "2030-06-01T10:00"
        data["end_datetime"] = "2030-06-01T10:00"
        response = admin_client.post(
            "/events/create",
            data=data,
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            count = db.session.scalar(db.select(db.func.count()).select_from(Event))
            assert count == 0


class TestBulkAction:
    def _create_multiple_events(self, app, admin_client, count: int = 2) -> list[int]:
        me_id = _make_master_event(app)
        ids = []
        for i in range(count):
            admin_client.post("/events/create", data=_event_form_data(me_id, name=f"Bulk Event {i}"), follow_redirects=True)
        with app.app_context():
            events = db.session.scalars(db.select(Event).where(Event.name.like("Bulk Event%"))).all()
            ids = [e.id for e in events]
        return ids

    def test_bulk_publish_changes_status(self, app, admin_client):
        ids = self._create_multiple_events(app, admin_client)
        admin_client.post(
            "/events/bulk",
            data={"action": "publish", "event_ids": [str(i) for i in ids]},
            follow_redirects=True,
        )
        with app.app_context():
            for event_id in ids:
                event = db.session.get(Event, event_id)
                assert event.status == EventStatus.PUBLISHED

    def test_bulk_cancel_archives_events(self, app, admin_client):
        ids = self._create_multiple_events(app, admin_client)
        admin_client.post(
            "/events/bulk",
            data={"action": "cancel", "event_ids": [str(i) for i in ids]},
            follow_redirects=True,
        )
        with app.app_context():
            for event_id in ids:
                event = db.session.get(Event, event_id)
                assert event.status == EventStatus.CANCELLED
                assert event.archived is True

    def test_bulk_action_member_forbidden(self, app, member_client):
        response = member_client.post(
            "/events/bulk",
            data={"action": "publish", "event_ids": ["1"]},
            follow_redirects=False,
        )
        assert response.status_code == 403

    def test_bulk_invalid_action_returns_400(self, admin_client):
        response = admin_client.post(
            "/events/bulk",
            data={"action": "destroy_everything", "event_ids": ["1"]},
        )
        assert response.status_code == 400

    def test_bulk_empty_selection_flashes_warning(self, admin_client):
        response = admin_client.post(
            "/events/bulk",
            data={"action": "publish", "event_ids": []},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Žádné akce".encode() in response.data


class TestAddSpot:
    def test_admin_can_add_spot(self, app, admin_client):
        me_id = _make_master_event(app)
        admin_client.post("/events/create", data=_event_form_data(me_id), follow_redirects=True)
        with app.app_context():
            event = db.session.scalar(db.select(Event).where(Event.name == "Test Event"))
            event_id = event.id

        from app.models.event import EventSpot
        response = admin_client.post(
            f"/events/{event_id}/spots/add",
            data={"description": "Zdravotník", "quantity": "1"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(EventSpot).where(EventSpot.event_id == event_id)
            )
            assert count >= 1

    def test_member_cannot_add_spot(self, app, member_client):
        with app.app_context():
            from app.models.role import Role
            from app.models.user import UserAccount
            me = MasterEvent(name="Spot Test ME")
            db.session.add(me)
            db.session.flush()
            creator_role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
            creator = UserAccount(email="creator_spot@test.com", name="Creator", is_active=True)
            creator.set_password("testpass123")
            creator.roles = [creator_role]
            db.session.add(creator)
            db.session.flush()
            from datetime import datetime, timezone
            event = Event(
                name="Spot Test Event",
                master_event_id=me.id,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
                created_by_id=creator.id,
            )
            db.session.add(event)
            db.session.commit()
            event_id = event.id

        response = member_client.post(
            f"/events/{event_id}/spots/add",
            data={"description": "Zdravotník", "quantity": "1"},
        )
        assert response.status_code == 403


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_event_in_status(app, status: EventStatus) -> int:
    """Create an event in the given status and return its ID."""
    from datetime import datetime, timezone
    with app.app_context():
        me = MasterEvent(name=f"ME for {status.value}")
        db.session.add(me)
        db.session.flush()
        event = Event(
            name=f"Event {status.value}",
            master_event_id=me.id,
            status=status,
            start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
            end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
        )
        db.session.add(event)
        db.session.commit()
        return event.id


# ── Edit: extended ────────────────────────────────────────────────────────────

class TestEventEditExtended:
    def test_get_returns_200(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.get(f"/events/{event_id}/edit")
        assert response.status_code == 200

    def test_get_404_for_missing(self, admin_client):
        response = admin_client.get("/events/999999/edit")
        assert response.status_code == 404

    def test_completed_event_redirects(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.COMPLETED)
        response = admin_client.get(f"/events/{event_id}/edit", follow_redirects=False)
        assert response.status_code in (200, 302)

    def test_stale_version_flashes(self, app, admin_client):
        me_id = _make_master_event(app)
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/edit",
            data={**_event_form_data(me_id), "version": "9999"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "mezitím" in response.data.decode()

    def test_empty_name_flashes(self, app, admin_client):
        me_id = _make_master_event(app)
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        with app.app_context():
            version = db.session.get(Event, event_id).version
        data = {**_event_form_data(me_id), "name": "", "version": str(version)}
        response = admin_client.post(
            f"/events/{event_id}/edit", data=data, follow_redirects=True
        )
        assert response.status_code == 200
        assert "povinný" in response.data.decode()

    def test_successful_edit_saves(self, app, admin_client):
        me_id = _make_master_event(app)
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        with app.app_context():
            version = db.session.get(Event, event_id).version
        response = admin_client.post(
            f"/events/{event_id}/edit",
            data={**_event_form_data(me_id, name="Renamed Event"), "version": str(version)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(Event, event_id).name == "Renamed Event"


# ── Transition: edge cases ────────────────────────────────────────────────────

class TestEventTransitionExtended:
    def test_transition_404_for_missing_event(self, admin_client):
        response = admin_client.post(
            "/events/999999/transition", data={"target_status": "PUBLISHED"}
        )
        assert response.status_code == 404

    def test_transition_invalid_status_400(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/transition", data={"target_status": "NOT_VALID_STATUS"}
        )
        assert response.status_code == 400

    def test_transition_not_allowed_flashes(self, app, admin_client):
        """Transitioning DRAFT → COMPLETED is not a valid transition."""
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/transition",
            data={"target_status": EventStatus.COMPLETED.value},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "povolen" in response.data.decode()


# ── Cancel ────────────────────────────────────────────────────────────────────

class TestEventCancel:
    def test_member_cannot_cancel(self, app, member_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = member_client.post(f"/events/{event_id}/cancel")
        assert response.status_code == 403

    def test_cancel_404_for_missing(self, admin_client):
        response = admin_client.post("/events/999999/cancel")
        assert response.status_code == 404

    def test_cancel_completed_event_flashes(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.COMPLETED)
        response = admin_client.post(f"/events/{event_id}/cancel", follow_redirects=True)
        assert response.status_code == 200
        assert "nelze" in response.data.decode() or "Dokončen" in response.data.decode()

    def test_cancel_draft_event_succeeds(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(f"/events/{event_id}/cancel", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.status == EventStatus.CANCELLED
            assert event.archived is True


# ── Restore ───────────────────────────────────────────────────────────────────

class TestEventRestore:
    def test_member_cannot_restore(self, app, member_client):
        event_id = _make_event_in_status(app, EventStatus.CANCELLED)
        response = member_client.post(f"/events/{event_id}/restore")
        assert response.status_code == 403

    def test_restore_404_for_missing(self, admin_client):
        response = admin_client.post("/events/999999/restore")
        assert response.status_code == 404

    def test_restore_non_cancelled_flashes(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(f"/events/{event_id}/restore", follow_redirects=True)
        assert response.status_code == 200
        assert "zrušen" in response.data.decode()

    def test_restore_cancelled_succeeds(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.CANCELLED)
        response = admin_client.post(f"/events/{event_id}/restore", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            event = db.session.get(Event, event_id)
            assert event.status == EventStatus.DRAFT
            assert event.archived is False


# ── Calendar feed ─────────────────────────────────────────────────────────────

class TestCalendarFeedExtended:
    def test_feed_returns_json_for_admin(self, app, admin_client):
        _make_event_in_status(app, EventStatus.PUBLISHED)
        response = admin_client.get("/events/feed")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_feed_member_cannot_see_drafts(self, app, member_client):
        """Member does not have event.view_draft so draft events are excluded."""
        _make_event_in_status(app, EventStatus.DRAFT)
        response = member_client.get("/events/feed")
        assert response.status_code == 200
        data = response.get_json()
        statuses = [item["extendedProps"]["status_key"] for item in data]
        assert "DRAFT" not in statuses


# ── Edit spot ─────────────────────────────────────────────────────────────────

class TestEditSpot:
    def _create_event_with_spot(self, app) -> tuple[int, int]:
        from datetime import datetime, timezone
        from app.models.event import EventSpot
        with app.app_context():
            me = MasterEvent(name="EditSpot ME")
            db.session.add(me)
            db.session.flush()
            event = Event(
                name="EditSpot Event",
                master_event_id=me.id,
                status=EventStatus.DRAFT,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
            )
            db.session.add(event)
            db.session.flush()
            spot = EventSpot(event_id=event.id, description="Old Desc")
            db.session.add(spot)
            db.session.commit()
            return event.id, spot.id

    def test_member_cannot_edit_spot(self, app, member_client):
        event_id, spot_id = self._create_event_with_spot(app)
        response = member_client.post(
            f"/events/{event_id}/spots/{spot_id}/edit", data={}
        )
        assert response.status_code == 403

    def test_spot_404_for_missing(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/spots/999999/edit", data={"description": "X"}
        )
        assert response.status_code == 404

    def test_edit_spot_saves_description(self, app, admin_client):
        from app.models.event import EventSpot
        event_id, spot_id = self._create_event_with_spot(app)
        response = admin_client.post(
            f"/events/{event_id}/spots/{spot_id}/edit",
            data={"description": "New Desc"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            spot = db.session.get(EventSpot, spot_id)
            assert spot.description == "New Desc"


# ── Delete spot ───────────────────────────────────────────────────────────────

class TestDeleteSpot:
    def _create_event_with_spot(self, app) -> tuple[int, int]:
        from datetime import datetime, timezone
        from app.models.event import EventSpot
        with app.app_context():
            me = MasterEvent(name="DelSpot ME")
            db.session.add(me)
            db.session.flush()
            event = Event(
                name="DelSpot Event",
                master_event_id=me.id,
                status=EventStatus.DRAFT,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
            )
            db.session.add(event)
            db.session.flush()
            spot = EventSpot(event_id=event.id)
            db.session.add(spot)
            db.session.commit()
            return event.id, spot.id

    def test_member_cannot_delete_spot(self, app, member_client):
        event_id, spot_id = self._create_event_with_spot(app)
        response = member_client.post(f"/events/{event_id}/spots/{spot_id}/delete")
        assert response.status_code == 403

    def test_delete_404_for_missing_spot(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(f"/events/{event_id}/spots/999999/delete")
        assert response.status_code == 404

    def test_delete_spot_succeeds(self, app, admin_client):
        from app.models.event import EventSpot
        event_id, spot_id = self._create_event_with_spot(app)
        response = admin_client.post(
            f"/events/{event_id}/spots/{spot_id}/delete", follow_redirects=False
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(EventSpot, spot_id) is None


# ── Equipment plan: extended ──────────────────────────────────────────────────

class TestEquipmentPlanExtended:
    def _make_event_and_type(self, app):
        from app.models.equipment import EquipmentType, EquipmentCategory
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        with app.app_context():
            et = EquipmentType(name="Plan Type", category=EquipmentCategory.SHARED)
            db.session.add(et)
            db.session.commit()
            return event_id, et.id

    def test_plan_add_404_for_missing_event(self, app, admin_client):
        from app.models.equipment import EquipmentType, EquipmentCategory
        with app.app_context():
            et = EquipmentType(name="Plan T2", category=EquipmentCategory.SHARED)
            db.session.add(et)
            db.session.commit()
            type_id = et.id
        response = admin_client.post(
            "/events/999999/equipment/plan",
            data={"type_id": str(type_id), "quantity": "1"},
        )
        assert response.status_code == 404

    def test_plan_add_invalid_type_quantity_flashes(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/equipment/plan",
            data={"type_id": "", "quantity": "0"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "platný" in response.data.decode() or "typ" in response.data.decode().lower()

    def test_plan_remove_works(self, app, admin_client):
        from app.models.equipment import EventEquipmentPlan
        event_id, type_id = self._make_event_and_type(app)
        # Add a plan entry
        admin_client.post(
            f"/events/{event_id}/equipment/plan",
            data={"type_id": str(type_id), "quantity": "1"},
            follow_redirects=True,
        )
        # Remove it
        response = admin_client.post(
            f"/events/{event_id}/equipment/plan/remove",
            data={"type_id": str(type_id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(EventEquipmentPlan, (event_id, type_id)) is None


# ── Equipment assign: extended ────────────────────────────────────────────────

class TestEquipmentAssignExtended:
    def _make_event_type_item(self, app):
        from app.models.equipment import EquipmentType, EquipmentCategory, EquipmentItem
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        with app.app_context():
            et = EquipmentType(name="Assign Type", category=EquipmentCategory.SHARED)
            db.session.add(et)
            db.session.flush()
            item = EquipmentItem(name="Assign Item", type_id=et.id)
            db.session.add(item)
            db.session.commit()
            return event_id, item.id

    def test_assign_duplicate_item_flashes(self, app, admin_client):
        event_id, item_id = self._make_event_type_item(app)
        admin_client.post(
            f"/events/{event_id}/equipment/assign",
            data={"item_id": str(item_id)},
            follow_redirects=True,
        )
        response = admin_client.post(
            f"/events/{event_id}/equipment/assign",
            data={"item_id": str(item_id)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "přiřazena" in response.data.decode() or "již" in response.data.decode()

    def test_unassign_no_item_id_flashes(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/equipment/unassign", data={}, follow_redirects=True
        )
        assert response.status_code == 200
        assert "Chybí" in response.data.decode() or "položka" in response.data.decode()

    def test_unassign_not_found_flashes(self, app, admin_client):
        event_id = _make_event_in_status(app, EventStatus.DRAFT)
        response = admin_client.post(
            f"/events/{event_id}/equipment/unassign",
            data={"item_id": "999999"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "nenalezeno" in response.data.decode() or "přiřazení" in response.data.decode()

    def test_unassign_succeeds(self, app, admin_client):
        from app.models.equipment import EventEquipmentAssignment
        event_id, item_id = self._make_event_type_item(app)
        admin_client.post(
            f"/events/{event_id}/equipment/assign",
            data={"item_id": str(item_id)},
            follow_redirects=True,
        )
        response = admin_client.post(
            f"/events/{event_id}/equipment/unassign",
            data={"item_id": str(item_id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            import sqlalchemy as sa
            ea = db.session.scalar(
                sa.select(EventEquipmentAssignment).where(
                    EventEquipmentAssignment.event_id == event_id,
                    EventEquipmentAssignment.equipment_item_id == item_id,
                )
            )
            assert ea is None
