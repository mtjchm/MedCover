import os
from flask import Flask, redirect, request, url_for
from .extensions import db, migrate, login_manager, mail
from .config import config_by_name


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

    @app.before_request
    def _setup_guard():
        """
        Redirect to the setup wizard if initial setup is not complete.
        Skips static files, the setup blueprint itself, and auth routes
        (so the app doesn't get into a redirect loop before the DB is seeded).
        """
        from .models.settings import get_settings

        # Allow static files, setup pages, and auth pages through unconditionally
        if request.endpoint and (
            request.endpoint.startswith("setup.")
            or request.endpoint == "static"
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
