import schedule
import time
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = create_app("production")

# Sentinel user ID used in audit log rows written by the scheduler (no human actor)
SCHEDULER_ACTOR_ID = None

# How long to wait between individual SMTP sends (seconds).
# 6 s ≈ 10 emails/min — safely under typical relay limits (e.g. MS365: 30/min).
MAIL_QUEUE_INTERVAL_SECONDS: int = int(os.environ.get("MAIL_QUEUE_INTERVAL_SECONDS", "6"))


def process_email_queue() -> None:
    """Drain the outbox_email queue one message at a time.

    Called every MAIL_QUEUE_INTERVAL_SECONDS (default 6 s).  Picks the oldest
    pending (or retriable failed) row, attempts SMTP delivery, then marks it
    sent or increments the retry counter.  After MAX_RETRIES failures the row
    is permanently marked 'failed' so it can be inspected by an admin.
    """
    with app.app_context():
        from app.extensions import db, mail
        from app.models.outbox import OutboxEmail
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
            return

        try:
            msg = Message(subject=row.subject, recipients=[row.to_email], body=row.body)
            mail.send(msg)
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
            else:
                log.warning(
                    "Mail send failed (attempt %d/%d): id=%d to=%s — %s",
                    row.retry_count, OutboxEmail.MAX_RETRIES, row.id, row.to_email, exc,
                )

        db.session.commit()


def open_assignments() -> None:
    """Auto-transition Events from Published → Assignments Open when assignments_open_datetime has passed."""
    with app.app_context():
        from app.extensions import db
        from app.models.event import Event, EventStatus
        from app.models.audit import AuditLogEntry

        now = datetime.now(timezone.utc)
        events = db.session.scalars(
            db.select(Event).where(
                Event.status == EventStatus.PUBLISHED,
                Event.assignments_open_datetime != None,  # noqa: E711
                Event.assignments_open_datetime <= now,
            )
        ).all()

        for event in events:
            event.status = EventStatus.ASSIGNMENTS_OPEN
            event.version += 1
            db.session.add(AuditLogEntry(
                actor_id=SCHEDULER_ACTOR_ID,
                action_type="status_change",
                entity_type="Event",
                entity_id=str(event.id),
                summary=f"[Scheduler] Přihlašování automaticky otevřeno pro akci '{event.name}'",
            ))
            log.info("Opened assignments for event id=%s name=%r", event.id, event.name)

        if events:
            db.session.commit()
            log.info("open_assignments: processed %d event(s)", len(events))


def close_completed_events() -> None:
    """Auto-transition Events from Assignments Open/Closed → Completed after end_datetime."""
    with app.app_context():
        from app.extensions import db
        from app.models.event import Event, EventStatus
        from app.models.audit import AuditLogEntry

        now = datetime.now(timezone.utc)
        events = db.session.scalars(
            db.select(Event).where(
                Event.status.in_([EventStatus.ASSIGNMENTS_OPEN, EventStatus.ASSIGNMENTS_CLOSED]),
                Event.end_datetime <= now,
                Event.archived == False,  # noqa: E712
            )
        ).all()

        for event in events:
            event.status = EventStatus.COMPLETED
            event.archived = True
            event.version += 1
            db.session.add(AuditLogEntry(
                actor_id=SCHEDULER_ACTOR_ID,
                action_type="status_change",
                entity_type="Event",
                entity_id=str(event.id),
                summary=f"[Scheduler] Akce '{event.name}' automaticky dokončena po skončení termínu",
            ))
            log.info("Completed event id=%s name=%r", event.id, event.name)

        if events:
            db.session.commit()
            log.info("close_completed_events: processed %d event(s)", len(events))


def send_reminders() -> None:
    """Send unfilled-spot reminder emails to coordinator/RP for open events."""
    with app.app_context():
        from app.extensions import db
        from app.models.event import Event, EventStatus
        from app.mail import send_unfilled_spots_reminder

        events = db.session.scalars(
            db.select(Event).where(
                Event.status == EventStatus.ASSIGNMENTS_OPEN,
                Event.archived == False,  # noqa: E712
            )
        ).all()

        for event in events:
            unfilled = event.total_spots - event.filled_spots
            if unfilled <= 0:
                continue
            # Notify coordinator (ME) and/or RP
            recipients: set[tuple[str, str]] = set()
            if event.responsible_person:
                recipients.add((event.responsible_person.email, event.responsible_person.name))
            if event.master_event and event.master_event.coordinator:
                recipients.add((event.master_event.coordinator.email, event.master_event.coordinator.name))
            for email, name in recipients:
                send_unfilled_spots_reminder(email, name, event, unfilled)
                log.info("Reminder sent for event id=%s to %s", event.id, email)


def send_admin_digest() -> None:
    """Send daily admin digest email."""
    with app.app_context():
        log.info("TODO: send_admin_digest task (Phase 3 email)")


schedule.every(MAIL_QUEUE_INTERVAL_SECONDS).seconds.do(process_email_queue)
schedule.every(1).minutes.do(open_assignments)
schedule.every(1).minutes.do(close_completed_events)
schedule.every(5).minutes.do(send_reminders)
schedule.every().day.at("07:00").do(send_admin_digest)

log.info("Scheduler started (mail queue interval: %ds)", MAIL_QUEUE_INTERVAL_SECONDS)

while True:
    schedule.run_pending()
    # Write heartbeat so the admin dashboard can confirm the scheduler is alive
    try:
        with app.app_context():
            from app.extensions import db
            from app.models.settings import get_settings
            s = get_settings()
            s.scheduler_last_seen = datetime.now(timezone.utc)
            db.session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("Heartbeat write failed: %s", exc)
    time.sleep(5)  # short sleep so email queue is drained promptly

