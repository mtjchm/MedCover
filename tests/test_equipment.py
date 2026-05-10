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


# ── Type create: validation edge cases ───────────────────────────────────────

class TestEquipmentTypeCreateExtended:
    def test_invalid_category_flashes(self, admin_client):
        response = admin_client.post(
            "/equipment/types/create",
            data={"name": "Valid Name", "category": "not_a_category"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "kategorie" in response.data.decode()

    def test_duplicate_name_flashes(self, app, admin_client):
        _make_type(app, "Duplicate Type")
        response = admin_client.post(
            "/equipment/types/create",
            data={"name": "Duplicate Type", "category": "shared"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "existuje" in response.data.decode()


# ── Type edit: extended ───────────────────────────────────────────────────────

class TestEquipmentTypeEditExtended:
    def test_get_returns_200(self, app, admin_client):
        type_id = _make_type(app)
        response = admin_client.get(f"/equipment/types/{type_id}/edit")
        assert response.status_code == 200

    def test_404_for_missing_type(self, admin_client):
        response = admin_client.get("/equipment/types/999999/edit")
        assert response.status_code == 404

    def test_edit_invalid_category_flashes(self, app, admin_client):
        type_id = _make_type(app)
        with app.app_context():
            et = db.session.get(EquipmentType, type_id)
            version = et.version
        response = admin_client.post(
            f"/equipment/types/{type_id}/edit",
            data={"name": "Valid", "category": "bad_cat", "version": str(version)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "kategorie" in response.data.decode()

    def test_edit_duplicate_name_flashes(self, app, admin_client):
        type_id = _make_type(app, "Type A")
        _make_type(app, "Type B")
        with app.app_context():
            et = db.session.get(EquipmentType, type_id)
            version = et.version
        response = admin_client.post(
            f"/equipment/types/{type_id}/edit",
            data={"name": "Type B", "category": "shared", "version": str(version)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "existuje" in response.data.decode()

    def test_edit_empty_name_flashes(self, app, admin_client):
        type_id = _make_type(app)
        with app.app_context():
            version = db.session.get(EquipmentType, type_id).version
        response = admin_client.post(
            f"/equipment/types/{type_id}/edit",
            data={"name": "", "category": "shared", "version": str(version)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "povinný" in response.data.decode()

    def test_edit_member_forbidden(self, app, member_client):
        type_id = _make_type(app)
        response = member_client.post(f"/equipment/types/{type_id}/edit", data={})
        assert response.status_code == 403

    def test_null_description_renders_empty_not_none(self, app, admin_client):
        """Regression for #84: NULL description must render as '' not 'None'."""
        type_id = _make_type(app)  # description is NULL by default
        response = admin_client.get(f"/equipment/types/{type_id}/edit")
        body = response.data.decode()
        assert "None" not in body


# ── Type delete: extended ─────────────────────────────────────────────────────

class TestEquipmentTypeDeleteExtended:
    def test_delete_404_for_missing(self, admin_client):
        response = admin_client.post("/equipment/types/999999/delete")
        assert response.status_code == 404

    def test_delete_member_forbidden(self, app, member_client):
        type_id = _make_type(app)
        response = member_client.post(f"/equipment/types/{type_id}/delete")
        assert response.status_code == 403


# ── Items list: filters ───────────────────────────────────────────────────────

class TestEquipmentItemsList:
    def test_list_returns_200(self, admin_client):
        response = admin_client.get("/equipment/items/")
        assert response.status_code == 200

    def test_filter_by_type_returns_200(self, app, admin_client):
        type_id = _make_type(app)
        response = admin_client.get(f"/equipment/items/?type_id={type_id}")
        assert response.status_code == 200

    def test_filter_issued_yes(self, admin_client):
        response = admin_client.get("/equipment/items/?issued=yes")
        assert response.status_code == 200

    def test_filter_issued_no(self, admin_client):
        response = admin_client.get("/equipment/items/?issued=no")
        assert response.status_code == 200

    def test_list_member_forbidden(self, member_client):
        """Member has equipment.view, so 200 is correct — test that access works."""
        response = member_client.get("/equipment/items/")
        assert response.status_code == 200


# ── Item create: extended validation ─────────────────────────────────────────

class TestEquipmentItemCreateExtended:
    def test_get_returns_200(self, admin_client):
        response = admin_client.get("/equipment/items/create")
        assert response.status_code == 200

    def test_empty_name_flashes(self, app, admin_client):
        type_id = _make_type(app)
        response = admin_client.post(
            "/equipment/items/create",
            data={"name": "", "type_id": str(type_id)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "povinný" in response.data.decode()

    def test_missing_type_flashes(self, admin_client):
        response = admin_client.post(
            "/equipment/items/create",
            data={"name": "Item", "type_id": ""},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "povinný" in response.data.decode() or "Typ" in response.data.decode()

    def test_invalid_type_flashes(self, admin_client):
        response = admin_client.post(
            "/equipment/items/create",
            data={"name": "Item", "type_id": "999999"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Neplatný" in response.data.decode() or "typ" in response.data.decode()


# ── Item edit ─────────────────────────────────────────────────────────────────

class TestEquipmentItemEdit:
    def test_get_returns_200(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = admin_client.get(f"/equipment/items/{item_id}/edit")
        assert response.status_code == 200

    def test_404_for_missing_item(self, admin_client):
        response = admin_client.get("/equipment/items/999999/edit")
        assert response.status_code == 404

    def test_stale_version_flashes(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = admin_client.post(
            f"/equipment/items/{item_id}/edit",
            data={"name": "New", "type_id": str(type_id), "version": "999"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "mezitím" in response.data.decode()

    def test_empty_name_flashes(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        with app.app_context():
            version = db.session.get(EquipmentItem, item_id).version
        response = admin_client.post(
            f"/equipment/items/{item_id}/edit",
            data={"name": "", "type_id": str(type_id), "version": str(version)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "povinný" in response.data.decode()

    def test_successful_edit_redirects(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        with app.app_context():
            version = db.session.get(EquipmentItem, item_id).version
        response = admin_client.post(
            f"/equipment/items/{item_id}/edit",
            data={"name": "Renamed Item", "type_id": str(type_id), "version": str(version)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(EquipmentItem, item_id).name == "Renamed Item"

    def test_member_forbidden(self, app, member_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = member_client.post(f"/equipment/items/{item_id}/edit", data={})
        assert response.status_code == 403

    def test_null_optional_fields_render_empty_not_none(self, app, admin_client):
        """Regression for #84: NULL optional fields must render as '' not 'None'."""
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)  # serial_number/home_location/notes all NULL
        response = admin_client.get(f"/equipment/items/{item_id}/edit")
        body = response.data.decode()
        assert "None" not in body


# ── Item delete: extended ─────────────────────────────────────────────────────

class TestEquipmentItemDeleteExtended:
    def test_delete_success(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = admin_client.post(f"/equipment/items/{item_id}/delete", follow_redirects=False)
        assert response.status_code == 302
        with app.app_context():
            assert db.session.get(EquipmentItem, item_id) is None

    def test_delete_404_for_missing(self, admin_client):
        response = admin_client.post("/equipment/items/999999/delete")
        assert response.status_code == 404

    def test_delete_issued_item_flashes(self, app, admin_client):
        from app.models.user import UserAccount
        from datetime import datetime, timezone
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        with app.app_context():
            admin = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            item = db.session.get(EquipmentItem, item_id)
            item.issued_to_id = admin.id
            item.issued_at = datetime.now(timezone.utc)
            db.session.commit()
        response = admin_client.post(f"/equipment/items/{item_id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert "vydána" in response.data.decode() or "nelze" in response.data.decode()

    def test_delete_member_forbidden(self, app, member_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = member_client.post(f"/equipment/items/{item_id}/delete")
        assert response.status_code == 403


# ── Item issue/return: extended ───────────────────────────────────────────────

class TestEquipmentItemIssueExtended:
    def test_already_issued_flashes(self, app, admin_client):
        from app.models.user import UserAccount
        from datetime import datetime, timezone
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        with app.app_context():
            admin = db.session.scalar(db.select(UserAccount).where(UserAccount.email == "admin@test.com"))
            item = db.session.get(EquipmentItem, item_id)
            item.issued_to_id = admin.id
            item.issued_at = datetime.now(timezone.utc)
            db.session.commit()
            user_id = str(admin.id)
        response = admin_client.post(
            f"/equipment/items/{item_id}/issue",
            data={"user_id": user_id},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "vydána" in response.data.decode() or "již" in response.data.decode()

    def test_no_user_id_flashes(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = admin_client.post(
            f"/equipment/items/{item_id}/issue", data={}, follow_redirects=True
        )
        assert response.status_code == 200
        assert "povinný" in response.data.decode() or "uživatel" in response.data.decode().lower()

    def test_user_not_found_flashes(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = admin_client.post(
            f"/equipment/items/{item_id}/issue",
            data={"user_id": "00000000-0000-0000-0000-000000000000"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "nalezen" in response.data.decode() or "uživatel" in response.data.decode().lower()


class TestEquipmentItemReturnExtended:
    def test_not_issued_flashes(self, app, admin_client):
        type_id = _make_type(app)
        item_id = _make_item(app, type_id)
        response = admin_client.post(
            f"/equipment/items/{item_id}/return", follow_redirects=True
        )
        assert response.status_code == 200
        assert "vydána" in response.data.decode() or "není" in response.data.decode()
