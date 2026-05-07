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
from app.models.event import Event, EventSpot, EventStatus
from app.models.master_event import MasterEvent
from app.models.user import UserAccount
from app.models.audit import AuditLogEntry
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
    return render_template("events/index.html", events=events, show_archived=show_archived, EventStatus=EventStatus)


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
                "filled": e.filled_spots,
                "total": e.total_spots,
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

    if request.method == "POST":
        event, error = _parse_event_form(request.form)
        if error or event is None:
            flash(error or "Chyba formuláře.", "danger")
            return render_template("events/create.html", master_events=master_events, users=users)

        db.session.add(event)
        db.session.flush()
        _build_spots(event, request.form)
        _audit("create", event, f"Vytvořena akce '{event.name}'")
        db.session.commit()

        flash("Akce byla vytvořena.", "success")
        return redirect(url_for("events.detail", event_id=event.id))

    return render_template("events/create.html", master_events=master_events, users=users)


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

    return render_template("events/detail.html", event=event, EventStatus=EventStatus, eligible_users=eligible_users)


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

        updated, error = _parse_event_form(request.form, existing=event)
        if error:
            flash(error, "danger")
            return render_template("events/edit.html", event=event, master_events=master_events, users=users)

        event.version += 1
        _audit("edit", event, f"Upravena akce '{event.name}'")
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


# ── Spot management ───────────────────────────────────────────────────────────

@events_bp.post("/<int:event_id>/spots/add")
@login_required
def add_spot(event_id: int) -> Response:
    if not current_user.has_permission("event.edit"):
        abort(403)
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    description = request.form.get("description", "").strip() or None
    spot = EventSpot(event_id=event_id, description=description)
    db.session.add(spot)
    event.version += 1
    _audit("edit", event, f"Přidána pozice k akci '{event.name}'")
    db.session.commit()

    flash("Místo přidáno.", "success")
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
    """Create spots from spot_count field."""
    spot_count = int(form.get("spot_count", 0) or 0)
    for _ in range(spot_count):
        db.session.add(EventSpot(event_id=event.id))
