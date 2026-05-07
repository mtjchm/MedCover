"""
Credentials admin blueprint.

Permissions:
  credential.view    — list + detail
  credential.create  — create
  credential.edit    — edit (name, description, parent hierarchy)
  credential.delete  — delete (only if no users or spots hold it)
"""

from __future__ import annotations

from flask import Blueprint, Response, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models.credential import Credential
from app.models.audit import AuditLogEntry
from app.utils import diff_changes

credentials_bp = Blueprint("credentials", __name__, url_prefix="/credentials")


def _audit(action: str, cred: Credential, summary: str, changes: dict | None = None) -> None:
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type=action,
        entity_type="Credential",
        entity_id=str(cred.id),
        summary=summary,
        changes_json=changes,
    ))


# ── List ──────────────────────────────────────────────────────────────────────

@credentials_bp.get("/")
@login_required
def index() -> str:
    if not current_user.has_permission("credential.view"):
        abort(403)
    credentials = db.session.scalars(
        db.select(Credential).order_by(Credential.name)
    ).all()
    return render_template("credentials/index.html", credentials=credentials)


# ── Create ────────────────────────────────────────────────────────────────────

@credentials_bp.route("/create", methods=["GET", "POST"])
@login_required
def create() -> str | Response:
    if not current_user.has_permission("credential.create"):
        abort(403)

    all_credentials = db.session.scalars(db.select(Credential).order_by(Credential.name)).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        parent_ids = request.form.getlist("parent_ids")

        if not name:
            flash("Název kvalifikace je povinný.", "danger")
            return render_template("credentials/create.html", all_credentials=all_credentials)

        if db.session.scalar(db.select(Credential).where(Credential.name == name)):
            flash("Kvalifikace s tímto názvem již existuje.", "danger")
            return render_template("credentials/create.html", all_credentials=all_credentials)

        cred = Credential(name=name, description=description)
        for pid in parent_ids:
            parent = db.session.get(Credential, int(pid))
            if parent:
                cred.parents.append(parent)

        db.session.add(cred)
        db.session.flush()
        _audit("create", cred, f"Vytvořena kvalifikace '{cred.name}'")
        db.session.commit()

        flash(f"Kvalifikace '{cred.name}' byla vytvořena.", "success")
        return redirect(url_for("credentials.index"))

    return render_template("credentials/create.html", all_credentials=all_credentials)


# ── Edit ──────────────────────────────────────────────────────────────────────

@credentials_bp.route("/<int:cred_id>/edit", methods=["GET", "POST"])
@login_required
def edit(cred_id: int) -> str | Response:
    if not current_user.has_permission("credential.edit"):
        abort(403)

    cred = db.session.get(Credential, cred_id)
    if cred is None:
        abort(404)

    all_credentials = db.session.scalars(
        db.select(Credential).where(Credential.id != cred_id).order_by(Credential.name)
    ).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        parent_ids = {int(pid) for pid in request.form.getlist("parent_ids")}

        if not name:
            flash("Název kvalifikace je povinný.", "danger")
            return render_template("credentials/edit.html", cred=cred, all_credentials=all_credentials)

        conflict = db.session.scalar(
            db.select(Credential).where(Credential.name == name, Credential.id != cred_id)
        )
        if conflict:
            flash("Kvalifikace s tímto názvem již existuje.", "danger")
            return render_template("credentials/edit.html", cred=cred, all_credentials=all_credentials)

        before = {"name": cred.name, "description": cred.description, "parents": str([p.id for p in cred.parents])}
        cred.name = name
        cred.description = description
        # Sync parents
        cred.parents = [c for pid in parent_ids if (c := db.session.get(Credential, pid)) is not None]

        _audit("edit", cred, f"Upravena kvalifikace '{cred.name}'", diff_changes(
            before,
            {"name": cred.name, "description": cred.description, "parents": str([p.id for p in cred.parents])},
        ))
        db.session.commit()

        flash(f"Kvalifikace '{cred.name}' byla uložena.", "success")
        return redirect(url_for("credentials.index"))

    return render_template("credentials/edit.html", cred=cred, all_credentials=all_credentials)


# ── Delete ────────────────────────────────────────────────────────────────────

@credentials_bp.post("/<int:cred_id>/delete")
@login_required
def delete(cred_id: int) -> Response:
    if not current_user.has_permission("credential.delete"):
        abort(403)

    cred = db.session.get(Credential, cred_id)
    if cred is None:
        abort(404)

    # Guard: cannot delete if assigned to users or spots
    from app.models.credential import user_credentials
    holder_count = db.session.scalar(
        db.select(db.func.count()).select_from(user_credentials).where(
            user_credentials.c.credential_id == cred_id
        )
    )
    if holder_count and holder_count > 0:
        flash(f"Nelze smazat kvalifikaci '{cred.name}' — je přiřazena uživatelům.", "danger")
        return redirect(url_for("credentials.index"))

    _audit("delete", cred, f"Smazána kvalifikace '{cred.name}'")
    db.session.delete(cred)
    db.session.commit()

    flash(f"Kvalifikace '{cred.name}' byla smazána.", "success")
    return redirect(url_for("credentials.index"))
