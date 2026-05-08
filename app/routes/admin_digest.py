"""Admin digest configuration, preview and send routes."""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, Response, url_for
from flask_login import current_user, login_required

from app.extensions import db

log = logging.getLogger(__name__)

bp = Blueprint("admin_digest", __name__, url_prefix="/admin/digest")

_FREQUENCY_OPTIONS = [
    (6, "Každých 6 hodin"),
    (12, "Každých 12 hodin"),
    (24, "Jednou denně"),
    (48, "Každé 2 dny"),
    (72, "Každé 3 dny"),
    (168, "Jednou týdně"),
]


def _require_digest_perm() -> None:
    if not current_user.is_authenticated or not current_user.has_permission("admin.manage_digest"):
        abort(403)


# ── Settings page ─────────────────────────────────────────────────────────────

@bp.route("/", methods=["GET"])
@login_required
def index() -> str:
    _require_digest_perm()
    from app.models.digest import get_digest_schedule
    from app.digest.registry import BLOCK_REGISTRY

    schedule = get_digest_schedule()
    return render_template(
        "admin/digest/index.html",
        schedule=schedule,
        frequency_options=_FREQUENCY_OPTIONS,
        hour_options=list(range(24)),
        block_registry=BLOCK_REGISTRY,
    )


@bp.route("/save", methods=["POST"])
@login_required
def save() -> Response:
    _require_digest_perm()
    from app.models.digest import get_digest_schedule

    schedule = get_digest_schedule()

    client_version = request.form.get("version", type=int, default=0)
    if client_version != schedule.version:
        flash("Nastavení bylo mezitím změněno — načtěte stránku znovu.", "danger")
        return redirect(url_for("admin_digest.index"))

    schedule.enabled = bool(request.form.get("enabled"))
    schedule.frequency_hours = int(request.form.get("frequency_hours", 24))
    schedule.preferred_hour_utc = max(0, min(23, int(request.form.get("preferred_hour_utc", 7))))
    schedule.email_subject = request.form.get("email_subject", "").strip() or "MedCover — Přehledový e-mail"
    schedule.header_html = request.form.get("header_html", "").strip() or None
    schedule.footer_html = request.form.get("footer_html", "").strip() or None
    schedule.version += 1

    db.session.commit()
    flash("Nastavení přehledového e-mailu bylo uloženo.", "success")
    return redirect(url_for("admin_digest.index"))


# ── Block config ──────────────────────────────────────────────────────────────

@bp.route("/blocks/<block_type>/save", methods=["POST"])
@login_required
def save_block(block_type: str) -> Response:
    _require_digest_perm()
    from app.models.digest import get_digest_schedule, DigestBlock
    from app.digest.registry import BLOCK_REGISTRY
    import sqlalchemy as sa

    if block_type not in BLOCK_REGISTRY:
        abort(404)

    schedule = get_digest_schedule()
    block = db.session.scalar(
        sa.select(DigestBlock).where(
            DigestBlock.digest_schedule_id == schedule.id,
            DigestBlock.block_type == block_type,
        ).with_for_update()
    )
    if block is None:
        abort(404)

    client_version = request.form.get("version", type=int, default=0)
    if client_version != block.version:
        flash("Nastavení bloku bylo mezitím změněno — načtěte stránku znovu.", "danger")
        return redirect(url_for("admin_digest.index"))

    block.enabled = bool(request.form.get("enabled"))
    cls = BLOCK_REGISTRY[block_type]
    new_config = dict(block.config_json or cls.default_config)

    # Merge form values for known config keys
    _merge_block_config(block_type, new_config, request.form)

    block.config_json = new_config
    block.version += 1
    db.session.commit()
    flash(f'Blok "{cls.label}" byl uložen.', "success")
    return redirect(url_for("admin_digest.index"))


