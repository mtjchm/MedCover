"""
Event CRUD blueprint.

Lifecycle state machine:
  Draft → Published (manual, event.publish)
  Published → Assignments Open (manual trigger or automatic via scheduler)
  Assignments Open → Assignments Closed (manual or auto when fully staffed)
  Assignments Closed → Assignments Open (manual re-open)
  Assignments Closed → Completed (automatic after end_datetime passes)
  Any non-Completed → Cancelled (manual, event.cancel)
  Cancelled → Draft (manual restore, event.restore)
  Completed cannot be cancelled.

Permissions:
  event.view         — view published+ events
  event.view_draft   — view draft events
  event.create       — create events
  event.edit         — edit events
  event.publish      — Draft → Published
  event.assignments.open  — Published → Assignments Open (manual)
  event.assignments.close — Assignments Open → Assignments Closed
  event.cancel       — → Cancelled
  event.restore      — Cancelled → Draft
"""

from __future__ import annotations

from flask import Blueprint, Response, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models.event import Event, EventSpot, EventStatus, EventTemplate
from app.models.master_event import MasterEvent
from app.models.user import UserAccount
from app.models.audit import AuditLogEntry
from app.models.equipment import EquipmentItem, EquipmentType, EventEquipmentPlan, EventEquipmentAssignment
from app.models.qualification import Qualification
from app.models.assignment import Assignment
from app.utils import diff_changes
import app.mail as mailer
from zoneinfo import ZoneInfo

_PRAGUE_TZ = ZoneInfo("Europe/Prague")

events_bp = Blueprint("events", __name__, url_prefix="/events")

# Valid manual lifecycle transitions: (from_status, to_status, required_permission)
_TRANSITIONS: list[tuple[EventStatus, EventStatus, str]] = [
    (EventStatus.DRAFT,               EventStatus.PUBLISHED,            "event.publish"),
    (EventStatus.PUBLISHED,           EventStatus.ASSIGNMENTS_OPEN,     "event.assignments.open"),
    (EventStatus.ASSIGNMENTS_OPEN,    EventStatus.ASSIGNMENTS_CLOSED,   "event.assignments.close"),
    (EventStatus.ASSIGNMENTS_CLOSED,  EventStatus.ASSIGNMENTS_OPEN,     "event.assignments.open"),
]


def _audit(action: str, event: Event, summary: str, changes: dict | None = None) -> None:
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type=action,
        entity_type="Event",
        entity_id=str(event.id),
        summary=summary,
        changes_json=changes,
    ))


def _can_view(event: Event) -> bool:
    if event.status == EventStatus.DRAFT:
        return current_user.has_permission("event.view_draft")
    return current_user.has_permission("event.view")


# ── List ──────────────────────────────────────────────────────────────────────

@events_bp.get("/")
@login_required
def index() -> str:
    if not current_user.has_any_permission("event.view", "event.view_draft"):
        abort(403)

    show_archived = request.args.get("archived") == "1"
    query = db.select(Event).order_by(Event.start_datetime.desc())

    if not current_user.has_permission("event.view_draft"):
        query = query.where(Event.status != EventStatus.DRAFT)
    if not show_archived:
        query = query.where(Event.archived == False)  # noqa: E712

    events = db.session.scalars(query).all()
    event_templates: list[EventTemplate] = []
    if current_user.has_permission("event.create"):
        event_templates = list(db.session.scalars(
            db.select(EventTemplate).order_by(EventTemplate.name)
        ).all())

    # Map event_id → list of (spot_id, description) for eligible unfilled spots
    eligible_spot_map: dict[int, list[tuple[int, str | None]]] = {}
    if current_user.has_permission("event.assign_own"):
        user_assigned_spot_ids = set(db.session.scalars(
            db.select(Assignment.spot_id).where(Assignment.user_id == current_user.id)
        ).all())
        for e in events:
            if e.status != EventStatus.ASSIGNMENTS_OPEN:
                continue
            eligible = [
                (s.id, s.description)
                for s in e.spots
                if s.assignment is None and s.id not in user_assigned_spot_ids and s.is_eligible(current_user)
            ]
            if eligible:
                eligible_spot_map[e.id] = eligible

    return render_template(
        "events/index.html",
        events=events,
        show_archived=show_archived,
        EventStatus=EventStatus,
        has_draft_perm=current_user.has_permission("event.view_draft"),
        event_templates=event_templates,
        eligible_spot_map=eligible_spot_map,
    )


