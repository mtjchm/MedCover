from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped
from app.extensions import db

if TYPE_CHECKING:
    from app.models.user import UserAccount


class Assignment(db.Model):  # type: ignore[misc]
    __tablename__ = "assignment"

    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey("event_spot.id"), unique=True, nullable=False)
    user_id = db.Column(db.Uuid, db.ForeignKey("user_account.id"), nullable=False)
    assigned_by_id = db.Column(db.Uuid, db.ForeignKey("user_account.id"), nullable=True)
    assigned_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    spot = db.relationship("EventSpot", back_populates="assignment")
    user: Mapped[UserAccount] = db.relationship("UserAccount", foreign_keys=[user_id])
    assigned_by: Mapped[UserAccount | None] = db.relationship("UserAccount", foreign_keys=[assigned_by_id])
    debriefing: Mapped[DebriefingRecord | None] = db.relationship(
        "DebriefingRecord", back_populates="assignment", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Assignment spot={self.spot_id} user={self.user_id}>"


class DebriefingRecord(db.Model):  # type: ignore[misc]
    __tablename__ = "debriefing_record"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), unique=True, nullable=False)
    submitted_by_id = db.Column(db.Uuid, db.ForeignKey("user_account.id"), nullable=False)
    actual_hours = db.Column(db.Numeric(5, 2), nullable=False)
    patients_treated = db.Column(db.Integer, default=0, nullable=False)
    materials_used = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    assignment = db.relationship("Assignment", back_populates="debriefing")
    submitted_by = db.relationship("UserAccount", foreign_keys=[submitted_by_id])

    def __repr__(self) -> str:
        return f"<DebriefingRecord assignment={self.assignment_id}>"
