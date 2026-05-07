from __future__ import annotations

from datetime import datetime, timezone
import socket

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_mail import Message

from app.extensions import db, mail
from app.models.user import UserAccount
from app.models.settings import get_settings

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

_PAGE_SIZE = 50


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
    db_error: str | None = None
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_ok = False
        db_error = type(exc).__name__

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
    smtp_reachable: bool | None = None  # None = not tested (not configured)
    smtp_error: str | None = None
    if smtp_configured:
        try:
            with socket.create_connection((settings.smtp_server, settings.smtp_port), timeout=2):
                smtp_reachable = True
        except OSError as exc:
            smtp_reachable = False
            smtp_error = str(exc)

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
        db_error=db_error,
        sched_status=sched_status,
        sched_last=sched_last,
        sched_age_s=sched_age_s,
        smtp_configured=smtp_configured,
        smtp_reachable=smtp_reachable,
        smtp_error=smtp_error,
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


# ── Audit log ─────────────────────────────────────────────────────────────────

@admin_bp.route("/audit-log/")
@login_required
def audit_log_list() -> str:
    _require_permission("admin.view")

    from app.models.audit import AuditLogEntry

    page = request.args.get("page", 1, type=int)
    f_entity_type = request.args.get("entity_type", "").strip()
    f_actor_id = request.args.get("actor_id", "").strip()
    f_action_type = request.args.get("action_type", "").strip()
    f_date_from = request.args.get("date_from", "").strip()
    f_date_to = request.args.get("date_to", "").strip()
    f_q = request.args.get("q", "").strip()

    query = db.select(AuditLogEntry).order_by(AuditLogEntry.timestamp.desc())

    if f_entity_type:
        query = query.where(AuditLogEntry.entity_type == f_entity_type)
    if f_actor_id:
        query = query.where(AuditLogEntry.actor_id == f_actor_id)
    if f_action_type:
        query = query.where(AuditLogEntry.action_type == f_action_type)
    if f_date_from:
        try:
            dt_from = datetime.strptime(f_date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.where(AuditLogEntry.timestamp >= dt_from)
        except ValueError:
            pass
    if f_date_to:
        try:
            dt_to = datetime.strptime(f_date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # include the full day
            from datetime import timedelta
            query = query.where(AuditLogEntry.timestamp < dt_to + timedelta(days=1))
        except ValueError:
            pass
    if f_q:
        query = query.where(AuditLogEntry.summary.ilike(f"%{f_q}%"))

    # Paginate manually: count + offset/limit
    total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    entries = db.session.scalars(
        query.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE)
    ).all()
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)

    # Distinct values for filter dropdowns
    entity_types = db.session.scalars(
        db.select(AuditLogEntry.entity_type).distinct().order_by(AuditLogEntry.entity_type)
    ).all()
    action_types = db.session.scalars(
        db.select(AuditLogEntry.action_type).distinct().order_by(AuditLogEntry.action_type)
    ).all()
    actors = db.session.scalars(
        db.select(UserAccount)
        .where(UserAccount.id.in_(
            db.select(AuditLogEntry.actor_id).where(AuditLogEntry.actor_id.isnot(None)).distinct()
        ))
        .order_by(UserAccount.name)
    ).all()

    return render_template(
        "admin/audit_log_list.html",
        entries=entries,
        page=page,
        total=total,
        total_pages=total_pages,
        entity_types=entity_types,
        action_types=action_types,
        actors=actors,
        f_entity_type=f_entity_type,
        f_actor_id=f_actor_id,
        f_action_type=f_action_type,
        f_date_from=f_date_from,
        f_date_to=f_date_to,
        f_q=f_q,
    )


@admin_bp.route("/audit-log/<int:entry_id>")
@login_required
def audit_log_detail(entry_id: int) -> str:
    _require_permission("admin.view")

    from app.models.audit import AuditLogEntry
    from flask import abort

    entry = db.session.get(AuditLogEntry, entry_id)
    if entry is None:
        abort(404)

    return render_template("admin/audit_log_detail.html", entry=entry)
