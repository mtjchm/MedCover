"""
Admin notification management route.

Provides a catalog of all email notification types defined in NOTIFICATION_CATALOG
and allows admins to toggle each configurable type on/off via AppSettings.
"""

from __future__ import annotations


from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.mail import NOTIFICATION_CATALOG
from app.models.settings import get_settings
from app.utils import audit, diff_changes, require_permission

notifications_bp = Blueprint("notifications", __name__, url_prefix="/admin/notifications")


def _build_toggle_groups(catalog: list[dict]) -> list[dict]:
    """Group catalog entries by settings_field for the toggle UI.

    Returns a list of dicts: {settings_field, label_cs, entries} sorted by
    first appearance in the catalog.  Always-on entries are excluded.
    """
    seen: dict[str, dict] = {}
    order: list[str] = []
    for entry in catalog:
        field = entry["settings_field"]
        if field is None:
            continue
        if field not in seen:
            seen[field] = {"settings_field": field, "entries": []}
            order.append(field)
        seen[field]["entries"].append(entry)
    return [seen[f] for f in order]


@notifications_bp.route("/", methods=["GET", "POST"])
@login_required
def index() -> str | Response:
    require_permission("admin.manage_settings")
    settings = get_settings()

    # Unique togglable fields (one checkbox per field, not per catalog entry)
    togglable_fields = {
        entry["settings_field"]
        for entry in NOTIFICATION_CATALOG
        if entry["settings_field"] is not None
    }
    toggle_groups = _build_toggle_groups(NOTIFICATION_CATALOG)

    if request.method == "POST":
        before = {field: getattr(settings, field, True) for field in togglable_fields}

        for field in togglable_fields:
            setattr(settings, field, field in request.form)

        after = {field: getattr(settings, field) for field in togglable_fields}
        changes = diff_changes(before, after)

        audit("edit", "AppSettings", 1, "Nastavení e-mailových oznámení bylo upraveno.", changes)
        db.session.commit()
        flash("Nastavení oznámení bylo uloženo.", "success")
        return redirect(url_for("notifications.index"))

    return render_template(
        "admin/notifications.html",
        catalog=NOTIFICATION_CATALOG,
        toggle_groups=toggle_groups,
        settings=settings,
    )
