"""Tests for spot assignment: claim, release, permissions."""
from app.extensions import db
from app.models.event import Event, EventSpot, EventStatus
from app.models.assignment import Assignment
from app.models.master_event import MasterEvent
from app.models.role import Role
from app.models.user import UserAccount
from tests.conftest import _make_user


def _setup_open_event(app) -> tuple[int, int]:
    """Create a published, assignments-open event with one spot. Returns (event_id, spot_id)."""
    with app.app_context():
        me = MasterEvent(name="Test ME")
        db.session.add(me)
        db.session.flush()

        role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
        creator = UserAccount(email="creator@test.com", name="Creator", is_active=True)
        creator.set_password("testpass123")
        creator.roles = [role]
        db.session.add(creator)
        db.session.flush()

        from datetime import datetime, timezone
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
        db.session.commit()

        return event.id, spot.id


class TestAssignmentClaim:
    def test_member_can_claim_open_spot(self, app, member_client):
        event_id, spot_id = _setup_open_event(app)
        response = member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            assignment = db.session.scalar(
                db.select(Assignment).where(Assignment.spot_id == spot_id)
            )
            assert assignment is not None
            # Verify the correct user is stored
            member = db.session.scalar(
                db.select(UserAccount).where(UserAccount.email == "member@test.com")
            )
            assert assignment.user_id == member.id

    def test_claim_already_taken_spot_is_rejected(self, app, member_client):
        event_id, spot_id = _setup_open_event(app)
        # First claim
        member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)
        # Second claim (same user, same spot — spot is now taken)
        response = member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)
        assert response.status_code == 200  # Back to detail, with flash
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(Assignment).where(Assignment.spot_id == spot_id)
            )
            assert count == 1  # Only one assignment, not two

    def test_claim_requires_login(self, app, client):
        _, spot_id = _setup_open_event(app)
        response = client.post(f"/assignments/claim/{spot_id}", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_cannot_claim_spot_in_draft_event(self, app, member_client):
        """Spot in a DRAFT event should not be claimable."""
        with app.app_context():
            me = MasterEvent(name="Test ME")
            db.session.add(me)
            db.session.flush()

            role = db.session.scalar(db.select(Role).where(Role.name == Role.ADMIN))
            creator = UserAccount(email="creator2@test.com", name="Creator2", is_active=True)
            creator.set_password("testpass123")
            creator.roles = [role]
            db.session.add(creator)
            db.session.flush()

            from datetime import datetime, timezone
            event = Event(
                name="Draft Event",
                master_event_id=me.id,
                start_datetime=datetime(2030, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_datetime=datetime(2030, 6, 1, 18, 0, tzinfo=timezone.utc),
                status=EventStatus.DRAFT,
                created_by_id=creator.id,
            )
            db.session.add(event)
            db.session.flush()

            spot = EventSpot(event_id=event.id)
            db.session.add(spot)
            db.session.commit()
            spot_id = spot.id

        member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(Assignment).where(Assignment.spot_id == spot_id)
            )
            assert count == 0


class TestAssignmentRelease:
    def test_member_can_release_own_assignment(self, app, member_client):
        event_id, spot_id = _setup_open_event(app)
        member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)
        with app.app_context():
            assignment = db.session.scalar(
                db.select(Assignment).where(Assignment.spot_id == spot_id)
            )
            assignment_id = assignment.id

        response = member_client.post(
            f"/assignments/release/{assignment_id}", follow_redirects=False
        )
        assert response.status_code == 302
        with app.app_context():
            remaining = db.session.get(Assignment, assignment_id)
            assert remaining is None


class TestAdminAssignment:
    def test_admin_can_assign_other_user(self, app, admin_client):
        event_id, spot_id = _setup_open_event(app)
        with app.app_context():
            _make_user("target@test.com", "Target", Role.MEMBER)
            target = db.session.scalar(
                db.select(UserAccount).where(UserAccount.email == "target@test.com")
            )
            target_id = str(target.id)

        response = admin_client.post(
            f"/assignments/assign/{spot_id}",
            data={"user_id": target_id},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            assignment = db.session.scalar(
                db.select(Assignment).where(Assignment.spot_id == spot_id)
            )
            assert assignment is not None

    def test_member_cannot_assign_others(self, app, member_client):
        event_id, spot_id = _setup_open_event(app)
        with app.app_context():
            _make_user("target@test.com", "Target", Role.MEMBER)
            target = db.session.scalar(
                db.select(UserAccount).where(UserAccount.email == "target@test.com")
            )
            target_id = str(target.id)

        response = member_client.post(
            f"/assignments/assign/{spot_id}",
            data={"user_id": target_id},
            follow_redirects=False,
        )
        assert response.status_code == 403

    def test_second_user_cannot_claim_taken_spot(self, app, member_client):
        """A different user should not be able to claim a spot already taken by another user."""
        event_id, spot_id = _setup_open_event(app)

        # First member claims the spot
        member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)

        # Second member (fresh client — separate session) tries to claim the same spot
        with app.app_context():
            _make_user("member2@test.com", "Second Member", Role.MEMBER)

        from tests.conftest import _login
        second_client = app.test_client()
        _login(second_client, "member2@test.com")
        response = second_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)

        assert response.status_code == 200
        with app.app_context():
            count = db.session.scalar(
                db.select(db.func.count()).select_from(Assignment).where(Assignment.spot_id == spot_id)
            )
            assert count == 1  # Still only one assignment


class TestAssignmentReleaseOwnership:
    def test_member_cannot_release_others_assignment(self, app, member_client):
        """A member must not be able to release another user's assignment."""
        event_id, spot_id = _setup_open_event(app)

        # First member claims the spot
        member_client.post(f"/assignments/claim/{spot_id}", follow_redirects=True)
        with app.app_context():
            assignment = db.session.scalar(
                db.select(Assignment).where(Assignment.spot_id == spot_id)
            )
            assignment_id = assignment.id

        # Second member (fresh client — separate session) tries to release it
        with app.app_context():
            _make_user("member2@test.com", "Second Member", Role.MEMBER)
        from tests.conftest import _login
        second_client = app.test_client()
        _login(second_client, "member2@test.com")
        response = second_client.post(f"/assignments/release/{assignment_id}", follow_redirects=False)

        assert response.status_code == 403
        with app.app_context():
            remaining = db.session.get(Assignment, assignment_id)
            assert remaining is not None  # Assignment must still exist
