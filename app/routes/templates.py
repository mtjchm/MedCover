"""
Event Template CRUD blueprint.

Permissions:
  event_template.view    — list templates
  event_template.create  — create templates
  event_template.edit    — edit templates
  event_template.delete  — delete templates
"""

from __future__ import annotations

from flask import Blueprint, Response, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.event import EventTemplate, EventSpotTemplate
from app.models.qualification import Qualification
from app.models.equipment import EquipmentType, EventTemplateEquipmentPlan
from app.models.audit import AuditLogEntry
from app.utils import diff_changes

templates_bp = Blueprint("templates", __name__, url_prefix="/templates")


def _audit(
    action: str, template: EventTemplate, summary: str, changes: dict | None = None
) -> None:
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type=action,
        entity_type="EventTemplate",
        entity_id=str(template.id),
        summary=summary,
        changes_json=changes,
    ))


def _parse_spot_slots(form: dict) -> list[tuple[str | None, bool, list[int]]]:
    """Parse spot template data from form.

    Expects spot_desc_N, spot_cred_N (multiple checkboxes), spot_optional_N,
    and spot_total fields.
    Returns list of (description, is_optional, qualification_ids) for each slot.
    """
    try:
        spot_total = int(form.get("spot_total", 0) or 0)
    except (ValueError, TypeError):
        spot_total = 0

    slots: list[tuple[str | None, bool, list[int]]] = []
    for n in range(spot_total):
        desc = (form.get(f"spot_desc_{n}") or "").strip() or None
        is_optional = form.get(f"spot_optional_{n}") == "1"
        qual_ids = [int(c) for c in form.getlist(f"spot_cred_{n}") if str(c).isdigit()]
        slots.append((desc, is_optional, qual_ids))
    return slots


def _rebuild_equipment_plans(template: EventTemplate, form: dict) -> None:
    """Delete existing equipment plans and recreate from form data."""
    for ep in list(template.equipment_plans):
        db.session.delete(ep)
    db.session.flush()
    for key, val in form.items():
        if key.startswith("equip_qty_"):
            try:
                type_id = int(key.split("equip_qty_")[1])
                qty = int(val)
            except (ValueError, IndexError):
                continue
            if qty > 0:
                ep = EventTemplateEquipmentPlan(
                    template_id=template.id,
                    equipment_type_id=type_id,
                    quantity_required=qty,
                )
                db.session.add(ep)


def _rebuild_spot_templates(
        template: EventTemplate, slots: list[tuple[str | None, bool, list[int]]]) -> None:
    """Delete existing spot templates and recreate from slots."""
    for st in list(template.spot_templates):
        db.session.delete(st)
    db.session.flush()
    for desc, is_optional, qual_ids in slots:
        st = EventSpotTemplate(template_id=template.id, description=desc, is_optional=is_optional)
        if qual_ids:
            creds = db.session.scalars(
                db.select(Qualification).where(Qualification.id.in_(qual_ids))
            ).all()
            st.required_qualifications = list(creds)
        db.session.add(st)


# ── List ──────────────────────────────────────────────────────────────────────

@templates_bp.get("/")
@login_required
def index() -> str:
    if not current_user.has_permission("event_template.view"):
        abort(403)

    all_templates = db.session.scalars(
        db.select(EventTemplate).order_by(EventTemplate.name)
    ).all()
    return render_template("templates/index.html", templates=all_templates)


# ── Create ────────────────────────────────────────────────────────────────────

