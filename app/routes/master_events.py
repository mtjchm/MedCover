"""
Master Event CRUD blueprint.

Permissions:
  master_event.view    — list + detail
  master_event.create  — create
  master_event.edit    — edit
  master_event.archive / master_event.unarchive — archive toggle
"""

from __future__ import annotations

from flask import Blueprint, Response, render_template, redirect, url_for, flash, request
from flask_login import login_required

from app.extensions import db
from app.models.master_event import MasterEvent
from app.utils import RECORD_MODIFIED_MSG, audit, check_version_conflict, diff_changes, get_or_404, require_permission
from app.queries import active_users_list

master_events_bp = Blueprint("master_events", __name__, url_prefix="/master-events")


# ── List ─────────────────────────────────────────────────────────────────────

@master_events_bp.get("/")
@login_required
def index() -> str:
    require_permission("master_event.view")

    show_archived = request.args.get("archived") == "1"
    query = db.select(MasterEvent)
    if not show_archived:
        query = query.where(MasterEvent.archived.is_(False))
    query = query.order_by(MasterEvent.is_general.desc(), MasterEvent.name)
    master_events = db.session.scalars(query).all()

    return render_template(
        "master_events/index.html",
        master_events=master_events,
        show_archived=show_archived,
    )


# ── Create ────────────────────────────────────────────────────────────────────

@master_events_bp.route("/create", methods=["GET", "POST"])
@login_required
def create() -> str | Response:
    require_permission("master_event.create")

    coordinators = active_users_list()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        coordinator_id = request.form.get("coordinator_id") or None

        if not name:
            flash("Název nadřazené akce je povinný.", "danger")
            return render_template("master_events/create.html", coordinators=coordinators)

        if db.session.scalar(db.select(MasterEvent).where(MasterEvent.name == name)):
            flash("Nadřazená akce s tímto názvem již existuje.", "danger")
            return render_template("master_events/create.html", coordinators=coordinators)

        me = MasterEvent(
            name=name,
            description=description,
            coordinator_id=coordinator_id,
        )
        db.session.add(me)
        db.session.flush()
        audit("create", "MasterEvent", me.id, f"Vytvořena nadřazená akce '{me.name}'")
        db.session.commit()

        flash(f'Nadřazená akce „{me.name}" byla vytvořena.',  'success')
        return redirect(url_for("master_events.detail", me_id=me.id))

    return render_template("master_events/create.html", coordinators=coordinators)


# ── Detail ────────────────────────────────────────────────────────────────────

@master_events_bp.get("/<int:me_id>")
@login_required
def detail(me_id: int) -> str:
    require_permission("master_event.view")

    me = get_or_404(MasterEvent, me_id)

    from app.models.event import Event, EventStatus
    events = db.session.scalars(
        db.select(Event).where(Event.master_event_id == me_id).order_by(Event.start_datetime.desc())
    ).all()

    stats = {
        "total": len(events),
        "draft": sum(1 for e in events if e.status == EventStatus.DRAFT),
        "published": sum(1 for e in events if e.status == EventStatus.PUBLISHED),
        "assignments_open": sum(1 for e in events if e.status == EventStatus.ASSIGNMENTS_OPEN),
        "assignments_closed": sum(1 for e in events if e.status == EventStatus.ASSIGNMENTS_CLOSED),
        "completed": sum(1 for e in events if e.status == EventStatus.COMPLETED),
        "cancelled": sum(1 for e in events if e.status == EventStatus.CANCELLED),
    }

    return render_template("master_events/detail.html", me=me, events=events, stats=stats)


# ── Edit ──────────────────────────────────────────────────────────────────────

@master_events_bp.route("/<int:me_id>/edit", methods=["GET", "POST"])
@login_required
def edit(me_id: int) -> str | Response:
    require_permission("master_event.edit")

    me = get_or_404(MasterEvent, me_id)

    coordinators = active_users_list()

    if request.method == "POST":
        if check_version_conflict(me, request.form.get("version")):
            flash(RECORD_MODIFIED_MSG, "danger")
            return render_template("master_events/edit.html", me=me, coordinators=coordinators)

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        coordinator_id = request.form.get("coordinator_id") or None

        if not name:
            flash("Název nadřazené akce je povinný.", "danger")
            return render_template("master_events/edit.html", me=me, coordinators=coordinators)

        conflict = db.session.scalar(
            db.select(MasterEvent).where(MasterEvent.name == name, MasterEvent.id != me_id)
        )
        if conflict:
            flash("Nadřazená akce s tímto názvem již existuje.", "danger")
            return render_template("master_events/edit.html", me=me, coordinators=coordinators)

        before = {"name": me.name, "description": me.description, "coordinator_id": str(me.coordinator_id)}
        me.name = name
        me.description = description
        me.coordinator_id = coordinator_id
        me.version += 1

        audit("edit", "MasterEvent", me.id, f"Upraven záznam nadřazené akce '{me.name}'", diff_changes(
            before,
            {"name": me.name, "description": me.description, "coordinator_id": str(me.coordinator_id)},
        ))

        db.session.commit()

        flash(f'Nadřazená akce „{me.name}" byla uložena.',  'success')
        return redirect(url_for("master_events.detail", me_id=me.id))

    return render_template("master_events/edit.html", me=me, coordinators=coordinators)


# ── Archive / Unarchive ───────────────────────────────────────────────────────

@master_events_bp.post("/<int:me_id>/archive")
@login_required
def archive(me_id: int) -> Response:
    require_permission("master_event.archive")

    me = get_or_404(MasterEvent, me_id)
    if me.is_general:
        flash("Výchozí nadřazenou akci nelze archivovat.", "danger")
        return redirect(url_for("master_events.detail", me_id=me_id))

    me.archived = True
    me.version += 1
    audit("archive", "MasterEvent", me.id, f"Nadřazená akce '{me.name}' byla archivována")
    db.session.commit()

    flash(f'Nadřazená akce „{me.name}" byla archivována.',  'success')
    return redirect(url_for("master_events.index"))


@master_events_bp.post("/<int:me_id>/unarchive")
@login_required
def unarchive(me_id: int) -> Response:
    require_permission("master_event.unarchive")

    me = get_or_404(MasterEvent, me_id)

    me.archived = False
    me.version += 1
    audit("unarchive", "MasterEvent", me.id, f"Nadřazená akce '{me.name}' byla obnovena z archivu")
    db.session.commit()

    flash(f'Nadřazená akce „{me.name}" byla obnovena z archivu.',  'success')
    return redirect(url_for("master_events.detail", me_id=me_id))
