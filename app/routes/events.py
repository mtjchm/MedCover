from flask import Blueprint

events_bp = Blueprint("events", __name__, url_prefix="/events")


@events_bp.route("/")
def index():
    return "TODO: event list / calendar"