def _merge_block_config(block_type: str, config: dict[str, object], form: Any) -> None:
    """Write form values into config dict for the given block type."""
    config["title"] = form.get("title", config.get("title", "")).strip()

    if block_type == "server_stats":
        for key in ("show_user_count", "show_event_count", "show_db_size",
                    "show_scheduler_heartbeat", "show_outbox_pending", "show_outbox_peak"):
            config[key] = bool(form.get(key))
        config["peak_hours"] = max(1, int(form.get("peak_hours", 24) or 24))

    elif block_type == "audit_log":
        config["hours"] = max(1, int(form.get("hours", 24) or 24))
        config["max_rows"] = max(1, min(200, int(form.get("max_rows", 50) or 50)))
        config["show_actor"] = bool(form.get("show_actor"))
        config["entity_types"] = form.getlist("entity_types")
        config["action_types"] = form.getlist("action_types")

    elif block_type == "upcoming_events":
        config["days_ahead"] = max(1, int(form.get("days_ahead", 7) or 7))
        config["max_rows"] = max(1, min(100, int(form.get("max_rows", 15) or 15)))
        config["show_unfilled_only"] = bool(form.get("show_unfilled_only"))

    elif block_type == "new_users":
        config["hours"] = max(1, int(form.get("hours", 24) or 24))
        config["max_rows"] = max(1, min(100, int(form.get("max_rows", 20) or 20)))
        config["show_pending_only"] = bool(form.get("show_pending_only"))

    elif block_type == "feedback_summary":
        config["hours"] = max(1, int(form.get("hours", 24) or 24))
        config["max_rows"] = max(1, min(100, int(form.get("max_rows", 20) or 20)))

    elif block_type == "free_text":
        config["content"] = form.get("content", "")


# ── Block reorder ─────────────────────────────────────────────────────────────

@bp.route("/blocks/reorder", methods=["POST"])
@login_required
def reorder_blocks() -> dict[str, bool]:
    _require_digest_perm()
    from app.models.digest import get_digest_schedule, DigestBlock
    import sqlalchemy as sa

    order: list[str] = request.get_json(silent=True) or []
    schedule = get_digest_schedule()

    for i, btype in enumerate(order):
        db.session.execute(
            sa.update(DigestBlock)
            .where(DigestBlock.digest_schedule_id == schedule.id, DigestBlock.block_type == btype)
            .values(sort_order=i)
        )
    db.session.commit()
    return {"ok": True}


# ── Preview ───────────────────────────────────────────────────────────────────

@bp.route("/preview")
@login_required
def preview() -> Response:
    _require_digest_perm()
    from app.digest.renderer import render_digest

    html = render_digest(db.session)
    return Response(html, content_type="text/html; charset=utf-8")


# ── Send test ─────────────────────────────────────────────────────────────────

@bp.route("/send-test", methods=["POST"])
@login_required
def send_test() -> Response:
    _require_digest_perm()
    from app.digest.renderer import render_digest
    from app.mail import send_admin_digest
    from app.models.digest import get_digest_schedule

    email = request.form.get("test_email", "").strip()
    if not email:
        flash("Zadejte e-mailovou adresu.", "danger")
        return redirect(url_for("admin_digest.index"))

    schedule = get_digest_schedule()
    html = render_digest(db.session)
    send_admin_digest(email, f"[TEST] {schedule.email_subject}", html)
    db.session.commit()
    flash(f"Testovací přehledový e-mail byl zařazen do fronty pro {email}.", "success")
    return redirect(url_for("admin_digest.index"))


# ── Send now (to all admins) ──────────────────────────────────────────────────

@bp.route("/send-now", methods=["POST"])
@login_required
def send_now() -> Response:
    _require_digest_perm()
    from app.digest.renderer import render_digest
    from app.mail import send_admin_digest, user_can_receive_notification
    from app.models.digest import get_digest_schedule
    from app.models.user import UserAccount
    import sqlalchemy as sa

    schedule = get_digest_schedule()
    html = render_digest(db.session)

    recipients = db.session.scalars(
        sa.select(UserAccount).where(UserAccount.is_active == True)  # noqa: E712
    ).all()

    count = 0
    for user in recipients:
        if user_can_receive_notification(user, "admin_digest"):
            send_admin_digest(user.email, schedule.email_subject, html)
            count += 1

    db.session.commit()
    flash(f"Přehledový e-mail byl zařazen do fronty pro {count} příjemce.", "success")
    return redirect(url_for("admin_digest.index"))
