"""Tests for the debriefing blueprint: submit, edit, event overview."""
from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.models.assignment import Assignment, DebriefingRecord
from app.models.audit import AuditLogEntry
from app.models.event import Event, EventSpot, EventStatus
from app.models.master_event import MasterEvent
from app.models.role import Role
from app.models.user import UserAccount
from tests.conftest import _make_user, _login

# Use a dedicated email so this doesn't clash with the member_client fixture
_ASSIGNED_EMAIL = "assigned_member@test.com"


def _setup_completed_assignment(app) -> tuple[int, int, int]:
    """Create a completed event with one spot assigned to _ASSIGNED_EMAIL.

    Returns (event_id, spot_id, assignment_id).
    The assigned user's email is _ASSIGNED_EMAIL so callers can log in fresh.
    """
    with app.app_context():
        me = MasterEvent(name="Test ME")
        db.session.add(me)
        db.session.flush()

        admin_role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
        creator = UserAccount(email="creator@test.com", name="Creator", is_active=True)
        creator.set_password("testpass123")
        creator.roles = [admin_role]
        db.session.add(creator)
        db.session.flush()

        assigned = _make_user(_ASSIGNED_EMAIL, "Assigned Member", Role.MEMBER)
        assigned_id = assigned.id

        event = Event(
            name="Completed Event",
            master_event_id=me.id,
            start_datetime=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            end_datetime=datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc),
            status=EventStatus.COMPLETED,
            created_by_id=creator.id,
        )
        db.session.add(event)
        db.session.flush()

        spot = EventSpot(event_id=event.id)
        db.session.add(spot)
        db.session.flush()

        assignment = Assignment(
            spot_id=spot.id,
            user_id=assigned_id,
            assigned_by_id=creator.id,
        )
        db.session.add(assignment)
        db.session.commit()

        return event.id, spot.id, assignment.id


def _assigned_client(app):
    """Return a fresh test client logged in as the assigned member."""
    c = app.test_client()
    _login(c, _ASSIGNED_EMAIL)
    return c


# ── Submit / View ─────────────────────────────────────────────────────────────


