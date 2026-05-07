from __future__ import annotations

import uuid
import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from flask_login import UserMixin
from sqlalchemy.orm import Mapped
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.qualification import Qualification


class CalendarView(str, enum.Enum):
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    LIST = "list"


# Many-to-many: UserAccount ↔ Role
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Uuid, db.ForeignKey("user_account.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
)


class UserAccount(UserMixin, db.Model):  # type: ignore[misc]
    __tablename__ = "user_account"

    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    preferred_calendar_view = db.Column(
        db.Enum(CalendarView, name="calendar_view_enum"),
        default=CalendarView.LIST,
        nullable=False,
    )
    dashboard_horizon_days = db.Column(db.Integer, default=30, nullable=False, server_default="30")
    dark_mode = db.Column(db.Boolean, default=False, nullable=False, server_default="false")
    # Optimistic locking — increment on every write; catch StaleDataError → HTTP 409
    version = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    roles: Mapped[list[Role]] = db.relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )

    qualifications: Mapped[list[Qualification]] = db.relationship(
        "Qualification",
        secondary="user_qualifications",
        back_populates="holders",
        lazy="selectin",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_permission(self, code: str) -> bool:
        return any(p.code == code for role in self.roles for p in role.permissions)

    def has_any_permission(self, *codes: str) -> bool:
        owned = {p.code for role in self.roles for p in role.permissions}
        return bool(owned & set(codes))

    # Flask-Login: use str(uuid) as session token
    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:
        return f"<UserAccount {self.email}>"
