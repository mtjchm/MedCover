from flask import Blueprint

master_events_bp = Blueprint("master_events", __name__, url_prefix="/master-events")


@master_events_bp.route("/")
def index():
    return "TODO: master event list"
