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

    from .routes import register_blueprints
    register_blueprints(app)

    return app
