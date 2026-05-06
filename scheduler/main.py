import schedule
import time
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = create_app("production")


def open_assignments() -> None:
    """Auto-transition Events from Published → Assignments Open at assignments_open_at."""
    with app.app_context():
        log.info("TODO: open_assignments task")


def close_completed_events() -> None:
    """Auto-transition Events from Assignments Closed → Completed after end_datetime."""
    with app.app_context():
        log.info("TODO: close_completed_events task")


def send_reminders() -> None:
    """Send unfilled-spot reminder emails per each Event's reminder_schedule."""
    with app.app_context():
        log.info("TODO: send_reminders task")


def send_admin_digest() -> None:
    """Send daily admin digest email."""
    with app.app_context():
        log.info("TODO: send_admin_digest task")


schedule.every(1).minutes.do(open_assignments)
schedule.every(1).minutes.do(close_completed_events)
schedule.every(1).minutes.do(send_reminders)
schedule.every().day.at("07:00").do(send_admin_digest)

log.info("Scheduler started")

while True:
    schedule.run_pending()
    time.sleep(30)
