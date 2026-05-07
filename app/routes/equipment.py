from __future__ import annotations

from flask import Blueprint

equipment_bp = Blueprint("equipment", __name__, url_prefix="/equipment")


@equipment_bp.route("/")
def index() -> str:
    return "TODO: equipment inventory"
