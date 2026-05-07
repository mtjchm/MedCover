"""Tests for equipment inventory CRUD and permissions."""
from app.extensions import db
from app.models.equipment import EquipmentCategory, EquipmentItem, EquipmentType
from app.models.event import Event, EventStatus
from app.models.master_event import MasterEvent


def _make_type(app, name: str = "Test Type", category: EquipmentCategory = EquipmentCategory.SHARED) -> int:
    with app.app_context():
        et = EquipmentType(name=name, category=category)
        db.session.add(et)
        db.session.commit()
        return et.id


def _make_item(app, type_id: int, name: str = "Test Item") -> int:
    with app.app_context():
        item = EquipmentItem(name=name, type_id=type_id)
        db.session.add(item)
        db.session.commit()
        return item.id


def _make_event(app) -> int:
    with app.app_context():
        me = MasterEvent(name="Test ME")
        db.session.add(me)
        db.session.flush()
        event = Event(
            name="Test Event",
            master_event_id=me.id,
            status=EventStatus.DRAFT,
            start_datetime=__import__('datetime').datetime(2030, 6, 1, 10, 0, tzinfo=__import__('datetime').timezone.utc),
            end_datetime=__import__('datetime').datetime(2030, 6, 1, 18, 0, tzinfo=__import__('datetime').timezone.utc),
        )
        db.session.add(event)
        db.session.commit()
        return event.id


class TestEquipmentTypeList:
    def test_list_accessible_for_admin(self, admin_client):
        response = admin_client.get("/equipment/")
        assert response.status_code == 200

    def test_list_accessible_for_member(self, member_client):
        response = member_client.get("/equipment/")
        assert response.status_code == 200

    def test_list_requires_login(self, client):
        response = client.get("/equipment/", follow_redirects=False)
        assert response.status_code == 302


class TestEquipmentTypeCreate:
    def test_create_page_loads_for_admin(self, admin_client):
        response = admin_client.get("/equipment/types/create")
        assert response.status_code == 200

    def test_create_page_forbidden_for_member(self, member_client):
        response = member_client.get("/equipment/types/create")
        assert response.status_code == 403

    def test_admin_can_create_type(self, app, admin_client):
        response = admin_client.post(
            "/equipment/types/create",
            data={"name": "Defibrilátor", "category": "shared", "description": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            et = db.session.scalar(db.select(EquipmentType).where(EquipmentType.name == "Defibrilátor"))
            assert et is not None
            assert et.category == EquipmentCategory.SHARED

    def test_create_type_missing_name(self, admin_client):
        response = admin_client.post(
            "/equipment/types/create",
            data={"name": "", "category": "shared"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_member_cannot_create_type(self, member_client):
        response = member_client.post(
            "/equipment/types/create",
            data={"name": "Test", "category": "shared"},
        )
        assert response.status_code == 403


class TestEquipmentTypeEdit:
    def test_admin_can_edit_type(self, app, admin_client):
        type_id = _make_type(app, "Old Name")
        response = admin_client.post(
            f"/equipment/types/{type_id}/edit",
            data={"name": "New Name", "category": "personal", "version": "1"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            et = db.session.get(EquipmentType, type_id)
            assert et.name == "New Name"
            assert et.category == EquipmentCategory.PERSONAL

    def test_optimistic_lock_conflict(self, app, admin_client):
        type_id = _make_type(app)
        response = admin_client.post(
            f"/equipment/types/{type_id}/edit",
            data={"name": "New Name", "category": "shared", "version": "99"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "mezitím změněn" in response.data.decode("utf-8")


class TestEquipmentTypeDelete:
    def test_admin_can_delete_empty_type(self, app, admin_client):
        type_id = _make_type(app)
        response = admin_client.post(
            f"/equipment/types/{type_id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(EquipmentType, type_id) is None

    def test_cannot_delete_type_with_items(self, app, admin_client):
        type_id = _make_type(app)
        _make_item(app, type_id)
        response = admin_client.post(
            f"/equipment/types/{type_id}/delete",
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            assert db.session.get(EquipmentType, type_id) is not None


class TestEquipmentItemCreate:
    def test_admin_can_create_item(self, app, admin_client):
        type_id = _make_type(app)
        response = admin_client.post(
            "/equipment/items/create",
            data={"name": "AED Unit 1", "type_id": str(type_id), "serial_number": "SN001"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            item = db.session.scalar(db.select(EquipmentItem).where(EquipmentItem.name == "AED Unit 1"))
            assert item is not None
            assert item.serial_number == "SN001"

    def test_member_cannot_create_item(self, app, member_client):
        type_id = _make_type(app)
        response = member_client.post(
            "/equipment/items/create",
            data={"name": "Test", "type_id": str(type_id)},
        )
        assert response.status_code == 403


class TestEquipmentItemIssue:
    def test_admin_can_issue_item(self, app, admin_client):
        type_id = _make_type(app, category=EquipmentCategory.PERSONAL)
        item_id = _make_item(app, type_id)
        # get user id
        from app.models.user import UserAccount
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            user_id = str(user.id)
        response = admin_client.post(
            f"/equipment/items/{item_id}/issue",
            data={"user_id": user_id},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            item = db.session.get(EquipmentItem, item_id)
            assert item.issued_to_id is not None

    def test_admin_can_return_item(self, app, admin_client):
        type_id = _make_type(app, category=EquipmentCategory.PERSONAL)
        item_id = _make_item(app, type_id)
        from app.models.user import UserAccount
        from datetime import datetime, timezone
        with app.app_context():
            user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            item = db.session.get(EquipmentItem, item_id)
            item.issued_to_id = user.id
            item.issued_at = datetime.now(timezone.utc)
            db.session.commit()
        response = admin_client.post(
            f"/equipment/items/{item_id}/return",
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            item = db.session.get(EquipmentItem, item_id)
            assert item.issued_to_id is None


class TestEventEquipmentPlan:
    def test_admin_can_add_plan_entry(self, app, admin_client):
        type_id = _make_type(app)
        event_id = _make_event(app)
        response = admin_client.post(
            f"/events/{event_id}/equipment/plan",
            data={"type_id": str(type_id), "quantity": "2"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        from app.models.equipment import EventEquipmentPlan
        with app.app_context():
            plan = db.session.get(EventEquipmentPlan, (event_id, type_id))
            assert plan is not None
            assert plan.quantity_required == 2

    def test_member_cannot_add_plan_entry(self, app, member_client):
        type_id = _make_type(app)
        event_id = _make_event(app)
        response = member_client.post(
            f"/events/{event_id}/equipment/plan",
            data={"type_id": str(type_id), "quantity": "1"},
        )
        assert response.status_code == 403


class TestEventEquipmentAssign:
    def test_admin_can_assign_item(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        event_id = _make_event(app)
        response = admin_client.post(
            f"/events/{event_id}/equipment/assign",
            data={"item_id": str(item_id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        from app.models.equipment import EventEquipmentAssignment
        with app.app_context():
            ea = db.session.scalar(
                db.select(EventEquipmentAssignment).where(
                    EventEquipmentAssignment.event_id == event_id,
                    EventEquipmentAssignment.equipment_item_id == item_id,
                )
            )
            assert ea is not None

    def test_member_cannot_assign_item(self, app, member_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        event_id = _make_event(app)
        response = member_client.post(
            f"/events/{event_id}/equipment/assign",
            data={"item_id": str(item_id)},
        )
        assert response.status_code == 403
