import enum
from datetime import datetime, timezone
from app.extensions import db


class EventStatus(str, enum.Enum):
    DRAFT = "Koncept"
    PUBLISHED = "Zveřejněná"
    ASSIGNMENTS_OPEN = "Přihlášky otevřeny"
    ASSIGNMENTS_CLOSED = "Přihlášky uzavřeny"
    COMPLETED = "Dokončena"
    CANCELLED = "Zrušena"


# M2M: EventSpot ↔ Credential (required credentials for a spot)
spot_credentials = db.Table(
    "spot_credentials",
    db.Column("spot_id", db.Integer, db.ForeignKey("event_spot.id"), primary_key=True),
    db.Column("credential_id", db.Integer, db.ForeignKey("credential.id"), primary_key=True),
)

# M2M: EventSpotTemplate ↔ Credential
spot_template_credentials = db.Table(
    "spot_template_credentials",
    db.Column("spot_template_id", db.Integer, db.ForeignKey("event_spot_template.id"), primary_key=True),
    db.Column("credential_id", db.Integer, db.ForeignKey("credential.id"), primary_key=True),
)


class EventTemplate(db.Model):
    __tablename__ = "event_template"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    paid = db.Column(db.Boolean, default=False, nullable=False)
    # Reminder schedule: list of hours-before-start values, stored as comma-separated ints
    # e.g. "24,48" means send reminders 24h and 48h before start
    reminder_schedule = db.Column(db.String(255), nullable=True, default="24")
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

    spot_templates = db.relationship(
        "EventSpotTemplate", back_populates="template", cascade="all, delete-orphan"
    )

    def reminder_hours(self) -> list[int]:
        if not self.reminder_schedule:
            return [24]
        return [int(h) for h in self.reminder_schedule.split(",") if h.strip().isdigit()]

    def __repr__(self) -> str:
        return f"<EventTemplate {self.name}>"


class EventSpotTemplate(db.Model):
    __tablename__ = "event_spot_template"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("event_template.id"), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    template = db.relationship("EventTemplate", back_populates="spot_templates")
    required_credentials = db.relationship(
        "Credential", secondary=spot_template_credentials, lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<EventSpotTemplate {self.id} for template {self.template_id}>"


class Event(db.Model):
    __tablename__ = "event"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    master_event_id = db.Column(db.Integer, db.ForeignKey("master_event.id"), nullable=False)
    status = db.Column(
        db.Enum(EventStatus, name="event_status_enum"),
        default=EventStatus.DRAFT,
        nullable=False,
    )
    archived = db.Column(db.Boolean, default=False, nullable=False)
    start_datetime = db.Column(db.DateTime(timezone=True), nullable=False)
    end_datetime = db.Column(db.DateTime(timezone=True), nullable=False)
    # When null: assignments open immediately on publish; when set: auto-open at this datetime
    assignments_open_datetime = db.Column(db.DateTime(timezone=True), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    contact_person = db.Column(db.String(255), nullable=True)
    paid = db.Column(db.Boolean, default=False, nullable=False)
    description = db.Column(db.Text, nullable=True)
    responsible_person_id = db.Column(db.Uuid, db.ForeignKey("user_account.id"), nullable=True)
    created_by_id = db.Column(db.Uuid, db.ForeignKey("user_account.id"), nullable=True)
    # Reminder schedule inherited from template or set manually (hours before start, comma-separated)
    reminder_schedule = db.Column(db.String(255), nullable=True, default="24")
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

    master_event = db.relationship("MasterEvent", back_populates="events")
    responsible_person = db.relationship("UserAccount", foreign_keys=[responsible_person_id])
    created_by = db.relationship("UserAccount", foreign_keys=[created_by_id])
    spots = db.relationship("EventSpot", back_populates="event", cascade="all, delete-orphan")

    # ── Derived staffing status ─────────────────────────────────────────────
    @property
    def total_spots(self) -> int:
        return len(self.spots)

    @property
    def filled_spots(self) -> int:
        return sum(1 for s in self.spots if s.assignment is not None)

    @property
    def staffing_status(self) -> str:
        total = self.total_spots
        filled = self.filled_spots
        if total == 0:
            return "No spots"
        if filled == 0:
            return "Not staffed"
        if filled < total:
            return "Partially staffed"
        if filled == total:
            return "Fully staffed"
        return "Overstaffed"

    def reminder_hours(self) -> list[int]:
        if not self.reminder_schedule:
            return [24]
        return [int(h) for h in self.reminder_schedule.split(",") if h.strip().isdigit()]

    def __repr__(self) -> str:
        return f"<Event {self.id}: {self.name} [{self.status}]>"


class EventSpot(db.Model):
    __tablename__ = "event_spot"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    # Optimistic locking — used in combination with with_for_update() for assignment
    version = db.Column(db.Integer, default=1, nullable=False)

    event = db.relationship("Event", back_populates="spots")
    required_credentials = db.relationship(
        "Credential", secondary=spot_credentials, lazy="selectin"
    )
    assignment = db.relationship(
        "Assignment", back_populates="spot", uselist=False, cascade="all, delete-orphan"
    )

    def is_eligible(self, user) -> bool:
        """Return True if the user holds credentials satisfying all spot requirements."""
        if not self.required_credentials:
            return True  # no credential requirement — anyone can fill it
        user_creds = set(user.credentials)
        for required in self.required_credentials:
            if not any(required.can_be_filled_by(uc) for uc in user_creds):
                return False
        return True

    def __repr__(self) -> str:
        return f"<EventSpot {self.id} event={self.event_id}>"
