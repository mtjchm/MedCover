import os
from flask import Flask
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

    if app.config.get("DEV_LOGIN_ENABLED"):
        from .routes.dev import dev_bp
        app.register_blueprint(dev_bp)

    return app
