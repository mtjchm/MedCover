from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, redirect, request, url_for
from werkzeug.wrappers import Response as WerkzeugResponse
from .extensions import db, migrate, login_manager, mail
from .config import config_by_name

_PRAGUE_TZ = ZoneInfo("Europe/Prague")


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    # Import models here so Flask-Migrate discovers all tables
    with app.app_context():
        from . import models  # noqa: F401

    from .routes import register_blueprints
    register_blueprints(app)

    @app.template_filter("localdt")
    def localdt_filter(dt: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
        """Convert a UTC datetime to Europe/Prague local time and format it."""
        if dt is None:
            return "—"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_PRAGUE_TZ).strftime(fmt)

    @app.template_global()
    def audit_entity_url(entity_type: str, entity_id: str) -> str | None:
        """Return a URL to view the given entity, or None if no page exists."""
        try:
            eid = int(entity_id)
        except (ValueError, TypeError):
            eid = entity_id  # type: ignore[assignment]
        mapping: dict[str, str | None] = {
            "Event": url_for("events.detail", event_id=eid),
            "MasterEvent": url_for("master_events.detail", me_id=eid),
            "AppSettings": url_for("app_settings.index"),
            "Credential": url_for("credentials.index"),
        }
        return mapping.get(entity_type)

    @app.before_request
    def _setup_guard() -> WerkzeugResponse | None:
        """
        Redirect to the setup wizard if initial setup is not complete.
        Skips static files, the setup blueprint itself, and auth routes
        (so the app doesn't get into a redirect loop before the DB is seeded).
        """
        from .models.settings import get_settings

        # Allow static files, setup pages, and health probe through unconditionally
        if request.endpoint and (
            request.endpoint.startswith("setup.")
            or request.endpoint == "static"
            or request.endpoint == "main.health"
        ):
            return None

        try:
            settings = get_settings()
        except Exception:
            # DB not ready yet (e.g. running migrations) — let it through
            return None

        if not settings.setup_complete:
            return redirect(url_for("setup.step1"))

        # Keep Flask-Mail config in sync with DB on every request (cheap dict write)
        settings.apply_to_app(app)
        return None

    return app
