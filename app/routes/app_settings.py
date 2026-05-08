"""
Admin application settings route — lets admins edit org info and SMTP config
after the initial setup wizard has completed.
"""

from __future__ import annotations

import pytz
from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_mail import Message

from app.extensions import db, mail
from app.models.audit import AuditLogEntry
from app.models.settings import get_settings
from app.utils import diff_changes

app_settings_bp = Blueprint("app_settings", __name__, url_prefix="/admin/settings")

_ALL_TIMEZONES = pytz.common_timezones


def _require_permission() -> None:
    if not current_user.has_permission("admin.manage_settings"):
        abort(403)


@app_settings_bp.route("/", methods=["GET", "POST"])
@login_required
def index() -> str | Response:
    _require_permission()
    settings = get_settings()

    if request.method == "POST":
        action = request.form.get("action", "save")

        # --- Read posted values ---
        org_name = request.form.get("org_name", "").strip() or None
        timezone = request.form.get("timezone", "Europe/Prague")
        app_base_url = request.form.get("app_base_url", "").strip().rstrip("/") or None
        feedback_enabled = "feedback_enabled" in request.form
        smtp_server = request.form.get("smtp_server", "").strip() or None
        smtp_port = int(request.form.get("smtp_port") or 587)
        smtp_use_tls = "smtp_use_tls" in request.form
        smtp_username = request.form.get("smtp_username", "").strip() or None
        new_pw = request.form.get("smtp_password", "")
        smtp_default_sender = request.form.get("smtp_default_sender", "").strip() or None

        # --- Validate ---
        if timezone not in pytz.all_timezones_set:
            flash("Neplatná časová zóna.", "warning")
            return render_template("admin/app_settings.html", settings=settings, timezones=_ALL_TIMEZONES)

        # --- Build before dict for audit (no secrets) ---
        before = {
            "org_name": settings.org_name,
            "timezone": settings.timezone,
            "app_base_url": settings.app_base_url,
            "feedback_enabled": settings.feedback_enabled,
            "smtp_server": settings.smtp_server,
            "smtp_port": settings.smtp_port,
            "smtp_use_tls": settings.smtp_use_tls,
            "smtp_username": settings.smtp_username,
            "smtp_default_sender": settings.smtp_default_sender,
            # smtp_password intentionally omitted — secret
        }

        # --- Apply changes ---
        settings.org_name = org_name
        settings.timezone = timezone
        settings.app_base_url = app_base_url
        settings.feedback_enabled = feedback_enabled
        settings.smtp_server = smtp_server
        settings.smtp_port = smtp_port
        settings.smtp_use_tls = smtp_use_tls
        settings.smtp_username = smtp_username
        if new_pw:
            settings.set_smtp_password(new_pw)
        settings.smtp_default_sender = smtp_default_sender
        db.session.flush()

        after = {
            "org_name": settings.org_name,
            "timezone": settings.timezone,
            "app_base_url": settings.app_base_url,
            "feedback_enabled": settings.feedback_enabled,
            "smtp_server": settings.smtp_server,
            "smtp_port": settings.smtp_port,
            "smtp_use_tls": settings.smtp_use_tls,
            "smtp_username": settings.smtp_username,
            "smtp_default_sender": settings.smtp_default_sender,
        }

        if action == "test":
            # Save first, then try test email
            db.session.commit()
            settings.apply_to_app(current_app._get_current_object())
            if not settings.smtp_configured:
                flash("Před odesláním testovacího e-mailu vyplňte SMTP nastavení.", "warning")
            else:
                try:
                    msg = Message(
                        subject="MedCover — testovací e-mail",
                        recipients=[settings.smtp_username],
                        body="Tento e-mail potvrzuje, že SMTP nastavení v MedCover je funkční.",
                    )
                    mail.send(msg)
                    flash("Testovací e-mail byl odeslán na adresu " + (settings.smtp_username or ""), "success")
                except Exception as exc:
                    flash(f"Odeslání se nezdařilo: {exc}", "danger")
            return render_template("admin/app_settings.html", settings=settings, timezones=_ALL_TIMEZONES)

        # --- Commit + audit ---
        db.session.add(AuditLogEntry(
            actor_id=current_user.id,
            action_type="edit",
            entity_type="AppSettings",
            entity_id=1,
            summary="Nastavení aplikace bylo upraveno.",
            changes_json=diff_changes(before, after),
        ))
        db.session.commit()
        settings.apply_to_app(current_app._get_current_object())
        flash("Nastavení bylo uloženo.", "success")
        return redirect(url_for("app_settings.index"))

    return render_template("admin/app_settings.html", settings=settings, timezones=_ALL_TIMEZONES)
