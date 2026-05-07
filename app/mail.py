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

import logging

from flask import render_template

from app.extensions import db
from app.models.outbox import OutboxEmail

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

def send_assignment_confirmed(user_email: str, user_name: str, event) -> None:
    """Notify a user that their spot assignment was confirmed."""
    body = render_template(
        "email/assignment_confirmed.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Přihlášení na akci: {event.name}", body)


def send_assignment_released(user_email: str, user_name: str, event) -> None:
    """Notify a user that their assignment was released (by themselves or coordinator)."""
    body = render_template(
        "email/assignment_released.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Odhlášení z akce: {event.name}", body)


# ── Event lifecycle notifications ─────────────────────────────────────────────

def send_event_published(user_email: str, user_name: str, event) -> None:
    """Notify a user that an event they might be interested in was published."""
    body = render_template(
        "email/event_published.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Nová akce: {event.name}", body)


def send_assignments_opened(user_email: str, user_name: str, event) -> None:
    """Notify a user that assignments opened for an event."""
    body = render_template(
        "email/assignments_opened.txt",
        user_name=user_name,
        event=event,
    )
    _enqueue(user_email, f"MedCover — Otevřeny přihlášky: {event.name}", body)


def send_event_cancelled(user_email: str, user_name: str, event) -> None:
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
    event,
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
