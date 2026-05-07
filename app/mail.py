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
    from app.models.event import Event

log = logging.getLogger(__name__)


def _enqueue(to: str, subject: str, body: str) -> None:
    """Insert a pending email row.  Must be called inside a Flask app context
    and inside an active DB session (the caller's transaction is fine)."""
    try:
        db.session.add(OutboxEmail(to_email=to, subject=subject, body=body))
        db.session.flush()   # assign id without a separate commit
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to enqueue mail to %s — %s", to, exc)


# ── Assignment notifications ──────────────────────────────────────────────────

def send_assignment_confirmed(user_email: str, user_name: str, event: Event) -> None:
    """Notify a user that their spot assignment was confirmed."""
    body = render_template(
        "email/assignment_confirmed.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Přihlášení na akci: {event.name}", body)


def send_assignment_released(user_email: str, user_name: str, event: Event) -> None:
    """Notify a user that their assignment was released (by themselves or coordinator)."""
    body = render_template(
        "email/assignment_released.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Odhlášení z akce: {event.name}", body)


# ── Event lifecycle notifications ─────────────────────────────────────────────

def send_event_published(user_email: str, user_name: str, event: Event) -> None:
    """Notify a user that an event they might be interested in was published."""
    body = render_template(
        "email/event_published.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Nová akce: {event.name}", body)


def send_assignments_opened(user_email: str, user_name: str, event: Event) -> None:
    """Notify a user that assignments opened for an event."""
    body = render_template(
        "email/assignments_opened.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Otevřeny přihlášky: {event.name}", body)


def send_event_cancelled(user_email: str, user_name: str, event: Event) -> None:
    """Notify assigned users that an event was cancelled."""
    body = render_template(
        "email/event_cancelled.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Akce zrušena: {event.name}", body)


# ── Reminder (scheduler) ──────────────────────────────────────────────────────

def send_unfilled_spots_reminder(
    coordinator_email: str,
    coordinator_name: str,
    event: Event,
    unfilled: int,
) -> None:
    """Remind coordinator/RP that an event still has unfilled spots."""
    body = render_template(
        "email/unfilled_spots_reminder.txt",
        coordinator_name=coordinator_name,
        event=event,
        unfilled=unfilled,
    )
    _enqueue(
        coordinator_email,
        f"MedCover — Připomínka: volná místa na akci {event.name}",
        body,
    )


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

    try:
        msg = Message(subject=row.subject, recipients=[row.to_email], body=row.body)
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