@templates_bp.route("/create", methods=["GET", "POST"])
@login_required
def create() -> str | Response:
    if not current_user.has_permission("event_template.create"):
        abort(403)

    qualifications = db.session.scalars(
        db.select(Qualification).order_by(Qualification.name)
    ).all()
    equipment_types = db.session.scalars(
        db.select(EquipmentType).order_by(EquipmentType.name)
    ).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        paid = request.form.get("paid") == "1"
        reminder_schedule = request.form.get("reminder_schedule", "24").strip() or "24"

        if not name:
            flash("Název šablony je povinný.", "danger")
            return render_template("templates/form.html", template=None, qualifications=qualifications, equipment_types=equipment_types)

        if db.session.scalar(db.select(EventTemplate).where(EventTemplate.name == name)):
            flash("Šablona s tímto názvem již existuje.", "danger")
            return render_template("templates/form.html", template=None, qualifications=qualifications, equipment_types=equipment_types)

        tmpl = EventTemplate(
            name=name,
            description=description,
            paid=paid,
            reminder_schedule=reminder_schedule,
        )
        db.session.add(tmpl)
        db.session.flush()

        slots = _parse_spot_slots(request.form)
        _rebuild_spot_templates(tmpl, slots)
        _rebuild_equipment_plans(tmpl, request.form)

        _audit("create", tmpl, f"Vytvořena šablona akce '{tmpl.name}'")
        db.session.commit()

        flash(f'Šablona „{tmpl.name}" byla vytvořena.', "success")
        return redirect(url_for("templates.index"))

    return render_template("templates/form.html", template=None, qualifications=qualifications, equipment_types=equipment_types)


# ── Edit ──────────────────────────────────────────────────────────────────────

@templates_bp.route("/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
def edit(template_id: int) -> str | Response:
    if not current_user.has_permission("event_template.edit"):
        abort(403)

    tmpl = db.session.get(EventTemplate, template_id)
    if tmpl is None:
        abort(404)

    qualifications = db.session.scalars(
        db.select(Qualification).order_by(Qualification.name)
    ).all()
    equipment_types = db.session.scalars(
        db.select(EquipmentType).order_by(EquipmentType.name)
    ).all()

    if request.method == "POST":
        submitted_version = int(request.form.get("version", 0))
        if submitted_version != tmpl.version:
            flash("Záznam byl mezitím změněn, načtěte stránku znovu.", "danger")
            return render_template("templates/form.html", template=tmpl, qualifications=qualifications, equipment_types=equipment_types)

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        paid = request.form.get("paid") == "1"
        reminder_schedule = request.form.get("reminder_schedule", "24").strip() or "24"

        if not name:
            flash("Název šablony je povinný.", "danger")
            return render_template("templates/form.html", template=tmpl, qualifications=qualifications, equipment_types=equipment_types)

        conflict = db.session.scalar(
            db.select(EventTemplate).where(
                EventTemplate.name == name, EventTemplate.id != template_id
            )
        )
        if conflict:
            flash("Šablona s tímto názvem již existuje.", "danger")
            return render_template("templates/form.html", template=tmpl, qualifications=qualifications, equipment_types=equipment_types)

        before = {
            "name": tmpl.name,
            "description": tmpl.description,
            "paid": tmpl.paid,
            "reminder_schedule": tmpl.reminder_schedule,
            "spot_count": len(tmpl.spot_templates),
        }

        tmpl.name = name
        tmpl.description = description
        tmpl.paid = paid
        tmpl.reminder_schedule = reminder_schedule
        tmpl.version += 1

        slots = _parse_spot_slots(request.form)
        _rebuild_spot_templates(tmpl, slots)
        _rebuild_equipment_plans(tmpl, request.form)

        after = {
            "name": tmpl.name,
            "description": tmpl.description,
            "paid": tmpl.paid,
            "reminder_schedule": tmpl.reminder_schedule,
            "spot_count": len(slots),
        }

        _audit(
            "edit",
            tmpl,
            f"Upravena šablona akce '{tmpl.name}'",
            diff_changes(before, after),
        )
        db.session.commit()

        flash(f'Šablona „{tmpl.name}" byla uložena.', "success")
        return redirect(url_for("templates.index"))

    return render_template("templates/form.html", template=tmpl, qualifications=qualifications, equipment_types=equipment_types)


# ── Delete ────────────────────────────────────────────────────────────────────

@templates_bp.post("/<int:template_id>/delete")
@login_required
def delete(template_id: int) -> Response:
    if not current_user.has_permission("event_template.delete"):
        abort(403)

    tmpl = db.session.get(EventTemplate, template_id)
    if tmpl is None:
        abort(404)

    name = tmpl.name
    _audit("delete", tmpl, f"Smazána šablona akce '{name}'")
    db.session.delete(tmpl)
    db.session.commit()

    flash(f'Šablona „{name}" byla smazána.', "success")
    return redirect(url_for("templates.index"))
