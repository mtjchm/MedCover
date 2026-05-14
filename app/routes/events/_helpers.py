"""Shared helpers for the events blueprint sub-modules."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import url_for
from flask_login import current_user

from app.extensions import db
from app.models.event import Event, EventSpot, EventStatus, EventTemplate, EventType
from app.models.equipment import (
    EquipmentItem,
    EventEquipmentAssignment,
    EventEquipmentPlan,
)
from app.models.qualification import Qualification
from app.models.role import Role
from app.models.user import UserAccount

PRAGUE_TZ = ZoneInfo("Europe/Prague")

# Valid manual lifecycle transitions: (from_status, to_status, required_permission)
TRANSITIONS: list[tuple[EventStatus, EventStatus, str]] = [
    (EventStatus.DRAFT,               EventStatus.PUBLISHED,            "event.publish"),
    (EventStatus.PUBLISHED,           EventStatus.ASSIGNMENTS_OPEN,     "event.assignments.open"),
    (EventStatus.ASSIGNMENTS_OPEN,    EventStatus.ASSIGNMENTS_CLOSED,   "event.assignments.close"),
    (EventStatus.ASSIGNMENTS_CLOSED,  EventStatus.ASSIGNMENTS_OPEN,     "event.assignments.open"),
]

# Maps action name → (target_status, required_permission, valid_from_statuses)
BULK_ACTIONS: dict[str, tuple[EventStatus, str, set[EventStatus]]] = {
    "publish": (
        EventStatus.PUBLISHED,
        "event.publish",
        {EventStatus.DRAFT},
    ),
    "open_assignments": (
        EventStatus.ASSIGNMENTS_OPEN,
        "event.assignments.open",
        {EventStatus.PUBLISHED, EventStatus.ASSIGNMENTS_CLOSED},
    ),
    "cancel": (
        EventStatus.CANCELLED,
        "event.cancel",
        {EventStatus.DRAFT, EventStatus.PUBLISHED, EventStatus.ASSIGNMENTS_OPEN, EventStatus.ASSIGNMENTS_CLOSED},
    ),
}

# FullCalendar event background colours by status value
STATUS_COLORS: dict[str, str] = {
    "Koncept":              "#6c757d",
    "Zveřejněná":          "#0d6efd",
    "Přihlášky otevřeny":  "#198754",
    "Přihlášky uzavřeny":  "#ffc107",
    "Dokončena":            "#212529",
    "Zrušena":              "#adb5bd",
}

PER_PAGE = 75


def can_view(event: Event) -> bool:
    """Check whether current_user can see *event* based on its status."""
    if event.status == EventStatus.DRAFT:
        return current_user.has_permission("event.view_draft")
    return current_user.has_permission("event.view")


def parse_event_form(form: dict, existing: Event | None = None) -> tuple[Event | None, str | None]:
    """Parse the event form and return (event, error_message).

    All datetime inputs are interpreted as Europe/Prague local time and stored
    as UTC in the database.
    """
    _PRAGUE = ZoneInfo("Europe/Prague")

    def _local_to_utc(s: str) -> datetime:
        """Parse a naive datetime string (Prague local time) and return UTC."""
        return datetime.fromisoformat(s).replace(tzinfo=_PRAGUE).astimezone(timezone.utc)

    name = form.get("name", "").strip()
    master_event_id = form.get("master_event_id", "").strip()
    start_str = form.get("start_datetime", "").strip()
    end_str = form.get("end_datetime", "").strip()
    address = form.get("address", "").strip() or None
    contact_person = form.get("contact_person", "").strip() or None
    description = form.get("description", "").strip() or None
    paid = form.get("paid") == "1"
    responsible_person_id = form.get("responsible_person_id") or None
    assignments_open_str = form.get("assignments_open_datetime", "").strip()

    # Event type
    event_type_str = form.get("event_type", "").strip()
    event_type = EventType[event_type_str] if event_type_str in EventType.__members__ else EventType.MEDICAL_COVER

    # Training-specific: planned participant count (optional)
    planned_participants_count: int | None = None
    if event_type == EventType.TRAINING:
        ppc_str = form.get("planned_participants_count", "").strip()
        if ppc_str:
            try:
                planned_participants_count = int(ppc_str)
                if planned_participants_count < 0:
                    return None, "Plánovaný počet účastníků musí být nezáporné číslo."
            except ValueError:
                return None, "Plánovaný počet účastníků musí být celé číslo."

    if not name:
        return None, "Název akce je povinný."
    if not master_event_id:
        return None, "Nadřazená akce je povinná."
    if not start_str or not end_str:
        return None, "Datum a čas začátku i konce jsou povinné."

    try:
        start_dt = _local_to_utc(start_str)
        end_dt = _local_to_utc(end_str)
    except ValueError:
        return None, "Neplatný formát data a času."

    if end_dt <= start_dt:
        return None, "Konec akce musí být po začátku."

    # Validate RP: Viewer-only users cannot be RP (AD17)
    if responsible_person_id:
        rp_user = db.session.get(UserAccount, responsible_person_id)
        if rp_user:
            rp_role_names = {r.name for r in rp_user.roles}
            if rp_role_names <= {Role.VIEWER}:
                return None, (
                    f"Uživatel {rp_user.name} má pouze roli Pozorovatel a nemůže být "
                    "odpovědnou osobou. Jako OP je potřeba mít roli Člen nebo vyšší."
                )

    assignments_open_dt = None
    if assignments_open_str:
        try:
            assignments_open_dt = _local_to_utc(assignments_open_str)
        except ValueError:
            return None, "Neplatný formát data otevření přihlášek."

    if existing is not None:
        existing.name = name
        existing.master_event_id = int(master_event_id)
        existing.start_datetime = start_dt
        existing.end_datetime = end_dt
        existing.address = address
        existing.contact_person = contact_person
        existing.description = description
        existing.paid = paid
        existing.responsible_person_id = responsible_person_id
        existing.assignments_open_datetime = assignments_open_dt
        existing.event_type = event_type
        # Reset planned_participants_count when type changes away from TRAINING
        existing.planned_participants_count = planned_participants_count
        return existing, None

    event = Event(
        name=name,
        master_event_id=int(master_event_id),
        start_datetime=start_dt,
        end_datetime=end_dt,
        address=address,
        contact_person=contact_person,
        description=description,
        paid=paid,
        responsible_person_id=responsible_person_id,
        assignments_open_datetime=assignments_open_dt,
        created_by_id=current_user.id,
        event_type=event_type,
        planned_participants_count=planned_participants_count,
    )
    return event, None


def build_spots(event: Event, form: dict) -> None:
    """Create spots from the dynamic spot builder fields (spot_desc_N / spot_cred_N / spot_optional_N)."""
    try:
        spot_total = int(form.get("spot_total", 0) or 0)
    except (ValueError, TypeError):
        spot_total = 0

    for i in range(spot_total):
        description = (form.get(f"spot_desc_{i}") or "").strip() or None
        is_optional = form.get(f"spot_optional_{i}") == "1"
        qual_ids = [int(c) for c in form.getlist(f"spot_cred_{i}") if str(c).isdigit()]
        qualifications = db.session.scalars(
            db.select(Qualification).where(Qualification.id.in_(qual_ids), Qualification.is_deleted.is_(False))
        ).all() if qual_ids else []
        spot = EventSpot(event_id=event.id, description=description, is_optional=is_optional)
        spot.required_qualifications = list(qualifications)
        db.session.add(spot)


def build_spots_from_template(event: Event, template: object) -> None:
    """Create event spots and equipment plans matching a template."""
    if not isinstance(template, EventTemplate):
        return
    for st in template.spot_templates:
        spot = EventSpot(event_id=event.id, description=st.description, is_optional=st.is_optional)
        spot.required_qualifications = list(st.required_qualifications)
        db.session.add(spot)
    for ep in template.equipment_plans:
        plan = EventEquipmentPlan(
            event_id=event.id,
            equipment_type_id=ep.equipment_type_id,
            quantity_required=ep.quantity_required,
        )
        db.session.add(plan)


def build_equipment_assignments(event: Event, item_ids: list[int]) -> None:
    """Create EventEquipmentAssignment records for *item_ids* on *event*.

    Silently skips unavailable items or IDs that don't resolve to a real item.
    Caller must have already flushed the event so event.id is set.
    """
    for item_id in item_ids:
        item = db.session.get(EquipmentItem, item_id)
        if item is None or not item.is_available:
            continue
        db.session.add(EventEquipmentAssignment(event_id=event.id, equipment_item_id=item.id))


def equipment_warnings_for_event(event: Event) -> list[dict]:
    """Return a list of warning dicts for items already assigned to *event*.

    Each dict has keys: item_name, status ("unavailable"|"conflict"),
    reason (str|None), conflicting_event (dict|None).
    """
    warnings: list[dict] = []
    assigned_items = [ea.equipment_item for ea in event.equipment_assignments]
    if not assigned_items:
        return warnings

    # Separate unavailable items (no DB query needed)
    available_ids: list[int] = []
    for item in assigned_items:
        if not item.is_available:
            warnings.append({
                "item_name": item.name,
                "status": "unavailable",
                "reason": item.unavailability_reason or "Bez udaného důvodu",
                "conflicting_event": None,
            })
        else:
            available_ids.append(item.id)

    # Single query for all conflicts across all available assigned items
    if available_ids:
        conflicts = db.session.scalars(
            db.select(EventEquipmentAssignment)
            .join(Event, EventEquipmentAssignment.event_id == Event.id)
            .where(
                EventEquipmentAssignment.equipment_item_id.in_(available_ids),
                EventEquipmentAssignment.event_id != event.id,
                Event.start_datetime < event.end_datetime,
                Event.end_datetime > event.start_datetime,
            )
        ).all()
        # Build item_id → name lookup
        id_to_name = {item.id: item.name for item in assigned_items}
        for c in conflicts:
            ce = c.event
            warnings.append({
                "item_name": id_to_name[c.equipment_item_id],
                "status": "conflict",
                "reason": None,
                "conflicting_event": {
                    "name": ce.name,
                    "start": ce.start_datetime,
                    "end": ce.end_datetime,
                    "url": url_for("events.detail", event_id=ce.id),
                },
            })
    return warnings


def copy_spots_with_assignments(source: Event, target: Event) -> None:
    """Copy spots (+ qualifications + existing assignments) from source to target."""
    from app.models.assignment import Assignment

    for spot in source.spots:
        new_spot = EventSpot(
            event_id=target.id,
            description=spot.description,
            is_optional=spot.is_optional,
        )
        new_spot.required_qualifications = list(spot.required_qualifications)
        db.session.add(new_spot)
        db.session.flush()  # need new_spot.id for the assignment

        if spot.assignment is not None:
            new_assignment = Assignment(
                spot_id=new_spot.id,
                user_id=spot.assignment.user_id,
            )
            db.session.add(new_assignment)


def copy_equipment(source: Event, target: Event) -> None:
    """Copy equipment plans and assignments from source to target."""
    for plan in source.equipment_plans:
        db.session.add(EventEquipmentPlan(
            event_id=target.id,
            equipment_type_id=plan.equipment_type_id,
            quantity_required=plan.quantity_required,
        ))
    for ea in source.equipment_assignments:
        db.session.add(EventEquipmentAssignment(
            event_id=target.id,
            equipment_item_id=ea.equipment_item_id,
        ))
