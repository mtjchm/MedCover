"""
Testable scheduler task implementations.

The scheduler (scheduler/main.py) delegates its core logic here so that
tests can call these functions directly with the test app context, without
importing or patching the scheduler module itself.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def run_send_reminders(db_session: Session, now: datetime | None = None) -> int:
    """Check all ASSIGNMENTS_OPEN events and send reminder emails where due.

    Args:
        db_session: An active SQLAlchemy session bound to the current app context.
        now:        The reference timestamp (default: utcnow). Pass an explicit
                    value in tests to control timing.

    Returns:
        Number of reminder emails enqueued.
    """
    from app.models.event import Event, EventStatus
    from app.mail import send_unfilled_spots_reminder

    if now is None:
        now = datetime.now(timezone.utc)

    events = db_session.scalars(
        db_session.query(Event).where(
            Event.status == EventStatus.ASSIGNMENTS_OPEN,
            Event.archived == False,  # noqa: E712
            Event.start_datetime > now,
        )
    ).all()

    total_sent = 0
    for event in events:
        unfilled = event.mandatory_total_spots - event.mandatory_filled_spots
        if unfilled <= 0:
            continue

        sent_map: dict = event.reminder_sent_json or {}
        changed = False

        for hours in event.reminder_hours():
            key = str(hours)
            if key in sent_map:
                continue  # already sent for this offset
            window_open_at = event.start_datetime - timedelta(hours=hours)
            if now < window_open_at:
                continue  # not yet time

            # Collect recipients: RP and/or coordinator
            recipients: set[tuple[str, str]] = set()
            if event.responsible_person:
                recipients.add((event.responsible_person.email, event.responsible_person.name))
            if event.master_event and event.master_event.coordinator:
                recipients.add((event.master_event.coordinator.email, event.master_event.coordinator.name))

            for email, name in recipients:
                send_unfilled_spots_reminder(email, name, event, unfilled)
                log.info("Reminder sent for event id=%s (%sh before) to %s", event.id, hours, email)
                total_sent += 1

            sent_map[key] = now.isoformat()
            changed = True

        if changed:
            event.reminder_sent_json = sent_map
            db_session.commit()

    return total_sent
