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
from app.models.audit import AuditLogEntry
from app.utils import diff_changes

debriefing_bp = Blueprint("debriefing", __name__, url_prefix="/debriefing")


def _audit(action: str, entity_type: str, entity_id: str, summary: str, changes: dict | None = None) -> None:
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        changes_json=changes,
    ))


# ── Submit a debriefing ───────────────────────────────────────────────────────

@debriefing_bp.route("/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def submit(assignment_id: int) -> str | Response:
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None:
        abort(404)

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

    if request.method == "POST":
        errors: list[str] = []

        # ── Confidential section (mandatory) ──────────────────────────────────
        grade_raw = request.form.get("grade", "").strip()
        try:
            grade = int(grade_raw)
            if grade not in range(1, 6):
                raise ValueError
        except ValueError:
            errors.append("Hodnocení musí být číslo od 1 do 5.")
            grade = 0

        feedback_event = request.form.get("feedback_event", "").strip() or None
        feedback_customer = request.form.get("feedback_customer", "").strip() or None
        feedback_colleagues = request.form.get("feedback_colleagues", "").strip() or None

        # ── RP section (responsible person only) ─────────────────────────────
        actual_start: datetime | None = None
        actual_end: datetime | None = None
        patients_count: int | None = None

        if is_rp:
            from zoneinfo import ZoneInfo
            from app.models.settings import get_settings
            tz_name = (get_settings() or type("_", (), {"timezone": "Europe/Prague"})()).timezone  # type: ignore[union-attr]
            tz = ZoneInfo(tz_name)

            start_raw = request.form.get("actual_start_datetime", "").strip()
            end_raw = request.form.get("actual_end_datetime", "").strip()
            patients_raw = request.form.get("patients_count", "").strip()

            try:
                actual_start = datetime.fromisoformat(start_raw).replace(tzinfo=tz).astimezone(timezone.utc)
            except (ValueError, TypeError):
                errors.append("Zadejte platný skutečný čas začátku.")

            try:
                actual_end = datetime.fromisoformat(end_raw).replace(tzinfo=tz).astimezone(timezone.utc)
            except (ValueError, TypeError):
                errors.append("Zadejte platný skutečný čas konce.")

            if actual_start and actual_end and actual_end <= actual_start:
                errors.append("Čas konce musí být po čase začátku.")

            try:
                patients_count = int(patients_raw)
                if patients_count < 0 or patients_count > 999:
                    raise ValueError
            except ValueError:
                errors.append("Počet ošetřených musí být celé číslo (0 nebo více).")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "debriefing/submit.html",
                assignment=assignment,
                event=event,
                is_rp=is_rp,
            )

        # ── Persist confidential record ───────────────────────────────────────
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
        _audit("create", "DebriefingRecord", str(record.id),
               f"Debriefing odevzdán pro akci '{event.name}'")

        # ── Persist RP event actuals ──────────────────────────────────────────
        if is_rp and actual_start and actual_end and patients_count is not None:
            before = {
                "actual_start_datetime": str(event.actual_start_datetime),
                "actual_end_datetime": str(event.actual_end_datetime),
                "patients_count": event.patients_count,
            }
            event.actual_start_datetime = actual_start
            event.actual_end_datetime = actual_end
            event.patients_count = patients_count
            event.version += 1
            _audit("edit", "Event", str(event.id),
                   f"Aktuální časy a počet ošetřených aktualizovány pro akci '{event.name}'",
                   diff_changes(before, {
                       "actual_start_datetime": str(actual_start),
                       "actual_end_datetime": str(actual_end),
                       "patients_count": patients_count,
                   }))

        db.session.commit()
        flash("Debriefing byl úspěšně odevzdán. Děkujeme.", "success")
        return redirect(url_for("events.detail", event_id=event.id))

    return render_template(
        "debriefing/submit.html",
        assignment=assignment,
        event=event,
        is_rp=is_rp,
    )


# ── Debriefing management (Debriefing Manager only) ───────────────────────────

@debriefing_bp.get("/manage")
@login_required
def manage() -> str:
    if not current_user.has_permission("debriefing.view_all"):
        abort(403)

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
    if not current_user.has_permission("debriefing.view_all"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    assignments = [s.assignment for s in event.spots if s.assignment is not None]
    return render_template("debriefing/event_overview.html", event=event, assignments=assignments)
