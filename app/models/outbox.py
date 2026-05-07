from datetime import datetime, timezone
from app.extensions import db


class OutboxEmail(db.Model):
    """Persistent email outbox — all outgoing emails are queued here and sent
    by the scheduler at a throttled rate (one per MAIL_QUEUE_INTERVAL_SECONDS)."""

    __tablename__ = "outbox_email"

    id = db.Column(db.Integer, primary_key=True)
    to_email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)

    # 'pending' → being picked up by scheduler
    # 'sent'    → successfully delivered to SMTP relay
    # 'failed'  → retry_count reached MAX_RETRIES; given up
    status = db.Column(db.String(16), nullable=False, default="pending", server_default="pending", index=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_error = db.Column(db.Text, nullable=True)

    MAX_RETRIES: int = 3

    def __repr__(self) -> str:
        return f"<OutboxEmail id={self.id} to={self.to_email!r} status={self.status}>"