# ── Calendar JSON feed ────────────────────────────────────────────────────────

# FullCalendar event background colours by status value
_STATUS_COLORS: dict[str, str] = {
    "Koncept":              "#6c757d",
    "Zveřejněná":          "#0d6efd",
    "Přihlášky otevřeny":  "#198754",
    "Přihlášky uzavřeny":  "#ffc107",
    "Dokončena":            "#212529",
    "Zrušena":              "#adb5bd",
}


@events_bp.get("/feed")
@login_required
def feed() -> Response:
    """Return events as FullCalendar-compatible JSON."""
    if not current_user.has_any_permission("event.view", "event.view_draft"):
        abort(403)

    show_archived = request.args.get("archived") == "1"

    query = db.select(Event)
    if not current_user.has_permission("event.view_draft"):
        query = query.where(Event.status != EventStatus.DRAFT)
    if not show_archived:
        query = query.where(Event.archived == False)  # noqa: E712

    events = db.session.scalars(query).all()
    items = []
    for e in events:
        color = _STATUS_COLORS.get(e.status.value, "#6c757d")
        items.append({
            "id": e.id,
            "title": e.name,
            "start": e.start_datetime.isoformat(),
            "end": e.end_datetime.isoformat(),
            "url": url_for("events.detail", event_id=e.id),
            "backgroundColor": color,
            "borderColor": color,
            "textColor": "#000" if e.status.value == "Přihlášky uzavřeny" else "#fff",
            "extendedProps": {
                "status": e.status.value,
                "status_key": e.status.name,
                "filled": e.mandatory_filled_spots,
                "total": e.mandatory_total_spots,
                "rp": e.responsible_person.name if e.responsible_person else None,
                "start_local": e.start_datetime.astimezone(_PRAGUE_TZ).strftime("%d.%m.%Y %H:%M"),
                "end_local": e.end_datetime.astimezone(_PRAGUE_TZ).strftime("%d.%m.%Y %H:%M"),
                "me_name": None if e.master_event.is_general else e.master_event.name,
            },
        })
    return jsonify(items)


# ── Create ────────────────────────────────────────────────────────────────────

@events_bp.route("/create", methods=["GET", "POST"])
@login_required
def create() -> str | Response:
    if not current_user.has_permission("event.create"):
        abort(403)

    master_events = db.session.scalars(
        db.select(MasterEvent).where(MasterEvent.archived == False).order_by(MasterEvent.is_general.desc(), MasterEvent.name)  # noqa: E712
    ).all()
    users = db.session.scalars(
        db.select(UserAccount).where(UserAccount.is_active == True).order_by(UserAccount.name)  # noqa: E712
    ).all()
    all_qualifications = db.session.scalars(db.select(Qualification).order_by(Qualification.name)).all()

    if request.method == "POST":
        event, error = _parse_event_form(request.form)
        if error or event is None:
            flash(error or "Chyba formuláře.", "danger")
            return render_template("events/create.html", master_events=master_events, users=users, all_qualifications=all_qualifications)

        db.session.add(event)
        db.session.flush()

        template_id_str = request.form.get("template_id", "").strip()
        if template_id_str:

            tmpl = db.session.get(EventTemplate, int(template_id_str))
            if tmpl:
                _build_spots_from_template(event, tmpl)
            else:
                _build_spots(event, request.form)
        else:
            _build_spots(event, request.form)

        _audit("create", event, f"Vytvořena akce '{event.name}'")
        db.session.commit()

        flash("Akce byla vytvořena.", "success")
        return redirect(url_for("events.detail", event_id=event.id))

    return render_template("events/create.html", master_events=master_events, users=users, all_qualifications=all_qualifications)


