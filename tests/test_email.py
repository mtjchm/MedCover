"""
Tests for the email outbox pipeline and individual send_* helpers.

Strategy:
  - All tests use unittest.mock.patch to replace flask_mail.Mail.send so no
    real SMTP connection is made.
  - Tests verify that the correct OutboxEmail rows are created (subject,
    recipient, body keywords) and that the scheduler's process_email_queue
    function transitions rows through pending → sent / failed correctly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.extensions import db
from app.models.event import Event, EventStatus
from app.models.master_event import MasterEvent
from app.models.outbox import OutboxEmail


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_event(name: str = "Testovací akce") -> Event:
    me = MasterEvent(name="Obecné", description="")
    db.session.add(me)
    db.session.flush()
    event = Event(
        name=name,
        master_event_id=me.id,
        start_datetime=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
        end_datetime=datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc),
        address="Praha",
        status=EventStatus.ASSIGNMENTS_OPEN,
    )
    db.session.add(event)
    db.session.flush()
    return event


# ── Outbox enqueue tests ───────────────────────────────────────────────────────

class TestOutboxEnqueue:
    """Verify that send_* helpers enqueue the correct OutboxEmail rows."""

    def test_send_assignment_confirmed_enqueues_row(self, app):
        from app.mail import send_assignment_confirmed
        with app.app_context():
            event = _make_event("Závody 2026")
            send_assignment_confirmed("jan@test.cz", "Jan Novák", event)
            db.session.commit()

            rows = db.session.scalars(db.select(OutboxEmail)).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.to_email == "jan@test.cz"
            assert "Závody 2026" in row.subject
            assert row.status == "pending"
            assert "Jan Novák" in row.body

    def test_send_assignment_released_enqueues_row(self, app):
        from app.mail import send_assignment_released
        with app.app_context():
            event = _make_event("Závody 2026")
            send_assignment_released("jan@test.cz", "Jan Novák", event)
            db.session.commit()

            row = db.session.scalars(db.select(OutboxEmail)).first()
            assert row is not None
            assert "Odhlášení" in row.subject
            assert row.to_email == "jan@test.cz"

    def test_send_event_published_enqueues_row(self, app):
        from app.mail import send_event_published
        with app.app_context():
            event = _make_event("Letní festival")
            send_event_published("petra@test.cz", "Petra Svobodová", event)
            db.session.commit()

            row = db.session.scalars(db.select(OutboxEmail)).first()
            assert row is not None
            assert "Letní festival" in row.subject
            assert "petra@test.cz" == row.to_email

    def test_send_assignments_opened_enqueues_row(self, app):
        from app.mail import send_assignments_opened
        with app.app_context():
            event = _make_event("Maraton")
            send_assignments_opened("user@test.cz", "User Name", event)
            db.session.commit()

            row = db.session.scalars(db.select(OutboxEmail)).first()
            assert row is not None
            assert "Otevřeny" in row.subject

    def test_send_event_cancelled_enqueues_row(self, app):
        from app.mail import send_event_cancelled
        with app.app_context():
            event = _make_event("Zrušená akce")
            send_event_cancelled("user@test.cz", "User Name", event)
            db.session.commit()

            row = db.session.scalars(db.select(OutboxEmail)).first()
            assert row is not None
            assert "zrušena" in row.subject.lower()

    def test_send_unfilled_spots_reminder_enqueues_row(self, app):
        from app.mail import send_unfilled_spots_reminder
        with app.app_context():
            event = _make_event("Akce s mezerami")
            send_unfilled_spots_reminder(
                "coord@test.cz", "Koordinátor", event, unfilled=3
            )
            db.session.commit()

            row = db.session.scalars(db.select(OutboxEmail)).first()
            assert row is not None
            assert "coord@test.cz" == row.to_email
            assert "3" in row.body

    def test_multiple_enqueues_all_pending(self, app):
        """All enqueued rows start as 'pending'."""
        from app.mail import send_assignment_confirmed, send_event_cancelled
        with app.app_context():
            event = _make_event()
            send_assignment_confirmed("a@test.cz", "A", event)
            send_event_cancelled("b@test.cz", "B", event)
            db.session.commit()

            rows = db.session.scalars(db.select(OutboxEmail)).all()
            assert len(rows) == 2
            assert all(r.status == "pending" for r in rows)


# ── Scheduler queue processing tests ─────────────────────────────────────────

class TestProcessEmailQueue:
    """Verify the drain_one_outbox_email function transitions rows correctly."""

    def _seed_pending(self, app, to: str = "test@test.cz") -> int:
        with app.app_context():
            row = OutboxEmail(to_email=to, subject="Test", body="Tělo zprávy")
            db.session.add(row)
            db.session.commit()
            return row.id

    def test_successful_send_marks_row_sent(self, app):
        row_id = self._seed_pending(app)

        with app.app_context():
            with patch("flask_mail.Mail.send"):
                from app.mail import drain_one_outbox_email
                drain_one_outbox_email()

        with app.app_context():
            row = db.session.get(OutboxEmail, row_id)
            assert row.status == "sent"
            assert row.sent_at is not None
            assert row.retry_count == 0

    def test_smtp_failure_increments_retry_count(self, app):
        row_id = self._seed_pending(app)

        with app.app_context():
            with patch("flask_mail.Mail.send", side_effect=Exception("Connection refused")):
                from app.mail import drain_one_outbox_email
                drain_one_outbox_email()

        with app.app_context():
            row = db.session.get(OutboxEmail, row_id)
            assert row.status == "pending"
            assert row.retry_count == 1
            assert "Connection refused" in row.last_error

    def test_exhausted_retries_marks_row_failed(self, app):
        """After MAX_RETRIES failures the row must be permanently 'failed'."""
        with app.app_context():
            row = OutboxEmail(
                to_email="x@test.cz",
                subject="Test",
                body="...",
                retry_count=OutboxEmail.MAX_RETRIES - 1,
            )
            db.session.add(row)
            db.session.commit()
            row_id = row.id

        with app.app_context():
            with patch("flask_mail.Mail.send", side_effect=Exception("timeout")):
                from app.mail import drain_one_outbox_email
                drain_one_outbox_email()

        with app.app_context():
            row = db.session.get(OutboxEmail, row_id)
            assert row.status == "failed"
            assert row.retry_count == OutboxEmail.MAX_RETRIES
            # Permanent failure should produce an audit log entry
            from app.models.audit import AuditLogEntry
            entry = db.session.scalar(
                db.select(AuditLogEntry).where(
                    AuditLogEntry.entity_type == "OutboxEmail",
                    AuditLogEntry.action_type == "email_failed",
                    AuditLogEntry.entity_id == str(row_id),
                )
            )
            assert entry is not None
            assert "x@test.cz" in entry.summary

    def test_already_failed_rows_are_skipped(self, app):
        """Rows with status='failed' must never be retried."""
        with app.app_context():
            row = OutboxEmail(
                to_email="x@test.cz",
                subject="Test",
                body="...",
                status="failed",
                retry_count=OutboxEmail.MAX_RETRIES,
            )
            db.session.add(row)
            db.session.commit()

        with app.app_context():
            with patch("flask_mail.Mail.send") as mock_send:
                from app.mail import drain_one_outbox_email
                drain_one_outbox_email()

        mock_send.assert_not_called()

    def test_already_sent_rows_are_skipped(self, app):
        """Rows with status='sent' must never be re-delivered."""
        with app.app_context():
            row = OutboxEmail(
                to_email="x@test.cz",
                subject="Test",
                body="...",
                status="sent",
            )
            db.session.add(row)
            db.session.commit()

        with app.app_context():
            with patch("flask_mail.Mail.send") as mock_send:
                from app.mail import drain_one_outbox_email
                drain_one_outbox_email()

        mock_send.assert_not_called()

    def test_empty_queue_returns_false(self, app):
        """drain_one_outbox_email on an empty outbox must return False."""
        with app.app_context():
            with patch("flask_mail.Mail.send") as mock_send:
                from app.mail import drain_one_outbox_email
                result = drain_one_outbox_email()

        assert result is False
        mock_send.assert_not_called()

    def test_processes_oldest_row_first(self, app):
        """Rows must be delivered in FIFO order (oldest created_at first)."""
        with app.app_context():
            older = OutboxEmail(
                to_email="older@test.cz", subject="Starší", body="...",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            newer = OutboxEmail(
                to_email="newer@test.cz", subject="Novější", body="...",
                created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )
            db.session.add_all([newer, older])  # insert newer first intentionally
            db.session.commit()

        sent_recipients: list[str] = []

        def _capture_send(msg: object) -> None:
            sent_recipients.append(getattr(msg, "recipients", [None])[0])

        with app.app_context():
            with patch("flask_mail.Mail.send", side_effect=_capture_send):
                from app.mail import drain_one_outbox_email
                drain_one_outbox_email()  # processes one row per call

        assert sent_recipients == ["older@test.cz"]


# ── SMTP settings admin route tests ──────────────────────────────────────────

class TestSmtpAdminSettings:
    """Verify the admin settings page handles SMTP config correctly."""

    def test_settings_page_does_not_expose_smtp_password(self, admin_client):
        response = admin_client.get("/admin/settings/", follow_redirects=True)
        assert response.status_code == 200
        assert b"devpassword" not in response.data
        assert b"smtp_password_enc" not in response.data

    def test_smtp_not_configured_exits_nonzero(self, app):
        """CLI send-test-email must exit 1 when SMTP is not configured."""
        from click.testing import CliRunner
        with app.app_context():
            from app.models.settings import get_settings
            settings = get_settings()
            settings.smtp_server = None
            db.session.commit()

        runner = CliRunner()
        with app.app_context():
            cmd = app.cli.commands["send-test-email"]
            result = runner.invoke(cmd, ["nobody@test.cz"], catch_exceptions=False)

        assert result.exit_code != 0
        assert "SMTP" in result.output


# ── OutboxEmail model unit tests ──────────────────────────────────────────────

class TestOutboxEmailModel:
    """Unit tests for the OutboxEmail model itself."""

    def test_default_status_is_pending(self, app):
        with app.app_context():
            row = OutboxEmail(to_email="a@b.com", subject="S", body="B")
            db.session.add(row)
            db.session.commit()
            assert row.status == "pending"

    def test_default_retry_count_is_zero(self, app):
        with app.app_context():
            row = OutboxEmail(to_email="a@b.com", subject="S", body="B")
            db.session.add(row)
            db.session.commit()
            assert row.retry_count == 0

    def test_max_retries_constant(self):
        assert OutboxEmail.MAX_RETRIES == 3

    def test_repr(self, app):
        with app.app_context():
            row = OutboxEmail(to_email="a@b.com", subject="S", body="B")
            db.session.add(row)
            db.session.commit()
            assert "a@b.com" in repr(row)
            assert "pending" in repr(row)
