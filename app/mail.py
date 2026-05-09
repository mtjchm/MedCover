"""
Centralised email helper for MedCover.

All public send_* functions enqueue a row into ``outbox_email`` instead of
calling the SMTP server directly.  The scheduler's ``process_email_queue``
job drains the queue at a controlled rate (MAIL_QUEUE_INTERVAL_SECONDS,
default 6 s ≈ 10 emails/minute) which keeps the app safely inside the
rate limits of any standard SMTP relay (e.g. Microsoft 365: 30/min).

Usage (inside a Flask app context):
    from app.mail import send_assignment_confirmed, send_event_published, ...

All functions are fire-and-forget — exceptions are logged, never raised.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from flask import render_template

from app.extensions import db
from app.models.outbox import OutboxEmail

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.event import Event
    from app.models.user import UserAccount

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role-based notification gating (AD17)
# ---------------------------------------------------------------------------

# Roles whose members may receive each notification category.
# "auth" (invite / password-reset / activation) is exempt — always allowed.
_NOTIFICATION_ALLOWED_ROLES: dict[str, set[str]] = {
    "admin_digest":      {"Admin"},
    "event_lifecycle":   {"Coordinator", "Member"},  # published, assignments_opened
    "assignment":        {"Member"},                 # confirmed, released
    "unfilled_reminder": {"Coordinator", "Member"},  # reminder to coordinator / RP
    "event_cancelled":   {"Member"},                 # cancelled → notify assigned users
}


def user_can_receive_notification(user: UserAccount, notification_type: str) -> bool:
    """Return True if *user* is eligible for a notification of *notification_type*.

    Rules (AD17):
    - Viewer-only users receive no operational emails (only auth emails).
    - Users with any non-Viewer role are subject to the per-category role map.
    - "auth" category is always True for all users (invite, reset, activation).
    """
    if notification_type == "auth":
        return True

    user_role_names: set[str] = {r.name for r in user.roles}

    # Viewer-only → no operational emails
    if user_role_names <= {"Viewer"}:
        return False

    allowed: set[str] = _NOTIFICATION_ALLOWED_ROLES.get(notification_type, set())
    return bool(user_role_names & allowed)


def _enqueue(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Insert a pending email row.  Must be called inside a Flask app context
    and inside an active DB session (the caller's transaction is fine)."""
    try:
        db.session.add(OutboxEmail(to_email=to, subject=subject, body=body, html_body=html_body))
        db.session.flush()   # assign id without a separate commit
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to enqueue mail to %s — %s", to, exc)


# ── Assignment notifications ──────────────────────────────────────────────────

def send_assignment_confirmed(user: UserAccount, event: Event) -> None:
    """Notify a user that their spot assignment was confirmed."""
    if not user_can_receive_notification(user, "assignment"):
        return
    body = render_template(
        "email/assignment_confirmed.txt",
        user_name=user.name,
        event=event,
    )
    _enqueue(user.email, f"MedCover — Přihlášení na akci: {event.name}", body)


def send_assignment_released(user: UserAccount, event: Event) -> None:
    """Notify a user that their assignment was released (by themselves or coordinator)."""
    if not user_can_receive_notification(user, "assignment"):
        return
    body = render_template(
        "email/assignment_released.txt",
        user_name=user.name,
        event=event,
    )
    _enqueue(user.email, f"MedCover — Odhlášení z akce: {event.name}", body)


# ── Event lifecycle notifications ─────────────────────────────────────────────

def send_event_published(user: UserAccount, event: Event) -> None:
    """Notify a user that an event they might be interested in was published."""
    if not user_can_receive_notification(user, "event_lifecycle"):
        return
    body = render_template(
        "email/event_published.txt",
        user_name=user.name,
        event=event,
    )
    _enqueue(user.email, f"MedCover — Nová akce: {event.name}", body)


def send_assignments_opened(user: UserAccount, event: Event) -> None:
    """Notify a user that assignments opened for an event."""
    if not user_can_receive_notification(user, "event_lifecycle"):
        return
    body = render_template(
        "email/assignments_opened.txt",
        user_name=user.name,
        event=event,
    )
    _enqueue(user.email, f"MedCover — Otevřeny přihlášky: {event.name}", body)


def send_event_cancelled(user: UserAccount, event: Event) -> None:
    """Notify an assigned user that an event was cancelled."""
    if not user_can_receive_notification(user, "event_cancelled"):
        return
    body = render_template(
        "email/event_cancelled.txt",
        user_name=user.name,
        event=event,
    )
    _enqueue(user.email, f"MedCover — Akce zrušena: {event.name}", body)


