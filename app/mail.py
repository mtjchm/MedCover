"""
Centralised email helper for MedCover.

Usage (inside a Flask app context):
    from app.mail import send_assignment_confirmed, send_event_published, ...

All functions are fire-and-forget — exceptions are logged, never raised.
This keeps callers simple and avoids breaking the main request flow.
"""

import logging
from typing import Optional

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail

log = logging.getLogger(__name__)


def _send(to: str, subject: str, body: str) -> None:
    msg = Message(subject=subject, recipients=[to], body=body)
    try:
        mail.send(msg)
    except Exception as exc:  # noqa: BLE001
        log.warning("Mail send failed to %s — %s", to, exc)


# ── Assignment notifications ──────────────────────────────────────────────────

def send_assignment_confirmed(user_email: str, user_name: str, event) -> None:
    """Notify a user that their spot assignment was confirmed."""
    body = render_template(
        "email/assignment_confirmed.txt",
        user_name=user_name,
        event=event,
    )
    _send(user_email, f"MedCover — Přihlášení na akci: {event.name}", body)


def send_assignment_released(user_email: str, user_name: str, event) -> None:
    """Notify a user that their assignment was released (by themselves or coordinator)."""
    body = render_template(
        "email/assignment_released.txt",
        user_name=user_name,
        event=event,
    )
    _send(user_email, f"MedCover — Odhlášení z akce: {event.name}", body)


# ── Event lifecycle notifications ─────────────────────────────────────────────

def send_event_published(user_email: str, user_name: str, event) -> None:
    """Notify a user that an event they might be interested in was published."""
    body = render_template(
        "email/event_published.txt",
        user_name=user_name,
        event=event,
    )
    _send(user_email, f"MedCover — Nová akce: {event.name}", body)


def send_assignments_opened(user_email: str, user_name: str, event) -> None:
    """Notify a user that assignments opened for an event."""
    body = render_template(
        "email/assignments_opened.txt",
        user_name=user_name,
        event=event,
    )
    _send(user_email, f"MedCover — Otevřeny přihlášky: {event.name}", body)


def send_event_cancelled(user_email: str, user_name: str, event) -> None:
    """Notify assigned users that an event was cancelled."""
    body = render_template(
        "email/event_cancelled.txt",
        user_name=user_name,
        event=event,
    )
    _send(user_email, f"MedCover — Akce zrušena: {event.name}", body)


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
    _send(
        coordinator_email,
        f"MedCover — Připomínka: volná místa na akci {event.name}",
        body,
    )
