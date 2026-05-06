from flask import Blueprint

equipment_bp = Blueprint("equipment", __name__, url_prefix="/equipment")


@equipment_bp.route("/")
def index():
    return "TODO: equipment inventory"
