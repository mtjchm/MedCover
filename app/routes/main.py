from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, render_template
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.extensions import db
from app.models.event import Event, EventSpot, EventStatus
from app.models.assignment import Assignment
from app.models.user import UserAccount

main_bp = Blueprint("main", __name__)


@main_bp.get("/health")
def health() -> tuple[Response, int]:
    """Liveness + readiness probe. Returns 200 if DB is reachable, 503 otherwise."""
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 503


@main_bp.route("/dashboard")
@login_required
def dashboard() -> str:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=current_user.dashboard_horizon_days)

    # ── Moje akce ─────────────────────────────────────────────────────────
    # Events where user is: assigned to a spot, RP, or creator — within horizon
    assigned_event_ids = db.session.scalars(
        db.select(EventSpot.event_id)
        .join(Assignment, Assignment.spot_id == EventSpot.id)
        .where(Assignment.user_id == current_user.id)
    ).all()

    my_events_query = (
        db.select(Event)
        .where(
            Event.end_datetime >= now,
            Event.start_datetime <= horizon,
            Event.status != EventStatus.CANCELLED,
            or_(
                Event.id.in_(assigned_event_ids),
                Event.responsible_person_id == current_user.id,
                Event.created_by_id == current_user.id,
            ),
        )
        .order_by(Event.start_datetime)
    )
    # Users without view_draft cannot open DRAFT events — exclude them to avoid 403
    if not current_user.has_permission("event.view_draft"):
        my_events_query = my_events_query.where(Event.status != EventStatus.DRAFT)
    my_events_raw = db.session.scalars(my_events_query).all()

    # Build (event, [tags]) pairs
    my_events: list[tuple[Event, list[str]]] = []
    for e in my_events_raw:
        tags = []
        if e.id in assigned_event_ids:
            tags.append("Přihlášen")
        if e.responsible_person_id == current_user.id:
            tags.append("Zodpovědný zdravotník")
        if e.created_by_id == current_user.id:
            tags.append("Koordinátor")
        my_events.append((e, tags))

    # ── Otevřené přihlášky — eligible ────────────────────────────────────
    open_events: list[Event] = []
    open_events_all: list[Event] = []

    if current_user.has_permission("event.assign_own"):
        already_in = set(assigned_event_ids)
        candidates = db.session.scalars(
            db.select(Event)
            .where(
                Event.status == EventStatus.ASSIGNMENTS_OPEN,
                Event.start_datetime <= horizon,
                Event.end_datetime >= now,
                Event.id.notin_(already_in),
            )
            .order_by(Event.start_datetime)
        ).all()

        for e in candidates:
            has_free = any(s.assignment is None and s.is_eligible(current_user) for s in e.spots)
            if has_free:
                open_events.append(e)

        open_events_all = [
            e for e in candidates
            if any(s.assignment is None for s in e.spots)
        ]

    # ── Koordinátor: vyžaduje pozornost ───────────────────────────────────
    attention_events: list[Event] = []
    if current_user.has_any_permission("event.publish", "event.assignments.open"):
        attention_events = list(db.session.scalars(
            db.select(Event)
            .where(
                Event.archived == False,  # noqa: E712
                Event.status.in_([EventStatus.DRAFT, EventStatus.PUBLISHED, EventStatus.ASSIGNMENTS_OPEN]),
                Event.start_datetime <= horizon,
                Event.end_datetime >= now,
            )
            .order_by(Event.start_datetime)
        ).all())

        # Filter to understaffed or needs-action events
        attention_events = [
            e for e in attention_events
            if e.status in (EventStatus.DRAFT, EventStatus.PUBLISHED)
            or (e.status == EventStatus.ASSIGNMENTS_OPEN and e.filled_spots < e.total_spots)
        ]

    # ── Admin: čekající aktivace ──────────────────────────────────────────
    pending_activations: list[UserAccount] = []
    if current_user.has_permission("user.activate"):
        pending_activations = list(db.session.scalars(
            db.select(UserAccount)
            .where(UserAccount.is_active == False)  # noqa: E712
            .order_by(UserAccount.created_at)
        ).all())

    return render_template(
        "main/dashboard.html",
        my_events=my_events,
        open_events=open_events,
        open_events_all=open_events_all,
        attention_events=attention_events,
        pending_activations=pending_activations,
        horizon_days=current_user.dashboard_horizon_days,
        EventStatus=EventStatus,
    )
