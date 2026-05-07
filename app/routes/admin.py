from __future__ import annotations

from datetime import datetime, timezone
import socket

from flask import Blueprint, Response, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from flask_mail import Message

from app.extensions import db, mail
from app.models.user import UserAccount
from app.models.settings import get_settings

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_permission(code: str) -> None:
    """Return 403 response if current user lacks the permission."""
    from flask import abort
    if not current_user.has_permission(code):
        abort(403)


@admin_bp.route("/")
@login_required
def index() -> str:
    _require_permission("admin.view")

    from app.models.event import Event, EventStatus
    from app.models.outbox import OutboxEmail
    from app.models.audit import AuditLogEntry

    settings = get_settings()
    now = datetime.now(timezone.utc)

    # ── DB health ──────────────────────────────────────────────────────────────
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # ── Scheduler heartbeat ────────────────────────────────────────────────────
    sched_last = settings.scheduler_last_seen
    if sched_last is None:
        sched_status = "unknown"
        sched_age_s = None
    else:
        sched_age_s = int((now - sched_last).total_seconds())
        if sched_age_s < 30:
            sched_status = "ok"
        elif sched_age_s < 300:
            sched_status = "warning"
        else:
            sched_status = "error"

    # ── SMTP reachability ──────────────────────────────────────────────────────
    smtp_configured = settings.smtp_configured
    smtp_reachable = None  # None = not tested (not configured)
    if smtp_configured:
        try:
            with socket.create_connection((settings.smtp_server, settings.smtp_port), timeout=2):
                smtp_reachable = True
        except Exception:
            smtp_reachable = False

    # ── Statistics ─────────────────────────────────────────────────────────────
    user_total = db.session.scalar(db.select(db.func.count()).select_from(UserAccount))
    user_active = db.session.scalar(db.select(db.func.count()).select_from(UserAccount).where(UserAccount.is_active == True))  # noqa: E712
    user_pending = user_total - user_active

    event_counts = {
        s.value: db.session.scalar(
            db.select(db.func.count()).select_from(Event).where(Event.status == s)
        )
        for s in EventStatus
    }
    event_total = sum(event_counts.values())

    outbox_pending = db.session.scalar(
        db.select(db.func.count()).select_from(OutboxEmail).where(OutboxEmail.status == "pending")
    )
    outbox_failed = db.session.scalar(
        db.select(db.func.count()).select_from(OutboxEmail).where(OutboxEmail.status == "failed")
    )
    outbox_last_sent = db.session.scalar(
        db.select(OutboxEmail.sent_at)
        .where(OutboxEmail.status == "sent")
        .order_by(OutboxEmail.sent_at.desc())
        .limit(1)
    )

    # ── Recent audit log ───────────────────────────────────────────────────────
    recent_audit = db.session.scalars(
        db.select(AuditLogEntry)
        .order_by(AuditLogEntry.timestamp.desc())
        .limit(8)
    ).all()

    return render_template(
        "admin/index.html",
        db_ok=db_ok,
        sched_status=sched_status,
        sched_last=sched_last,
        sched_age_s=sched_age_s,
        smtp_configured=smtp_configured,
        smtp_reachable=smtp_reachable,
        settings=settings,
        user_total=user_total,
        user_active=user_active,
        user_pending=user_pending,
        event_total=event_total,
        event_counts=event_counts,
        outbox_pending=outbox_pending,
        outbox_failed=outbox_failed,
        outbox_last_sent=outbox_last_sent,
        recent_audit=recent_audit,
        now=now,
    )


@admin_bp.route("/pending-users")
@login_required
def pending_users() -> str:
    _require_permission("user.activate")
    users = UserAccount.query.filter_by(is_active=False).order_by(UserAccount.created_at).all()
    return render_template("admin/pending_users.html", users=users)


@admin_bp.route("/activate/<uuid:user_id>", methods=["POST"])
@login_required
def activate_user(user_id: str) -> Response:
    _require_permission("user.activate")
    user = db.session.get(UserAccount, user_id)
    if not user:
        flash("Uživatel nenalezen.", "danger")
        return redirect(url_for("admin.pending_users"))
    if user.is_active:
        flash(f"{user.name} je již aktivní.", "info")
        return redirect(url_for("admin.pending_users"))

    user.is_active = True
    db.session.commit()

    _send_activation_email(user)
    flash(f"Účet {user.name} ({user.email}) byl aktivován.", "success")
    return redirect(url_for("admin.pending_users"))


def _send_activation_email(user: UserAccount) -> None:
    login_url = url_for("auth.login", _external=True)
    body = render_template("email/account_activated.txt", user=user, login_url=login_url)
    msg = Message(
        subject="MedCover — váš účet byl aktivován",
        recipients=[user.email],
        body=body,
    )
    try:
        mail.send(msg)
    except Exception as exc:
        current_app.logger.warning("Activation email failed for %s: %s", user.email, exc)