# ── Create from template ──────────────────────────────────────────────────────

@events_bp.get("/create-from-template/<int:template_id>")
@login_required
def create_from_template(template_id: int) -> str | Response:
    if not current_user.has_permission("event.create"):
        abort(403)
    tmpl = db.session.get(EventTemplate, template_id)
    if tmpl is None:
        abort(404)

    master_events = db.session.scalars(
        db.select(MasterEvent).where(MasterEvent.archived == False).order_by(MasterEvent.is_general.desc(), MasterEvent.name)  # noqa: E712
    ).all()
    users = db.session.scalars(
        db.select(UserAccount).where(UserAccount.is_active == True).order_by(UserAccount.name)  # noqa: E712
    ).all()
    all_qualifications = db.session.scalars(db.select(Qualification).order_by(Qualification.name)).all()

    return render_template(
        "events/create.html",
        master_events=master_events,
        users=users,
        template=tmpl,
        all_qualifications=all_qualifications,
    )


# ── Detail ────────────────────────────────────────────────────────────────────

@events_bp.get("/<int:event_id>")
@login_required
def detail(event_id: int) -> str | Response:
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if not _can_view(event):
        abort(403)

    eligible_users: list[UserAccount] = []
    if current_user.has_permission("event.assign_other"):
        eligible_users = list(db.session.scalars(
            db.select(UserAccount).where(UserAccount.is_active == True).order_by(UserAccount.name)  # noqa: E712
        ).all())

    all_equipment_types = db.session.scalars(
        db.select(EquipmentType).order_by(EquipmentType.name)
    ).all()
    assigned_item_ids = {ea.equipment_item_id for ea in event.equipment_assignments}
    if assigned_item_ids:
        available_equipment_items = db.session.scalars(
            db.select(EquipmentItem).where(
                EquipmentItem.id.notin_(assigned_item_ids)
            ).order_by(EquipmentItem.name)
        ).all()
    else:
        available_equipment_items = db.session.scalars(
            db.select(EquipmentItem).order_by(EquipmentItem.name)
        ).all()

    all_qualifications = db.session.scalars(
        db.select(Qualification).order_by(Qualification.name)
    ).all()

    # Precompute for JS eligibility check: for each qualification R, which qualification IDs can fill it?
    # fillers_map[R.id] = {R.id} ∪ fillers of each of R's parents (transitively)
    def _fillers(qual: Qualification, _visited: frozenset[int] = frozenset()) -> set[int]:
        if qual.id in _visited:
            return set()
        _visited = _visited | {qual.id}
        result = {qual.id}
        for parent in qual.parents:
            result |= _fillers(parent, _visited)
        return result

    fillers_map = {str(c.id): list(_fillers(c)) for c in all_qualifications}

    return render_template(
        "events/detail.html",
        event=event,
        EventStatus=EventStatus,
        eligible_users=eligible_users,
        all_equipment_types=all_equipment_types,
        available_equipment_items=available_equipment_items,
        all_qualifications=all_qualifications,
        fillers_map=fillers_map,
    )


# ── Edit ──────────────────────────────────────────────────────────────────────