# ── Reminder (scheduler) ──────────────────────────────────────────────────────

def send_unfilled_spots_reminder(
    user: UserAccount,
    event: Event,
    unfilled: list,
) -> None:
    """Remind coordinator/RP that an event still has unfilled spots."""
    if not user_can_receive_notification(user, "unfilled_reminder"):
        return
    body = render_template(
        "email/unfilled_spots_reminder.txt",
        coordinator_name=user.name,
        event=event,
        unfilled=len(unfilled) if isinstance(unfilled, list) else unfilled,
    )
    _enqueue(
        user.email,
        f"MedCover — Připomínka: volná místa na akci {event.name}",
        body,
    )


# ── Admin digest ──────────────────────────────────────────────────────────────

def send_admin_digest(recipient_email: str, subject: str, html_body: str) -> None:
    """Enqueue a digest email to a single recipient.

    Plain-text fallback is a minimal message directing the user to an HTML-capable client.
    """
    plain_fallback = "Tento e-mail obsahuje formátovaný obsah. Otevřete jej v e-mailovém klientovi s podporou HTML."
    _enqueue(recipient_email, subject, plain_fallback, html_body=html_body)


# ── Outbox drain (callable from tests and scheduler) ─────────────────────────


def _write_failure_audit(row: OutboxEmail) -> None:
    """Write an AuditLogEntry when an outbox email permanently fails.
    Called inside the active DB session — no commit here."""
    from app.models.audit import AuditLogEntry
    try:
        db.session.add(AuditLogEntry(
            actor_id=None,
            action_type="email_failed",
            entity_type="OutboxEmail",
            entity_id=str(row.id),
            summary=f"E-mail pro {row.to_email} se nepodařilo odeslat po {row.retry_count} pokusech: {row.last_error}",
            changes_json={"to": row.to_email, "subject": row.subject, "error": row.last_error},
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to write failure audit log for outbox id=%d — %s", row.id, exc)


def drain_one_outbox_email() -> bool:
    """Send the oldest pending outbox row within the current app context.

    Returns True if a row was processed (sent or failed), False if the queue
    was empty.  Designed to be called from both the scheduler and tests.
    """
    from app.extensions import mail as _mail
    from flask_mail import Message

    row: OutboxEmail | None = db.session.scalars(
        db.select(OutboxEmail)
        .where(
            OutboxEmail.status == "pending",
            OutboxEmail.retry_count < OutboxEmail.MAX_RETRIES,
        )
        .order_by(OutboxEmail.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()

    if row is None:
        return False

    # --- Dev email block check ---
    from app.models.settings import get_settings as _get_settings
    _settings = _get_settings()
    if not _settings.is_email_allowed(row.to_email):
        row.status = "skipped"
        row.last_error = "dev_email_block: recipient not in allowlist"
        db.session.commit()
        log.warning(
            "Mail suppressed (dev_email_block): id=%d to=%s subject=%r",
            row.id, row.to_email, row.subject,
        )
        return True

    try:
        msg = Message(subject=row.subject, recipients=[row.to_email], body=row.body)
        if row.html_body:
            msg.html = row.html_body
        _mail.send(msg)
        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)
        log.info("Mail sent: id=%d to=%s subject=%r", row.id, row.to_email, row.subject)
    except Exception as exc:  # noqa: BLE001
        row.retry_count += 1
        row.last_error = str(exc)
        if row.retry_count >= OutboxEmail.MAX_RETRIES:
            row.status = "failed"
            log.error(
                "Mail permanently failed: id=%d to=%s — %s (after %d retries)",
                row.id, row.to_email, exc, row.retry_count,
            )
            _write_failure_audit(row)
        else:
            log.warning(
                "Mail send failed (attempt %d/%d): id=%d to=%s — %s",
                row.retry_count, OutboxEmail.MAX_RETRIES, row.id, row.to_email, exc,
            )

    db.session.commit()
    return True


# ── Debriefing invitation ─────────────────────────────────────────────────────

def send_debriefing_invitation(assignment: Assignment, event: Event) -> None:
    """Send a debriefing invitation email to the assigned user."""
    user = assignment.user
    if not user_can_receive_notification(user, "assignment"):
        return
    from flask import url_for
    debriefing_url = url_for(
        "debriefing.submit",
        assignment_id=assignment.id,
        _external=True,
    )
    body = render_template(
        "email/debriefing_invitation.txt",
        user_name=user.name,
        event=event,
        debriefing_url=debriefing_url,
    )
    _enqueue(user.email, f"MedCover — Výjezdová zpráva: {event.name}", body)