class TestDebriefingSubmit:
    def test_submit_requires_login(self, app, client):
        _, _, assignment_id = _setup_completed_assignment(app)
        response = client.get(f"/debriefing/{assignment_id}", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_assigned_user_can_view_own_debrief_form(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        response = c.get(f"/debriefing/{assignment_id}")
        assert response.status_code == 200

    def test_debrief_not_accessible_for_non_completed_event(self, app, admin_client):
        """Debriefing form must redirect when event is not Completed."""
        with app.app_context():
            me = MasterEvent(name="Active ME")
            db.session.add(me)
            db.session.flush()
            admin_role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
            creator = UserAccount(email="creator2@test.com", name="Creator2", is_active=True)
            creator.set_password("testpass123")
            creator.roles = [admin_role]
            db.session.add(creator)
            db.session.flush()
            event = Event(
                name="Open Event",
                master_event_id=me.id,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
                status=EventStatus.ASSIGNMENTS_OPEN,
                created_by_id=creator.id,
            )
            db.session.add(event)
            db.session.flush()
            spot = EventSpot(event_id=event.id)
            db.session.add(spot)
            db.session.flush()
            assignment = Assignment(
                spot_id=spot.id,
                user_id=creator.id,
                assigned_by_id=creator.id,
            )
            db.session.add(assignment)
            db.session.commit()
            assignment_id = assignment.id

        response = admin_client.get(f"/debriefing/{assignment_id}", follow_redirects=True)
        assert response.status_code == 200
        assert "Hlášení lze vyplnit".encode() in response.data

    def test_stranger_cannot_view_others_debrief(self, app, member_client):
        """A member (member@test.com) must not access assigned_member@test.com's debrief."""
        _, _, assignment_id = _setup_completed_assignment(app)
        # member_client is member@test.com, assignment belongs to assigned_member@test.com
        response = member_client.get(f"/debriefing/{assignment_id}")
        assert response.status_code == 403

    def test_assigned_user_can_submit_own_debrief(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        response = c.post(
            f"/debriefing/{assignment_id}",
            data={
                "actual_hours": "4.5",
                "patients_treated": "3",
                "materials_used": "Obvazy",
                "feedback": "Vše proběhlo dobře.",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            record = db.session.scalar(
                db.select(DebriefingRecord).where(DebriefingRecord.assignment_id == assignment_id)
            )
            assert record is not None
            assert float(record.actual_hours) == 4.5
            assert record.patients_treated == 3
            assert record.materials_used == "Obvazy"

    def test_invalid_hours_rejected(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        response = c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "abc", "patients_treated": "0"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "platný počet hodin".encode() in response.data
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(DebriefingRecord)
                .where(DebriefingRecord.assignment_id == assignment_id)
            )
            assert count == 0

    def test_negative_hours_rejected(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        response = c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "-1", "patients_treated": "0"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "platný počet hodin".encode() in response.data

    def test_submit_writes_audit_log(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "2", "patients_treated": "0"},
            follow_redirects=True,
        )
        with app.app_context():
            entry = db.session.scalar(
                db.select(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "DebriefingRecord")
                .where(AuditLogEntry.action_type == "create")
            )
            assert entry is not None

    def test_debrief_404_for_missing_assignment(self, admin_client):
        response = admin_client.get("/debriefing/999999")
        assert response.status_code == 404


# ── Edit existing debrief ─────────────────────────────────────────────────────


class TestDebriefingEdit:
    def test_assigned_user_can_update_own_debrief(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        # Submit initial debrief
        c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "2", "patients_treated": "1"},
            follow_redirects=True,
        )
        # Update it
        c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "5", "patients_treated": "10", "feedback": "Aktualizace"},
            follow_redirects=True,
        )
        with app.app_context():
            record = db.session.scalar(
                db.select(DebriefingRecord).where(DebriefingRecord.assignment_id == assignment_id)
            )
            assert float(record.actual_hours) == 5
            assert record.patients_treated == 10
            assert record.feedback == "Aktualizace"

    def test_edit_writes_audit_log(self, app):
        _, _, assignment_id = _setup_completed_assignment(app)
        c = _assigned_client(app)
        c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "2", "patients_treated": "0"},
            follow_redirects=True,
        )
        c.post(
            f"/debriefing/{assignment_id}",
            data={"actual_hours": "3", "patients_treated": "0"},
            follow_redirects=True,
        )
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(AuditLogEntry)
                .where(AuditLogEntry.entity_type == "DebriefingRecord")
            )
            # create + edit = 2 entries
            assert count >= 2


# ── Event overview ────────────────────────────────────────────────────────────


class TestDebriefingEventOverview:
    def test_coordinator_can_view_event_overview(self, app, coordinator_client):
        event_id, _, assignment_id = _setup_completed_assignment(app)
        response = coordinator_client.get(f"/debriefing/event/{event_id}")
        assert response.status_code == 200

    def test_admin_can_view_event_overview(self, app, admin_client):
        event_id, _, _ = _setup_completed_assignment(app)
        response = admin_client.get(f"/debriefing/event/{event_id}")
        assert response.status_code == 200

    def test_member_cannot_view_event_overview(self, app, member_client):
        event_id, _, _ = _setup_completed_assignment(app)
        response = member_client.get(f"/debriefing/event/{event_id}")
        assert response.status_code == 403

    def test_event_overview_requires_login(self, app, client):
        event_id, _, _ = _setup_completed_assignment(app)
        response = client.get(f"/debriefing/event/{event_id}", follow_redirects=False)
        assert response.status_code == 302

    def test_event_overview_404_for_missing(self, admin_client):
        response = admin_client.get("/debriefing/event/999999")
        assert response.status_code == 404