@events_bp.route("/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit(event_id: int) -> str | Response:
    if not current_user.has_permission("event.edit"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    if event.status in (EventStatus.COMPLETED, EventStatus.CANCELLED):
        flash("Dokončené nebo zrušené akce nelze upravovat.", "warning")
        return redirect(url_for("events.detail", event_id=event_id))

    master_events = db.session.scalars(
        db.select(MasterEvent).where(MasterEvent.archived == False).order_by(MasterEvent.is_general.desc(), MasterEvent.name)  # noqa: E712
    ).all()
    users = db.session.scalars(
        db.select(UserAccount).where(UserAccount.is_active == True).order_by(UserAccount.name)  # noqa: E712
    ).all()

    if request.method == "POST":
        submitted_version = int(request.form.get("version", 0))
        if submitted_version != event.version:
            flash("Záznam byl mezitím změněn, načtěte stránku znovu.", "danger")
            return render_template("events/edit.html", event=event, master_events=master_events, users=users)

        # Snapshot before mutation
        before = {
            "name": event.name,
            "master_event_id": event.master_event_id,
            "start_datetime": str(event.start_datetime),
            "end_datetime": str(event.end_datetime),
            "address": event.address,
            "contact_person": event.contact_person,
            "description": event.description,
            "paid": event.paid,
            "responsible_person_id": str(event.responsible_person_id),
            "assignments_open_datetime": str(event.assignments_open_datetime),
        }

        updated, error = _parse_event_form(request.form, existing=event)
        if error:
            flash(error, "danger")
            return render_template("events/edit.html", event=event, master_events=master_events, users=users)

        after = {
            "name": event.name,
            "master_event_id": event.master_event_id,
            "start_datetime": str(event.start_datetime),
            "end_datetime": str(event.end_datetime),
            "address": event.address,
            "contact_person": event.contact_person,
            "description": event.description,
            "paid": event.paid,
            "responsible_person_id": str(event.responsible_person_id),
            "assignments_open_datetime": str(event.assignments_open_datetime),
        }

        event.version += 1
        _audit("edit", event, f"Upravena akce '{event.name}'", diff_changes(before, after))
        db.session.commit()

        flash("Akce byla uložena.", "success")
        return redirect(url_for("events.detail", event_id=event.id))

    return render_template("events/edit.html", event=event, master_events=master_events, users=users)


# ── Lifecycle transitions ─────────────────────────────────────────────────────

@events_bp.post("/<int:event_id>/transition")
@login_required
def transition(event_id: int) -> Response:
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    target = request.form.get("target_status")
    try:
        target_status = EventStatus(target)
    except ValueError:
        abort(400)

    allowed = next(
        (t for t in _TRANSITIONS if t[0] == event.status and t[1] == target_status),
        None,
    )
    if allowed is None:
        flash("Tento přechod stavu není povolen.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    if not current_user.has_permission(allowed[2]):
        abort(403)

    event.status = target_status
    event.version += 1
    _audit("status_change", event, f"Stav akce '{event.name}' změněn na '{target_status.value}'", {
        "before": {"status": event.status.value},
        "after": {"status": target_status.value},
    })
    db.session.commit()

    # Email notifications
    if target_status == EventStatus.PUBLISHED:
        active_users = db.session.scalars(
            db.select(UserAccount).where(UserAccount.is_active == True)  # noqa: E712
        ).all()
        for u in active_users:
            mailer.send_event_published(u.email, u.name, event)
    elif target_status == EventStatus.ASSIGNMENTS_OPEN:
        active_users = db.session.scalars(
            db.select(UserAccount).where(UserAccount.is_active == True)  # noqa: E712
        ).all()
        for u in active_users:
            mailer.send_assignments_opened(u.email, u.name, event)

    flash(f"Stav akce byl změněn na {target_status.value}.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events_bp.post("/<int:event_id>/cancel")
@login_required
def cancel(event_id: int) -> Response:
    if not current_user.has_permission("event.cancel"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.status == EventStatus.COMPLETED:
        flash("Dokončené akce nelze zrušit.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    event.status = EventStatus.CANCELLED
    event.archived = True
    event.version += 1
    _audit("status_change", event, f"Akce '{event.name}' zrušena a archivována")

    # Notify all assigned users before commit so we still have spot data
    assigned_users = [
        (s.assignment.user.email, s.assignment.user.name)
        for s in event.spots if s.assignment
    ]
    db.session.commit()

    for email, name in assigned_users:
        mailer.send_event_cancelled(email, name, event)

    flash("Akce byla zrušena.", "warning")
    return redirect(url_for("events.index"))


@events_bp.post("/<int:event_id>/restore")
@login_required
def restore(event_id: int) -> Response:
    if not current_user.has_permission("event.restore"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.status != EventStatus.CANCELLED:
        flash("Pouze zrušené akce lze obnovit.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    event.status = EventStatus.DRAFT
    event.archived = False
    event.version += 1
    _audit("status_change", event, f"Akce '{event.name}' obnovena do stavu Koncept")
    db.session.commit()

    flash("Akce byla obnovena.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


# ── Bulk lifecycle actions ────────────────────────────────────────────────────

# Maps action name → (target_status, required_permission, valid_from_statuses)
_BULK_ACTIONS: dict[str, tuple[EventStatus, str, set[EventStatus]]] = {
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


@events_bp.post("/bulk")
@login_required
def bulk_action() -> Response:
    action = request.form.get("action", "")
    if action not in _BULK_ACTIONS:
        abort(400)

    target_status, perm, valid_from = _BULK_ACTIONS[action]

    if not current_user.has_permission(perm):
        abort(403)

    raw_ids = request.form.getlist("event_ids")
    try:
        event_ids = [int(x) for x in raw_ids if x.isdigit()]
    except ValueError:
        abort(400)

    if not event_ids:
        flash("Žádné akce nebyly vybrány.", "warning")
        return redirect(url_for("events.index"))

    changed = 0
    skipped = 0

    for eid in event_ids:
        event = db.session.get(Event, eid)
        if event is None or event.status not in valid_from:
            skipped += 1
            continue
        prev_status = event.status.value
        event.status = target_status
        if target_status == EventStatus.CANCELLED:
            event.archived = True
        event.version += 1
        _audit(
            "status_change",
            event,
            f"Hromadná akce: stav akce '{event.name}' změněn na '{target_status.value}'",
            {"before": {"status": prev_status}, "after": {"status": target_status.value}},
        )
        changed += 1

    db.session.commit()

    msg = f"Změněno {changed} akcí."
    if skipped:
        msg += f" Přeskočeno {skipped} (nevhodný stav nebo nenalezeno)."
    flash(msg, "success" if changed else "warning")
    return redirect(url_for("events.index"))


@events_bp.post("/<int:event_id>/spots/add")
@login_required
def add_spot(event_id: int) -> Response:
    if not current_user.has_permission("event.edit"):
        abort(403)
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    description = request.form.get("description", "").strip() or None
    is_optional = request.form.get("is_optional") == "1"
    try:
        quantity = max(1, min(10, int(request.form.get("quantity", 1))))
    except (ValueError, TypeError):
        quantity = 1
    qual_ids = [int(c) for c in request.form.getlist("qualification_ids") if c.isdigit()]
    qualifications = db.session.scalars(
        db.select(Qualification).where(Qualification.id.in_(qual_ids))
    ).all() if qual_ids else []

    for _ in range(quantity):
        spot = EventSpot(event_id=event_id, description=description, is_optional=is_optional)
        spot.required_qualifications = list(qualifications)
        db.session.add(spot)

    event.version += 1
    opt_flag = " (volitelná)" if is_optional else ""
    qual_names = ", ".join(c.name for c in qualifications) if qualifications else "žádná"
    _audit("edit", event, f"Přidáno {quantity}× pozice '{description or '—'}'{opt_flag} (kvalifikace: {qual_names})")
    db.session.commit()

    flash(f"{'Pozice přidány' if quantity > 1 else 'Místo přidáno'}.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events_bp.post("/<int:event_id>/spots/<int:spot_id>/edit")
@login_required
def edit_spot(event_id: int, spot_id: int) -> Response:
    if not current_user.has_permission("event.edit"):
        abort(403)
    spot = db.session.get(EventSpot, spot_id)
    if spot is None or spot.event_id != event_id:
        abort(404)
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    description = request.form.get("description", "").strip() or None
    qual_ids = [int(c) for c in request.form.getlist("qualification_ids") if c.isdigit()]
    qualifications = db.session.scalars(
        db.select(Qualification).where(Qualification.id.in_(qual_ids))
    ).all() if qual_ids else []
    confirm_unassign = request.form.get("confirm_unassign") == "1"

    # Check if the assigned user would become ineligible under the new credentials
    unassign_needed = False
    if spot.assignment:
        assigned_user = spot.assignment.user
        # Temporarily simulate new creds to check eligibility
        old_creds = spot.required_qualifications
        spot.required_qualifications = list(qualifications)
        if not spot.is_eligible(assigned_user):  # type: ignore[arg-type]
            if not confirm_unassign:
                spot.required_qualifications = old_creds
                flash(
                    "Pozice nezměněna! Změna kvalifikací pro tuto pozici vyžaduje zaškrtnutí "
                    "potvrzovacího políčka ve formuláři úpravy pozice, protože je na pozici "
                    f"přihlášen uživatel {assigned_user.name}, který nesplňuje nové požadavky.",
                    "warning",
                )
                return redirect(url_for("events.detail", event_id=event_id) + f"#edit-spot-{spot_id}")
            unassign_needed = True
        else:
            spot.required_qualifications = old_creds  # reset — will be set properly below

    spot.description = description
    spot.is_optional = request.form.get("is_optional") == "1"
    spot.required_qualifications = list(qualifications)
    event.version += 1
    opt_flag = " (volitelná)" if spot.is_optional else ""
    qual_names = ", ".join(c.name for c in qualifications) if qualifications else "žádná"
    _audit("edit", event, f"Upravena pozice '{description or '—'}'{opt_flag} (kvalifikace: {qual_names})")

    if unassign_needed:
        assignment = spot.assignment
        unassigned_user = assignment.user
        db.session.add(AuditLogEntry(
            actor_id=current_user.id,
            action_type="delete",
            entity_type="Assignment",
            entity_id=str(assignment.id),
            summary=f"Uživatel '{unassigned_user.name}' automaticky odhlášen — nesplňuje nové požadavky pozice",
        ))
        db.session.delete(assignment)
        db.session.flush()

    db.session.commit()

    if unassign_needed:
        mailer.send_assignment_released(unassigned_user.email, unassigned_user.name, event)
        flash(f"Pozice upravena. Uživatel {unassigned_user.name} byl automaticky odhlášen.", "warning")
    else:
        flash("Pozice upravena.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events_bp.post("/<int:event_id>/spots/<int:spot_id>/delete")
@login_required
def delete_spot(event_id: int, spot_id: int) -> Response:
    if not current_user.has_permission("event.edit"):
        abort(403)
    spot = db.session.get(EventSpot, spot_id)
    if spot is None or spot.event_id != event_id:
        abort(404)
    if spot.assignment is not None:
        flash("Obsazenou pozici nelze smazat.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    db.session.delete(spot)
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    event.version += 1
    _audit("edit", event, f"Odstraněna pozice z akce '{event.name}'")
    db.session.commit()

    flash("Místo odstraněno.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_event_form(form: dict, existing: Event | None = None) -> tuple[Event | None, str | None]:
    """Parse the event form and return (event, error_message).

    All datetime inputs are interpreted as Europe/Prague local time and stored
    as UTC in the database.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
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
    )
    return event, None


def _build_spots(event: Event, form: dict) -> None:
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
            db.select(Qualification).where(Qualification.id.in_(qual_ids))
        ).all() if qual_ids else []
        spot = EventSpot(event_id=event.id, description=description, is_optional=is_optional)
        spot.required_qualifications = list(qualifications)
        db.session.add(spot)


def _build_spots_from_template(event: Event, template: object) -> None:
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


# ── Event Equipment: Plan ─────────────────────────────────────────────────────

@events_bp.post("/<int:event_id>/equipment/plan")
@login_required
def equipment_plan_add(event_id: int) -> Response:
    if not current_user.has_permission("event.equipment.plan"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.status == EventStatus.CANCELLED:
        flash("Zrušeným akcím nelze plánovat vybavení.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    type_id = request.form.get("type_id", type=int)
    quantity = request.form.get("quantity", 1, type=int)
    if not type_id or quantity < 1:
        flash("Zadejte platný typ a množství.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    et = db.session.get(EquipmentType, type_id)
    if et is None:
        abort(404)

    existing = db.session.get(EventEquipmentPlan, (event_id, type_id))
    if existing:
        existing.quantity_required = quantity
    else:
        db.session.add(EventEquipmentPlan(
            event_id=event_id,
            equipment_type_id=type_id,
            quantity_required=quantity,
        ))

    _audit("edit", event, f"Plán vybavení akce '{event.name}': {et.name} × {quantity}")
    db.session.commit()

    flash("Plán vybavení byl aktualizován.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events_bp.post("/<int:event_id>/equipment/plan/remove")
@login_required
def equipment_plan_remove(event_id: int) -> Response:
    if not current_user.has_permission("event.equipment.plan"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    type_id = request.form.get("type_id", type=int)
    if not type_id:
        flash("Chybí typ vybavení.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    plan = db.session.get(EventEquipmentPlan, (event_id, type_id))
    if plan:
        db.session.delete(plan)
        _audit("edit", event, f"Odstraněn typ vybavení z plánu akce '{event.name}'")
        db.session.commit()

    flash("Plán vybavení byl aktualizován.", "success")
    return redirect(url_for("events.detail", event_id=event_id))


# ── Event Equipment: Assignments ──────────────────────────────────────────────

@events_bp.post("/<int:event_id>/equipment/assign")
@login_required
def equipment_assign(event_id: int) -> Response:
    if not current_user.has_permission("event.equipment.assign"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if event.status == EventStatus.CANCELLED:
        flash("Zrušeným akcím nelze přiřazovat vybavení.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    item_id = request.form.get("item_id", type=int)
    if not item_id:
        flash("Vyberte položku vybavení.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    item = db.session.get(EquipmentItem, item_id)
    if item is None:
        abort(404)

    existing = db.session.scalar(
        db.select(EventEquipmentAssignment).where(
            EventEquipmentAssignment.event_id == event_id,
            EventEquipmentAssignment.equipment_item_id == item_id,
        )
    )
    if existing:
        flash("Tato položka je k akci již přiřazena.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    assignment = EventEquipmentAssignment(event_id=event_id, equipment_item_id=item_id)
    db.session.add(assignment)
    _audit("edit", event, f"Přiřazena položka vybavení '{item.name}' k akci '{event.name}'")
    db.session.commit()

    flash(f'Položka „{item.name}" byla přiřazena k akci.', "success")
    return redirect(url_for("events.detail", event_id=event_id))


@events_bp.post("/<int:event_id>/equipment/unassign")
@login_required
def equipment_unassign(event_id: int) -> Response:
    if not current_user.has_permission("event.equipment.assign"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    item_id = request.form.get("item_id", type=int)
    if not item_id:
        flash("Chybí položka vybavení.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    assignment = db.session.scalar(
        db.select(EventEquipmentAssignment).where(
            EventEquipmentAssignment.event_id == event_id,
            EventEquipmentAssignment.equipment_item_id == item_id,
        )
    )
    if assignment is None:
        flash("Přiřazení nenalezeno.", "danger")
        return redirect(url_for("events.detail", event_id=event_id))

    item = db.session.get(EquipmentItem, item_id)
    db.session.delete(assignment)
    _audit("edit", event, f"Vrácena položka vybavení '{item.name if item else item_id}' z akce '{event.name}'")
    db.session.commit()

    flash("Položka vybavení byla vrácena.", "success")
    return redirect(url_for("events.detail", event_id=event_id))
