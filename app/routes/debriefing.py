"""
Debriefing blueprint — post-event feedback submitted per assignment.

A debriefing record captures confidential feedback from each participant
after an event is completed. Only users with debriefing.view_all
(Debriefing Manager role) may read confidential responses.

The responsible person (RP) additionally updates the event with actual
start/end times and the count of patients treated (počet ošetřených).

Submission is final — records cannot be edited once submitted.

Routes:
  GET/POST /debriefing/<assignment_id>  — submit debriefing (own only)
  GET      /debriefing/manage           — list all records (Debriefing Manager)
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, Response, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.event import Event, EventStatus
from app.models.assignment import Assignment, DebriefingRecord
from app.utils import audit, diff_changes, get_or_404, require_permission

debriefing_bp = Blueprint("debriefing", __name__, url_prefix="/debriefing")


# ── Submit a debriefing ───────────────────────────────────────────────────────

def _parse_grade(raw: str) -> tuple[int, str | None]:
    """Validate the 1–5 grade. Return (grade, error_message)."""
    try:
        grade = int(raw)
    except ValueError:
        return 0, "Hodnocení musí být číslo od 1 do 5."
    if grade not in range(1, 6):
        return 0, "Hodnocení musí být číslo od 1 do 5."
    return grade, None


def _parse_rp_actuals(form: dict) -> tuple[datetime | None, datetime | None, int | None, list[str]]:
    """Parse and validate the RP-only actual start/end and patients count.

    Returns (actual_start_utc, actual_end_utc, patients_count, errors).
    """
    from zoneinfo import ZoneInfo
    from app.models.settings import get_settings

    settings = get_settings()
    tz_name = settings.timezone if settings else "Europe/Prague"
    tz = ZoneInfo(tz_name)

    errors: list[str] = []
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    patients_count: int | None = None

    try:
        actual_start = datetime.fromisoformat(
            form.get("actual_start_datetime", "").strip()
        ).replace(tzinfo=tz).astimezone(timezone.utc)
    except (ValueError, TypeError):
        errors.append("Zadejte platný skutečný čas začátku.")

    try:
        actual_end = datetime.fromisoformat(
            form.get("actual_end_datetime", "").strip()
        ).replace(tzinfo=tz).astimezone(timezone.utc)
    except (ValueError, TypeError):
        errors.append("Zadejte platný skutečný čas konce.")

    if actual_start and actual_end and actual_end <= actual_start:
        errors.append("Čas konce musí být po čase začátku.")

    try:
        patients_count = int(form.get("patients_count", "").strip())
        if patients_count < 0 or patients_count > 999:
            raise ValueError
    except ValueError:
        errors.append("Počet ošetřených musí být celé číslo (0 nebo více).")

    return actual_start, actual_end, patients_count, errors


def _apply_rp_actuals_to_event(
    event: Event, actual_start: datetime, actual_end: datetime, patients_count: int,
) -> None:
    """Update event with RP-supplied actuals and write an audit entry."""
    before = {
        "actual_start_datetime": str(event.actual_start_datetime),
        "actual_end_datetime": str(event.actual_end_datetime),
        "patients_count": event.patients_count,
    }
    event.actual_start_datetime = actual_start
    event.actual_end_datetime = actual_end
    event.patients_count = patients_count
    event.version += 1
    audit("edit", "Event", str(event.id),
          f"Aktuální časy a počet ošetřených aktualizovány pro akci '{event.name}'",
          diff_changes(before, {
              "actual_start_datetime": str(actual_start),
              "actual_end_datetime": str(actual_end),
              "patients_count": patients_count,
          }))


@debriefing_bp.route("/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def submit(assignment_id: int) -> str | Response:
    assignment = get_or_404(Assignment, assignment_id)
    event: Event = assignment.spot.event

    # Only the assigned user may submit their own debriefing
    if assignment.user_id != current_user.id:
        abort(403)

    # Debriefing only allowed after event is Completed
    if event.status != EventStatus.COMPLETED:
        flash("Debriefing lze vyplnit až po dokončení akce.", "warning")
        return redirect(url_for("events.detail", event_id=event.id))

    # Submission is final — show read-only view if already submitted
    if assignment.debriefing is not None:
        return render_template(
            "debriefing/submitted.html",
            assignment=assignment,
            event=event,
            record=assignment.debriefing,
        )

    is_rp = event.responsible_person_id == current_user.id

    if request.method != "POST":
        return render_template(
            "debriefing/submit.html", assignment=assignment, event=event, is_rp=is_rp,
        )

    # ── Validate ──────────────────────────────────────────────────────────────
    errors: list[str] = []
    grade, grade_err = _parse_grade(request.form.get("grade", "").strip())
    if grade_err:
        errors.append(grade_err)

    feedback_event = request.form.get("feedback_event", "").strip() or None
    feedback_customer = request.form.get("feedback_customer", "").strip() or None
    feedback_colleagues = request.form.get("feedback_colleagues", "").strip() or None

    actual_start: datetime | None = None
    actual_end: datetime | None = None
    patients_count: int | None = None
    if is_rp:
        actual_start, actual_end, patients_count, rp_errors = _parse_rp_actuals(request.form)
        errors.extend(rp_errors)

    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template(
            "debriefing/submit.html", assignment=assignment, event=event, is_rp=is_rp,
        )

    # ── Persist confidential record ───────────────────────────────────────────
    record = DebriefingRecord(
        assignment_id=assignment_id,
        submitted_by_id=current_user.id,
        grade=grade,
        feedback_event=feedback_event,
        feedback_customer=feedback_customer,
        feedback_colleagues=feedback_colleagues,
    )
    db.session.add(record)
    db.session.flush()
    audit("create", "DebriefingRecord", str(record.id),
          f"Debriefing odevzdán pro akci '{event.name}'")

    if is_rp and actual_start and actual_end and patients_count is not None:
        _apply_rp_actuals_to_event(event, actual_start, actual_end, patients_count)

    db.session.commit()
    flash("Debriefing byl úspěšně odevzdán. Děkujeme.", "success")
    return redirect(url_for("events.detail", event_id=event.id))


# ── Debriefing management (Debriefing Manager only) ───────────────────────────

@debriefing_bp.get("/manage")
@login_required
def manage() -> str:
    require_permission("debriefing.view_all")

    # Load all completed events that have at least one assignment
    events_with_debriefings = db.session.scalars(
        db.select(Event)
        .where(Event.status == EventStatus.COMPLETED)
        .order_by(Event.start_datetime.desc())
    ).all()

    return render_template(
        "debriefing/manage.html",
        events=events_with_debriefings,
    )


# ── Event debriefing detail (Debriefing Manager only) ─────────────────────────

@debriefing_bp.get("/event/<int:event_id>")
@login_required
def event_overview(event_id: int) -> str:
    require_permission("debriefing.view_all")

    event = get_or_404(Event, event_id)

    assignments = [s.assignment for s in event.spots if s.assignment is not None]
    return render_template("debriefing/event_overview.html", event=event, assignments=assignments)
