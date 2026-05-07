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
    """Send unfilled-spot reminder emails per each Event's reminder_schedule."""
    with app.app_context():
        log.info("TODO: send_reminders task (Phase 3 email)")


def send_admin_digest() -> None:
    """Send daily admin digest email."""
    with app.app_context():
        log.info("TODO: send_admin_digest task (Phase 3 email)")


schedule.every(1).minutes.do(open_assignments)
schedule.every(1).minutes.do(close_completed_events)
schedule.every(5).minutes.do(send_reminders)
schedule.every().day.at("07:00").do(send_admin_digest)

log.info("Scheduler started")

while True:
    schedule.run_pending()
    time.sleep(30)

