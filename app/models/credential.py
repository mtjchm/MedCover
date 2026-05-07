from __future__ import annotations

from sqlalchemy.orm import Mapped
from app.extensions import db

# Self-referential M2M: credential hierarchy
# credential_parents.parent_id → credentials whose holders CAN SUBSTITUTE for credential_id
# e.g. Doctor (parent) can fill a First Aider (child) spot
credential_parents = db.Table(
    "credential_parents",
    db.Column("credential_id", db.Integer, db.ForeignKey("credential.id"), primary_key=True),
    db.Column("parent_id", db.Integer, db.ForeignKey("credential.id"), primary_key=True),
)

# M2M: UserAccount ↔ Credential
user_credentials = db.Table(
    "user_credentials",
    db.Column("user_id", db.Uuid, db.ForeignKey("user_account.id"), primary_key=True),
    db.Column("credential_id", db.Integer, db.ForeignKey("credential.id"), primary_key=True),
)


class Credential(db.Model):  # type: ignore[misc]
    __tablename__ = "credential"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Credentials that can substitute for this one (e.g. Doctor is a parent of First Aider)
    parents: Mapped[list[Credential]] = db.relationship(
        "Credential",
        secondary=credential_parents,
        primaryjoin="Credential.id == credential_parents.c.credential_id",
        secondaryjoin="Credential.id == credential_parents.c.parent_id",
        backref="children",
        lazy="selectin",
    )

    holders = db.relationship(
        "UserAccount",
        secondary=user_credentials,
        back_populates="credentials",
        lazy="dynamic",
    )

    def can_be_filled_by(self, credential: Credential) -> bool:
        """Return True if a holder of `credential` can fill a spot requiring self."""
        if credential.id == self.id:
            return True
        return any(self.can_be_filled_by(parent) for parent in self.parents)

    def __repr__(self) -> str:
        return f"<Credential {self.name}>"
