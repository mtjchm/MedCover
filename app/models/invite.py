from __future__ import annotations

import uuid
from datetime import datetime, timezone
from app.extensions import db


class RegistrationInvite(db.Model):  # type: ignore[misc]
    __tablename__ = "registration_invite"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: uuid.uuid4().hex)
    email = db.Column(db.String(255), nullable=False)
    created_by_id = db.Column(db.Uuid, db.ForeignKey("user_account.id"), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_by = db.relationship("UserAccount", foreign_keys=[created_by_id])

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    def __repr__(self) -> str:
        return f"<RegistrationInvite {self.email} used={self.is_used}>"
