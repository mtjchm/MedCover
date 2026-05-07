"""Tests for event CRUD and lifecycle transitions."""
from app.extensions import db
from app.models.event import Event, EventStatus
from app.models.master_event import MasterEvent


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
