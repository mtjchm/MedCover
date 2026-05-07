"""
Reports & Statistics blueprint.

Routes:
  GET /reports/                          — index (three report cards)
  GET /reports/user/<user_id>            — per-user report
  GET /reports/master-event/<me_id>      — per-master-event report
  GET /reports/date-range                — date-range report (form + results)

Permission: report.view  (users may always view their own per-user report)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.assignment import Assignment
from app.models.event import Event, EventSpot, EventStatus
from app.models.master_event import MasterEvent
from app.models.user import UserAccount

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


# ── Index ─────────────────────────────────────────────────────────────────────

@reports_bp.get("/")
@login_required
def index() -> str:
    if not current_user.has_permission("report.view"):
        abort(403)
    return render_template("reports/index.html")


# ── Per-user report ───────────────────────────────────────────────────────────

@reports_bp.get("/user/<uuid:user_id>")
@login_required
def user_report(user_id: uuid.UUID) -> str:
    is_own = str(user_id) == str(current_user.id)
    if not is_own and not current_user.has_permission("report.view"):
        abort(403)

    user: UserAccount | None = db.session.get(UserAccount, user_id)
    if user is None:
        abort(404)

    # Load all assignments for this user with eager-loaded spot → event and debriefing
    assignments = list(db.session.scalars(
        db.select(Assignment)
        .where(Assignment.user_id == user_id)
        .options(
            selectinload(Assignment.spot).selectinload(EventSpot.event),  # type: ignore[arg-type]
            selectinload(Assignment.debriefing),
        )
        .order_by(Assignment.assigned_at)
    ).unique().all())

    # Build per-event rows
    rows = []
    total_planned_seconds = 0
    total_actual_hours = Decimal("0")
    total_patients = 0
    completed_count = 0

    for asgn in assignments:
        spot = asgn.spot
        if spot is None:
            continue
        event = spot.event
        if event is None:
            continue

        planned_seconds = int((event.end_datetime - event.start_datetime).total_seconds())
        planned_hours = planned_seconds / 3600

        debrief = asgn.debriefing
        actual_h = debrief.actual_hours if debrief else None
        patients = debrief.patients_treated if debrief else None

        rows.append({
            "event": event,
            "planned_hours": planned_hours,
            "actual_hours": actual_h,
            "patients_treated": patients,
        })

        if event.status == EventStatus.COMPLETED:
            completed_count += 1
            total_planned_seconds += planned_seconds
            if actual_h is not None:
                total_actual_hours += actual_h
            if patients is not None:
                total_patients += patients

    total_planned_hours = total_planned_seconds / 3600

    return render_template(
        "reports/user_report.html",
        report_user=user,
        rows=rows,
        total_planned_hours=total_planned_hours,
        total_actual_hours=total_actual_hours,
        total_patients=total_patients,
        completed_count=completed_count,
        is_own=is_own,
    )


# ── Per-Master-Event report ───────────────────────────────────────────────────

@reports_bp.get("/master-event/<int:me_id>")
@login_required
def me_report(me_id: int) -> str:
    if not current_user.has_permission("report.view"):
        abort(403)

    master_event: MasterEvent | None = db.session.get(MasterEvent, me_id)
    if master_event is None:
        abort(404)

    events: list[Event] = list(db.session.scalars(
        db.select(Event)
        .where(Event.master_event_id == me_id)
        .options(
            selectinload(Event.spots).selectinload(EventSpot.assignment).selectinload(Assignment.debriefing)  # type: ignore[arg-type]
        )
        .order_by(Event.start_datetime)
    ).all())

    # Count events by status
    status_counts: dict[str, int] = {}
    for ev in events:
        key = ev.status.value
        status_counts[key] = status_counts.get(key, 0) + 1

    # Build per-event rows
    rows = []
    grand_total_spots = 0
    grand_filled_spots = 0
    grand_worked_hours = Decimal("0")
    grand_patients = 0

    for ev in events:
        total_spots = len(ev.spots)
        filled_spots = sum(1 for s in ev.spots if s.assignment is not None)
        worked_hours = Decimal("0")
        patients = 0
        for spot in ev.spots:
            if spot.assignment and spot.assignment.debriefing:
                worked_hours += spot.assignment.debriefing.actual_hours
                patients += spot.assignment.debriefing.patients_treated

        rows.append({
            "event": ev,
            "total_spots": total_spots,
            "filled_spots": filled_spots,
            "worked_hours": worked_hours,
            "patients": patients,
        })

        grand_total_spots += total_spots
        grand_filled_spots += filled_spots
        grand_worked_hours += worked_hours
        grand_patients += patients

    return render_template(
        "reports/me_report.html",
        master_event=master_event,
        events=events,
        rows=rows,
        status_counts=status_counts,
        grand_total_spots=grand_total_spots,
        grand_filled_spots=grand_filled_spots,
        grand_worked_hours=grand_worked_hours,
        grand_patients=grand_patients,
    )


# ── Date-range report ─────────────────────────────────────────────────────────

@reports_bp.get("/date-range")
@login_required
def date_range_report() -> str:
    if not current_user.has_permission("report.view"):
        abort(403)

    from_date_str = request.args.get("from_date", "").strip()
    to_date_str = request.args.get("to_date", "").strip()

    if not from_date_str or not to_date_str:
        return render_template("reports/date_range.html", results=None, from_date=from_date_str, to_date=to_date_str)

    try:
        from_dt = datetime.strptime(from_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        to_dt = datetime.strptime(to_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    except ValueError:
        return render_template("reports/date_range.html", results=None, from_date=from_date_str, to_date=to_date_str, error="Neplatný formát data.")

    events: list[Event] = list(db.session.scalars(
        db.select(Event)
        .where(Event.start_datetime >= from_dt)
        .where(Event.start_datetime < to_dt)
        .options(
            selectinload(Event.master_event),  # type: ignore[arg-type]
            selectinload(Event.spots).selectinload(EventSpot.assignment).selectinload(Assignment.debriefing),  # type: ignore[arg-type]
        )
        .order_by(Event.start_datetime)
    ).unique().all())

    # Group by master event
    me_map: dict[int, dict] = {}
    for ev in events:
        me_id_key = ev.master_event_id
        if me_id_key not in me_map:
            me_map[me_id_key] = {
                "master_event": ev.master_event,
                "events": [],
            }
        me_map[me_id_key]["events"].append(ev)

    # Aggregate totals
    status_counts: dict[str, int] = {}
    total_spots = 0
    filled_spots = 0
    total_worked_hours = Decimal("0")
    total_patients = 0

    for ev in events:
        key = ev.status.value
        status_counts[key] = status_counts.get(key, 0) + 1
        total_spots += len(ev.spots)
        filled_spots += sum(1 for s in ev.spots if s.assignment is not None)
        for spot in ev.spots:
            if spot.assignment and spot.assignment.debriefing:
                total_worked_hours += spot.assignment.debriefing.actual_hours
                total_patients += spot.assignment.debriefing.patients_treated

    results = {
        "me_groups": list(me_map.values()),
        "status_counts": status_counts,
        "total_events": len(events),
        "total_spots": total_spots,
        "filled_spots": filled_spots,
        "total_worked_hours": total_worked_hours,
        "total_patients": total_patients,
    }

    return render_template(
        "reports/date_range.html",
        results=results,
        from_date=from_date_str,
        to_date=to_date_str,
    )
