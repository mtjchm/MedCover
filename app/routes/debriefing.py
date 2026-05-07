"""
Debriefing blueprint — post-event reports submitted per assignment.

A debriefing record captures actual hours worked, patients treated,
materials used, and optional feedback. It can be submitted by the
assigned user or a coordinator/admin after the event is Completed.

Routes:
  GET/POST /debriefing/<assignment_id>   — submit or view a debrief
  GET      /debriefing/event/<event_id>  — list all debriefs for an event (coordinator)
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.event import Event, EventStatus
from app.models.assignment import Assignment, DebriefingRecord
from app.models.audit import AuditLogEntry

debriefing_bp = Blueprint("debriefing", __name__, url_prefix="/debriefing")


def _audit(action: str, record: DebriefingRecord, summary: str) -> None:
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type=action,
        entity_type="DebriefingRecord",
        entity_id=str(record.id),
        summary=summary,
    ))


# ── Submit / view a single debriefing ─────────────────────────────────────────

@debriefing_bp.route("/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def submit(assignment_id: int):
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None:
        abort(404)

    event = db.session.get(Event, assignment.spot.event_id)

    # Access: own assignment OR coordinator/admin
    is_own = assignment.user_id == current_user.id
    is_coordinator = current_user.has_any_permission("event.edit", "event.assign_other")
    if not (is_own or is_coordinator):
        abort(403)

    # Debriefing only allowed after event is Completed
    if event.status != EventStatus.COMPLETED:
        flash("Hlášení lze vyplnit až po dokončení akce.", "warning")
        return redirect(url_for("events.detail", event_id=event.id))

    existing = assignment.debriefing

    if request.method == "POST":
        hours_raw = request.form.get("actual_hours", "").strip()
        patients_raw = request.form.get("patients_treated", "0").strip()
        materials = request.form.get("materials_used", "").strip() or None
        feedback = request.form.get("feedback", "").strip() or None

        try:
            actual_hours = Decimal(hours_raw)
            if actual_hours < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            flash("Zadejte platný počet hodin (kladné číslo).", "danger")
            return render_template("debriefing/submit.html", assignment=assignment, event=event, existing=existing)

        try:
            patients_treated = int(patients_raw)
            if patients_treated < 0:
                raise ValueError
        except (ValueError):
            patients_treated = 0

        if existing:
            existing.actual_hours = actual_hours
            existing.patients_treated = patients_treated
            existing.materials_used = materials
            existing.feedback = feedback
            existing.submitted_by_id = current_user.id
            _audit("edit", existing, f"Hlášení aktualizováno pro akci '{event.name}'")
        else:
            record = DebriefingRecord(
                assignment_id=assignment_id,
                submitted_by_id=current_user.id,
                actual_hours=actual_hours,
                patients_treated=patients_treated,
                materials_used=materials,
                feedback=feedback,
            )
            db.session.add(record)
            db.session.flush()
            _audit("create", record, f"Hlášení odevzdáno pro akci '{event.name}'")

        db.session.commit()
        flash("Hlášení bylo úspěšně uloženo.", "success")
        return redirect(url_for("events.detail", event_id=event.id))

    return render_template("debriefing/submit.html", assignment=assignment, event=event, existing=existing)


# ── Event debriefing overview (coordinator) ───────────────────────────────────

@debriefing_bp.get("/event/<int:event_id>")
@login_required
def event_overview(event_id: int):
    if not current_user.has_any_permission("event.edit", "event.assign_other"):
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    assignments = [s.assignment for s in event.spots if s.assignment is not None]
    return render_template("debriefing/event_overview.html", event=event, assignments=assignments)
