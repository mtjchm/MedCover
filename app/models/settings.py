from __future__ import annotations

import base64
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from flask import Flask, current_app

from app.extensions import db


def _fernet() -> Fernet:
    """Derive a Fernet key from the app SECRET_KEY (URL-safe base64, 32 bytes)."""
    raw = current_app.config["SECRET_KEY"].encode()
    # Pad or truncate to 32 bytes, then base64url-encode → valid Fernet key
    padded = (raw * ((32 // len(raw)) + 1))[:32]
    return Fernet(base64.urlsafe_b64encode(padded))


class AppSettings(db.Model):  # type: ignore[misc]
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)  # always id=1

    # --- Organisation ---
    org_name = db.Column(db.String(255), nullable=True)
    timezone = db.Column(db.String(64), default="Europe/Prague", nullable=False)
    # External base URL used when building absolute links in e-mails.
    # Example: "https://medcoverdev.spidermila.site"  (no trailing slash)
    app_base_url = db.Column(db.String(512), nullable=True)

    # --- SMTP ---
    smtp_server = db.Column(db.String(255), nullable=True)
    smtp_port = db.Column(db.Integer, default=587, nullable=False)
    smtp_use_tls = db.Column(db.Boolean, default=True, nullable=False)
    smtp_username = db.Column(db.String(255), nullable=True)
    smtp_password_enc = db.Column(db.Text, nullable=True)   # Fernet-encrypted
    smtp_default_sender = db.Column(db.String(255), nullable=True)

    # --- Lifecycle ---
    setup_complete = db.Column(db.Boolean, default=False, nullable=False)
    feedback_enabled = db.Column(db.Boolean, default=True, nullable=False)
    scheduler_last_seen = db.Column(db.DateTime(timezone=True), nullable=True)
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
        try:
            return _fernet().decrypt(self.smtp_password_enc.encode()).decode()
        except Exception:
            # Key mismatch (e.g. SECRET_KEY changed) — treat as no password
            return None

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_server and self.smtp_username and self.smtp_password_enc)

    def apply_to_app(self, app: Flask) -> None:
        """Push settings into Flask-Mail config so mail is sent using DB values.

        Port 465 uses implicit SSL (SMTP_SSL); port 587/25 use STARTTLS.
        Flask-Mail caches config in a _Mail state object at init_app time, so we
        must call mail.init_app(app) again after updating app.config to regenerate
        the cached state.
        """
        use_ssl = self.smtp_port == 465
        app.config["MAIL_SERVER"] = self.smtp_server
        app.config["MAIL_PORT"] = self.smtp_port
        app.config["MAIL_USE_SSL"] = use_ssl
        app.config["MAIL_USE_TLS"] = self.smtp_use_tls and not use_ssl
        app.config["MAIL_USERNAME"] = self.smtp_username
        app.config["MAIL_PASSWORD"] = self.get_smtp_password()
        app.config["MAIL_DEFAULT_SENDER"] = self.smtp_default_sender

        # Reinitialise Flask-Mail so the cached _Mail state picks up new values
        from app.extensions import mail as _mail
        _mail.init_app(app)

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
