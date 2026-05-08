"""Tests for the admin digest feature."""
from __future__ import annotations

import re
import sqlalchemy as sa

from app.extensions import db
from app.models.digest import DigestBlock, DigestMetricSnapshot, DigestSchedule, get_digest_schedule


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_csrf(client) -> str:
    """Extract CSRF token from the digest settings page."""
    resp = client.get("/admin/digest/")
    m = re.search(rb'name="csrf_token" value="([^"]+)"', resp.data)
    return m.group(1).decode() if m else ""


# ── render_digest ─────────────────────────────────────────────────────────────

def test_render_digest_returns_html(app: object) -> None:
    """render_digest should return non-empty HTML with the outer frame."""
    from app.digest.renderer import render_digest

    with app.app_context():
        schedule = get_digest_schedule()
        html = render_digest(db.session)

    assert "<!DOCTYPE html>" in html
    assert schedule.email_subject in html


def test_render_digest_includes_enabled_blocks(app: object) -> None:
    """Enabled blocks should appear in the rendered digest."""
    from app.digest.renderer import render_digest

    with app.app_context():
        schedule = get_digest_schedule()
        block = db.session.scalar(
            sa.select(DigestBlock).where(
                DigestBlock.digest_schedule_id == schedule.id,
                DigestBlock.block_type == "server_stats",
            )
        )
        block.enabled = True
        db.session.commit()

        html = render_digest(db.session)
        title = block.config_json.get("title", "Servisní statistiky")

    assert title in html


def test_render_digest_skips_disabled_blocks(app: object) -> None:
    """Disabled blocks should not appear in the rendered digest."""
    from app.digest.renderer import render_digest

    with app.app_context():
        schedule = get_digest_schedule()
        block = db.session.scalar(
            sa.select(DigestBlock).where(
                DigestBlock.digest_schedule_id == schedule.id,
                DigestBlock.block_type == "free_text",
            )
        )
        block.enabled = False
        block.config_json = {"title": "UNIQUE_TITLE_XYZ_FREE_TEXT", "content": "hello"}
        db.session.commit()

        html = render_digest(db.session)

    assert "UNIQUE_TITLE_XYZ_FREE_TEXT" not in html


# ── run_record_metrics ────────────────────────────────────────────────────────

def test_run_record_metrics_inserts_snapshot(app: object) -> None:
    """run_record_metrics should insert a DigestMetricSnapshot row."""
    from app.scheduler_tasks import run_record_metrics
    from datetime import datetime, timezone

    with app.app_context():
        now = datetime.now(timezone.utc)
        run_record_metrics(db.session, now=now)
        snap = db.session.scalar(
            sa.select(DigestMetricSnapshot).where(
                DigestMetricSnapshot.metric_name == "outbox_pending_count",
                DigestMetricSnapshot.snapshot_at == now,
            )
        )
        assert snap is not None
        assert snap.metric_value >= 0


def test_run_record_metrics_prunes_old_rows(app: object) -> None:
    """run_record_metrics should delete snapshots older than 30 days."""
    from app.scheduler_tasks import run_record_metrics
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        db.session.add(DigestMetricSnapshot(
            snapshot_at=old_time,
            metric_name="outbox_pending_count",
            metric_value=5.0,
        ))
        db.session.commit()

        run_record_metrics(db.session, now=datetime.now(timezone.utc))

        old = db.session.scalar(
            sa.select(DigestMetricSnapshot).where(DigestMetricSnapshot.snapshot_at == old_time)
        )
        assert old is None


# ── run_admin_digest ──────────────────────────────────────────────────────────

def test_run_admin_digest_skips_when_disabled(app: object) -> None:
    """run_admin_digest should return False when schedule.enabled is False."""
    from app.scheduler_tasks import run_admin_digest
    from datetime import datetime, timezone

    with app.app_context():
        schedule = get_digest_schedule()
        schedule.enabled = False
        db.session.commit()
        now = datetime(2025, 1, 1, schedule.preferred_hour_utc, 0, tzinfo=timezone.utc)
        result = run_admin_digest(db.session, now=now)

    assert result is False


def test_run_admin_digest_skips_wrong_hour(app: object) -> None:
    """run_admin_digest should skip if current hour != preferred_hour_utc."""
    from app.scheduler_tasks import run_admin_digest
    from datetime import datetime, timezone

    with app.app_context():
        schedule = get_digest_schedule()
        schedule.enabled = True
        schedule.preferred_hour_utc = 7
        schedule.last_sent_at = None
        db.session.commit()
        wrong_hour = 8  # 7 + 1
        now = datetime(2025, 1, 1, wrong_hour, 0, tzinfo=timezone.utc)
        result = run_admin_digest(db.session, now=now)

    assert result is False


def test_run_admin_digest_skips_too_soon(app: object) -> None:
    """run_admin_digest should skip if last_sent_at is too recent."""
    from app.scheduler_tasks import run_admin_digest
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        schedule = get_digest_schedule()
        hour = schedule.preferred_hour_utc
        now = datetime(2025, 6, 1, hour, 0, tzinfo=timezone.utc)
        schedule.enabled = True
        schedule.last_sent_at = now - timedelta(hours=schedule.frequency_hours - 1)
        db.session.commit()
        result = run_admin_digest(db.session, now=now)

    assert result is False


def test_run_admin_digest_enqueues_when_due(app: object, admin_client: object) -> None:
    """run_admin_digest should enqueue emails when schedule is enabled and due."""
    from app.scheduler_tasks import run_admin_digest
    from app.models.outbox import OutboxEmail
    from datetime import datetime, timezone

    with app.app_context():
        schedule = get_digest_schedule()
        hour = schedule.preferred_hour_utc
        now = datetime(2025, 6, 1, hour, 0, tzinfo=timezone.utc)
        schedule.enabled = True
        schedule.last_sent_at = None
        db.session.commit()

        result = run_admin_digest(db.session, now=now)
        assert result is True

        outbox = db.session.scalars(
            sa.select(OutboxEmail).where(OutboxEmail.to_email == "admin@test.com")
        ).all()

    assert len(outbox) >= 1
    assert outbox[0].html_body is not None


# ── Routes ────────────────────────────────────────────────────────────────────

def test_digest_preview_returns_html(app: object, admin_client: object) -> None:
    """GET /admin/digest/preview should return 200 with HTML content."""
    with app.app_context():
        get_digest_schedule()  # seed

    resp = admin_client.get("/admin/digest/preview")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data


def test_digest_settings_page_ok(app: object, admin_client: object) -> None:
    """GET /admin/digest/ should return 200."""
    with app.app_context():
        get_digest_schedule()  # seed

    resp = admin_client.get("/admin/digest/")
    assert resp.status_code == 200


def test_digest_save_persists(app: object, admin_client: object) -> None:
    """POST /admin/digest/save should update DigestSchedule fields."""
    with app.app_context():
        schedule = get_digest_schedule()
        version = schedule.version

    csrf = _get_csrf(admin_client)
    resp = admin_client.post("/admin/digest/save", data={
        "csrf_token": csrf,
        "enabled": "1",
        "frequency_hours": "12",
        "preferred_hour_utc": "8",
        "email_subject": "Test Subject",
        "version": str(version),
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        updated = db.session.get(DigestSchedule, 1)
        assert updated.frequency_hours == 12
        assert updated.email_subject == "Test Subject"


def test_digest_requires_permission(app: object, member_client: object) -> None:
    """Non-admin user should get 403 on digest routes."""
    resp = member_client.get("/admin/digest/")
    assert resp.status_code == 403
