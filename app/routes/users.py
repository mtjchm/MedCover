from __future__ import annotations

from flask import Blueprint

users_bp = Blueprint("users", __name__, url_prefix="/users")


@users_bp.route("/")
def index() -> str:
    return "TODO: user list"
