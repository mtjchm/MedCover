import schedule
import time
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

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

    Called every MAIL_QUEUE_INTERVAL_SECONDS (default 6 s).  Delegates to
    app.mail.drain_one_outbox_email which contains the actual logic and can
    also be called directly in tests without importing the scheduler.
    """
    with app.app_context():
        from app.mail import drain_one_outbox_email
        drain_one_outbox_email()


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
    """Send unfilled-spot reminder emails for events whose reminder window has arrived.

    Delegates to app.scheduler_tasks.run_send_reminders for the core logic so
    that it can be tested without importing this module.
    """
    with app.app_context():
        from app.extensions import db
        from app.scheduler_tasks import run_send_reminders
        run_send_reminders(db.session)


def send_admin_digest_task() -> None:
    """Send admin digest if it is due per DigestSchedule."""
    with app.app_context():
        from app.extensions import db
        from app.scheduler_tasks import run_admin_digest
        run_admin_digest(db.session)


def record_metrics() -> None:
    """Record outbox queue depth snapshot every 15 minutes."""
    with app.app_context():
        from app.extensions import db
        from app.scheduler_tasks import run_record_metrics
        run_record_metrics(db.session)


schedule.every(MAIL_QUEUE_INTERVAL_SECONDS).seconds.do(process_email_queue)
schedule.every(1).minutes.do(open_assignments)
schedule.every(1).minutes.do(close_completed_events)
schedule.every(5).minutes.do(send_reminders)
schedule.every(1).minutes.do(send_admin_digest_task)
schedule.every(15).minutes.do(record_metrics)

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
    # Also touch a local file so Docker healthcheck can verify without a DB query
    try:
        Path("/tmp/scheduler_heartbeat").touch()
    except Exception:
        pass
    time.sleep(5)  # short sleep so email queue is drained promptly
