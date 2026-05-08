"""
Testable scheduler task implementations.

The scheduler (scheduler/main.py) delegates its core logic here so that
tests can call these functions directly with the test app context, without
importing or patching the scheduler module itself.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa

log = logging.getLogger(__name__)


def run_send_reminders(db_session: Any, now: datetime | None = None) -> int:
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
        sa.select(Event).where(
            Event.status == EventStatus.ASSIGNMENTS_OPEN,
            Event.archived == False,  # noqa: E712
            Event.start_datetime > now,
        )
    ).all()

    total_sent = 0
    for event in events:
        unfilled = event.unfilled_spots
        if not unfilled:
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

            # Collect unique recipient User objects: RP and/or ME coordinator
            recipients: set = set()
            if event.responsible_person:
                recipients.add(event.responsible_person)
            if event.master_event and event.master_event.coordinator:
                recipients.add(event.master_event.coordinator)

            for user in recipients:
                send_unfilled_spots_reminder(user, event, unfilled)
                log.info("Reminder sent for event id=%s (%sh before) to %s", event.id, hours, user.email)
                total_sent += 1

            sent_map[key] = now.isoformat()
            changed = True

        if changed:
            event.reminder_sent_json = sent_map
            db_session.commit()

    return total_sent


def run_record_metrics(db_session: Any, now: datetime | None = None) -> None:
    """Record a snapshot of current outbox queue depth for peak tracking.

    Called by the scheduler every ~15 minutes.  Rows older than 30 days
    are pruned in the same call.
    """
    from app.models.digest import DigestMetricSnapshot
    from app.models.outbox import OutboxEmail

    if now is None:
        now = datetime.now(timezone.utc)

    pending = db_session.scalar(
        sa.select(sa.func.count()).select_from(OutboxEmail)
        .where(OutboxEmail.status == "pending")
    ) or 0

    db_session.add(DigestMetricSnapshot(
        snapshot_at=now,
        metric_name="outbox_pending_count",
        metric_value=float(pending),
    ))

    cutoff = now - timedelta(days=30)
    db_session.execute(
        sa.delete(DigestMetricSnapshot).where(DigestMetricSnapshot.snapshot_at < cutoff)
    )
    db_session.commit()
    log.debug("Metric snapshot: outbox_pending_count=%d", pending)


def run_admin_digest(db_session: Any, now: datetime | None = None) -> bool:
    """Send the admin digest if it is due according to DigestSchedule.

    Returns True if the digest was enqueued, False if skipped.
    """
    from app.models.digest import get_digest_schedule
    from app.digest.renderer import render_digest
    from app.mail import send_admin_digest, user_can_receive_notification
    from app.models.user import UserAccount

    if now is None:
        now = datetime.now(timezone.utc)

    schedule = get_digest_schedule()

    if not schedule.enabled:
        return False

    if now.hour != schedule.preferred_hour_utc:
        return False

    if schedule.last_sent_at is not None:
        elapsed = (now - schedule.last_sent_at).total_seconds()
        if elapsed < schedule.frequency_hours * 3600:
            return False

    recipients = db_session.scalars(
        sa.select(UserAccount).where(UserAccount.is_active == True)  # noqa: E712
    ).all()
    eligible = [u for u in recipients if user_can_receive_notification(u, "admin_digest")]

    if not eligible:
        log.info("Admin digest: no eligible recipients, skipping.")
        schedule.last_sent_at = now
        db_session.commit()
        return False

    html = render_digest(db_session)
    for user in eligible:
        send_admin_digest(user.email, schedule.email_subject, html)
        log.info("Admin digest enqueued for %s", user.email)

    schedule.last_sent_at = now
    db_session.commit()
    return True
