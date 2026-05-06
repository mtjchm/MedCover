"""
AppSettings — single-row table holding site-wide configuration.

One row is created during the setup wizard (setup_complete=False initially).
The SMTP password is stored Fernet-encrypted using a key derived from SECRET_KEY
so it is not stored in plaintext in the database.
"""

import base64
import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from flask import current_app

from app.extensions import db


def _fernet() -> Fernet:
    """Derive a Fernet key from the app SECRET_KEY (URL-safe base64, 32 bytes)."""
    raw = current_app.config["SECRET_KEY"].encode()
    # Pad or truncate to 32 bytes, then base64url-encode → valid Fernet key
    padded = (raw * ((32 // len(raw)) + 1))[:32]
    return Fernet(base64.urlsafe_b64encode(padded))


class AppSettings(db.Model):
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)  # always id=1

    # --- Organisation ---
    org_name = db.Column(db.String(255), nullable=True)
    timezone = db.Column(db.String(64), default="Europe/Prague", nullable=False)

    # --- SMTP ---
    smtp_server = db.Column(db.String(255), nullable=True)
    smtp_port = db.Column(db.Integer, default=587, nullable=False)
    smtp_use_tls = db.Column(db.Boolean, default=True, nullable=False)
    smtp_username = db.Column(db.String(255), nullable=True)
    smtp_password_enc = db.Column(db.Text, nullable=True)   # Fernet-encrypted
    smtp_default_sender = db.Column(db.String(255), nullable=True)

    # --- Lifecycle ---
    setup_complete = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ------------------------------------------------------------------ #
    # SMTP password helpers                                                #
    # ------------------------------------------------------------------ #

    def set_smtp_password(self, plaintext: str) -> None:
        if plaintext:
            self.smtp_password_enc = _fernet().encrypt(plaintext.encode()).decode()
        else:
            self.smtp_password_enc = None

    def get_smtp_password(self) -> str | None:
        if not self.smtp_password_enc:
            return None
        return _fernet().decrypt(self.smtp_password_enc.encode()).decode()

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_server and self.smtp_username and self.smtp_password_enc)

    def apply_to_app(self, app) -> None:
        """Push settings into Flask-Mail config so mail is sent using DB values."""
        app.config["MAIL_SERVER"] = self.smtp_server
        app.config["MAIL_PORT"] = self.smtp_port
        app.config["MAIL_USE_TLS"] = self.smtp_use_tls
        app.config["MAIL_USERNAME"] = self.smtp_username
        app.config["MAIL_PASSWORD"] = self.get_smtp_password()
        app.config["MAIL_DEFAULT_SENDER"] = self.smtp_default_sender

    def __repr__(self) -> str:
        return f"<AppSettings org={self.org_name!r} setup_complete={self.setup_complete}>"


# ------------------------------------------------------------------ #
# Module-level helper — safe to call from any request context         #
# ------------------------------------------------------------------ #

def get_settings() -> AppSettings:
    """Return the single AppSettings row, creating it if it doesn't exist yet."""
    row = db.session.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1)
        db.session.add(row)
        db.session.commit()
    return row
