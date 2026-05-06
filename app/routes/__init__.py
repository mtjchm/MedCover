from flask import Flask, redirect, url_for
from .auth import auth_bp
from .events import events_bp
from .master_events import master_events_bp
from .equipment import equipment_bp
from .users import users_bp
from .reports import reports_bp
from .admin import admin_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(master_events_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))
