from __future__ import annotations

from flask import Blueprint

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
def index() -> str:
    return "TODO: reports"
