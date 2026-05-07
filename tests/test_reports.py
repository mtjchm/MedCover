"""Tests for the reports blueprint."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta


from app.extensions import db
from app.models.assignment import Assignment, DebriefingRecord
from app.models.event import Event, EventSpot, EventStatus
from app.models.master_event import MasterEvent
from app.models.role import Role
from app.models.user import UserAccount


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(email: str, name: str, role_name: str) -> UserAccount:
    role = db.session.scalar(db.select(Role).where(Role.name == role_name))
    user = UserAccount(email=email, name=name, is_active=True)
    user.set_password("testpass123")
    user.roles = [role]
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email: str) -> None:
    client.post("/auth/login", data={"email": email, "password": "testpass123"}, follow_redirects=True)


def _make_me(name: str = "Testovací nadřazená akce") -> MasterEvent:
    me = MasterEvent(name=name)
    db.session.add(me)
    db.session.commit()
    return me


def _make_event(
    me: MasterEvent,
    name: str = "Testovací akce",
    status: EventStatus = EventStatus.COMPLETED,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Event:
    now = datetime.now(timezone.utc)
    ev = Event(
        name=name,
        master_event_id=me.id,
        status=status,
        start_datetime=start or now - timedelta(hours=4),
        end_datetime=end or now - timedelta(hours=2),
    )
    db.session.add(ev)
    db.session.commit()
    return ev


def _make_spot(event: Event) -> EventSpot:
    spot = EventSpot(event_id=event.id)
    db.session.add(spot)
    db.session.commit()
    return spot


def _make_assignment(spot: EventSpot, user: UserAccount, admin: UserAccount) -> Assignment:
    asgn = Assignment(spot_id=spot.id, user_id=user.id, assigned_by_id=admin.id)
    db.session.add(asgn)
    db.session.commit()
    return asgn


def _make_debriefing(asgn: Assignment, actual_hours: float = 2.0, patients: int = 3) -> DebriefingRecord:
    dr = DebriefingRecord(
        assignment_id=asgn.id,
        submitted_by_id=asgn.user_id,
        actual_hours=actual_hours,
        patients_treated=patients,
    )
    db.session.add(dr)
    db.session.commit()
    return dr


# ── Index ─────────────────────────────────────────────────────────────────────

class TestReportsIndex:
    def test_redirect_when_not_logged_in(self, client):
        resp = client.get("/reports/", follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_can_access_index(self, app, client):
        with app.app_context():
            _make_user("admin_rep@test.com", "Admin Rep", Role.ADMIN)
        _login(client, "admin_rep@test.com")
        resp = client.get("/reports/")
        assert resp.status_code == 200
        assert "Přehledy".encode() in resp.data

    def test_member_can_access_index(self, app, client):
        """Members have report.view permission."""
        with app.app_context():
            _make_user("member_rep@test.com", "Member Rep", Role.MEMBER)
        _login(client, "member_rep@test.com")
        resp = client.get("/reports/")
        assert resp.status_code == 200

    def test_unauthenticated_cannot_access_index(self, client):
        resp = client.get("/reports/", follow_redirects=False)
        assert resp.status_code == 302


# ── Per-user report ───────────────────────────────────────────────────────────

class TestUserReport:
    def test_member_can_access_own_report(self, app, client):
        with app.app_context():
            user = _make_user("member_own@test.com", "Own Member", Role.MEMBER)
            user_id = user.id
        _login(client, "member_own@test.com")
        resp = client.get(f"/reports/user/{user_id}")
        assert resp.status_code == 200

    def test_user_without_permission_cannot_access_other_user_report(self, app, client):
        """A user with no roles (no report.view) cannot view another user's report."""
        with app.app_context():
            # Create user with no roles (no report.view)
            norole = UserAccount(email="norole@test.com", name="No Role", is_active=True)
            norole.set_password("testpass123")
            db.session.add(norole)
            other = _make_user("other_norole@test.com", "Other User", Role.MEMBER)
            other_id = other.id
            db.session.commit()
        _login(client, "norole@test.com")
        resp = client.get(f"/reports/user/{other_id}")
        assert resp.status_code == 403

    def test_user_without_permission_can_access_own_report(self, app, client):
        """A user with no roles can still view their own report."""
        with app.app_context():
            norole = UserAccount(email="norole_own@test.com", name="No Role Own", is_active=True)
            norole.set_password("testpass123")
            db.session.add(norole)
            db.session.commit()
            norole_id = norole.id
        _login(client, "norole_own@test.com")
        resp = client.get(f"/reports/user/{norole_id}")
        assert resp.status_code == 200

    def test_admin_can_access_any_user_report(self, app, client):
        with app.app_context():
            _make_user("admin_ur@test.com", "Admin UR", Role.ADMIN)
            member = _make_user("member_c@test.com", "Member C", Role.MEMBER)
            member_id = member.id
        _login(client, "admin_ur@test.com")
        resp = client.get(f"/reports/user/{member_id}")
        assert resp.status_code == 200

    def test_coordinator_can_access_other_user_report(self, app, client):
        with app.app_context():
            _make_user("coord_ur@test.com", "Coord UR", Role.COORDINATOR)
            member = _make_user("member_d@test.com", "Member D", Role.MEMBER)
            member_id = member.id
        _login(client, "coord_ur@test.com")
        resp = client.get(f"/reports/user/{member_id}")
        assert resp.status_code == 200

    def test_404_for_nonexistent_user(self, app, client):
        with app.app_context():
            _make_user("admin_404@test.com", "Admin 404", Role.ADMIN)
        _login(client, "admin_404@test.com")
        resp = client.get(f"/reports/user/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_user_report_shows_correct_event_count(self, app, client):
        with app.app_context():
            admin = _make_user("admin_cnt@test.com", "Admin Cnt", Role.ADMIN)
            member = _make_user("member_cnt@test.com", "Member Cnt", Role.MEMBER)
            member_id = member.id

            me = _make_me("ME Count")
            ev1 = _make_event(me, "Akce 1", EventStatus.COMPLETED)
            ev2 = _make_event(me, "Akce 2", EventStatus.COMPLETED)
            # one event not assigned to member
            _make_event(me, "Akce 3", EventStatus.COMPLETED)

            spot1 = _make_spot(ev1)
            spot2 = _make_spot(ev2)
            _make_assignment(spot1, member, admin)
            _make_assignment(spot2, member, admin)

        _login(client, "admin_cnt@test.com")
        resp = client.get(f"/reports/user/{member_id}")
        assert resp.status_code == 200
        # member has 2 assignments
        assert b"Akce 1" in resp.data
        assert b"Akce 2" in resp.data
        assert b"Akce 3" not in resp.data

    def test_user_report_shows_debriefing_data(self, app, client):
        with app.app_context():
            admin = _make_user("admin_deb@test.com", "Admin Deb", Role.ADMIN)
            member = _make_user("member_deb@test.com", "Member Deb", Role.MEMBER)
            member_id = member.id

            me = _make_me("ME Deb")
            ev = _make_event(me, "Debriefing Akce", EventStatus.COMPLETED)
            spot = _make_spot(ev)
            asgn = _make_assignment(spot, member, admin)
            _make_debriefing(asgn, actual_hours=5.5, patients=7)

        _login(client, "admin_deb@test.com")
        resp = client.get(f"/reports/user/{member_id}")
        assert resp.status_code == 200
        assert b"5.5" in resp.data
        assert b"7" in resp.data


# ── Per-ME report ─────────────────────────────────────────────────────────────

class TestMEReport:
    def test_admin_can_access_me_report(self, app, client):
        with app.app_context():
            _make_user("admin_me@test.com", "Admin ME", Role.ADMIN)
            me = _make_me("ME Test Report")
            me_id = me.id
        _login(client, "admin_me@test.com")
        resp = client.get(f"/reports/master-event/{me_id}")
        assert resp.status_code == 200
        assert b"ME Test Report" in resp.data

    def test_member_can_access_me_report(self, app, client):
        with app.app_context():
            _make_user("member_me@test.com", "Member ME", Role.MEMBER)
            me = _make_me("ME Member Report")
            me_id = me.id
        _login(client, "member_me@test.com")
        resp = client.get(f"/reports/master-event/{me_id}")
        assert resp.status_code == 200

    def test_unauthenticated_cannot_access_me_report(self, app, client):
        with app.app_context():
            me = _make_me("ME Viewer")
            me_id = me.id
        resp = client.get(f"/reports/master-event/{me_id}", follow_redirects=False)
        assert resp.status_code == 302

    def test_me_report_404_for_nonexistent(self, app, client):
        with app.app_context():
            _make_user("admin_me404@test.com", "Admin ME 404", Role.ADMIN)
        _login(client, "admin_me404@test.com")
        resp = client.get("/reports/master-event/99999")
        assert resp.status_code == 404

    def test_me_report_shows_events(self, app, client):
        with app.app_context():
            admin = _make_user("admin_mev@test.com", "Admin MEV", Role.ADMIN)
            member = _make_user("member_mev@test.com", "Member MEV", Role.MEMBER)
            me = _make_me("ME With Events")
            me_id = me.id
            ev = _make_event(me, "Event V1", EventStatus.COMPLETED)
            spot = _make_spot(ev)
            asgn = _make_assignment(spot, member, admin)
            _make_debriefing(asgn, actual_hours=3.0, patients=2)
        _login(client, "admin_mev@test.com")
        resp = client.get(f"/reports/master-event/{me_id}")
        assert resp.status_code == 200
        assert b"Event V1" in resp.data
        assert b"3.0" in resp.data


# ── Date-range report ─────────────────────────────────────────────────────────

class TestDateRangeReport:
    def test_get_shows_form(self, app, client):
        with app.app_context():
            _make_user("admin_dr@test.com", "Admin DR", Role.ADMIN)
        _login(client, "admin_dr@test.com")
        resp = client.get("/reports/date-range")
        assert resp.status_code == 200
        assert b"from_date" in resp.data
        assert b"to_date" in resp.data

    def test_get_with_params_shows_results(self, app, client):
        with app.app_context():
            _make_user("admin_drp@test.com", "Admin DRP", Role.ADMIN)
            me = _make_me("ME DR Params")
            now = datetime.now(timezone.utc)
            _make_event(me, "DR Akce", EventStatus.COMPLETED,
                        start=now - timedelta(days=1),
                        end=now - timedelta(days=1) + timedelta(hours=2))
        _login(client, "admin_drp@test.com")
        from_d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        to_d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp = client.get(f"/reports/date-range?from_date={from_d}&to_date={to_d}")
        assert resp.status_code == 200
        assert b"DR Akce" in resp.data

    def test_date_range_only_returns_events_in_range(self, app, client):
        with app.app_context():
            _make_user("admin_drr@test.com", "Admin DRR", Role.ADMIN)
            me = _make_me("ME DR Range")
            now = datetime.now(timezone.utc)
            # inside range
            _make_event(me, "In Range", EventStatus.COMPLETED,
                        start=now - timedelta(days=3),
                        end=now - timedelta(days=3) + timedelta(hours=2))
            # outside range
            _make_event(me, "Out of Range", EventStatus.COMPLETED,
                        start=now - timedelta(days=30),
                        end=now - timedelta(days=30) + timedelta(hours=2))
        _login(client, "admin_drr@test.com")
        from_d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        to_d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp = client.get(f"/reports/date-range?from_date={from_d}&to_date={to_d}")
        assert resp.status_code == 200
        assert b"In Range" in resp.data
        assert b"Out of Range" not in resp.data

    def test_date_range_empty_result_for_no_events(self, app, client):
        with app.app_context():
            _make_user("admin_dre@test.com", "Admin DRE", Role.ADMIN)
        _login(client, "admin_dre@test.com")
        resp = client.get("/reports/date-range?from_date=2000-01-01&to_date=2000-01-31")
        assert resp.status_code == 200
        # Should not error, may show empty message
        assert b"date-range" in resp.data or b"from_date" in resp.data

    def test_unauthenticated_cannot_access_date_range(self, client):
        resp = client.get("/reports/date-range", follow_redirects=False)
        assert resp.status_code == 302
