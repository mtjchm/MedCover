from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
def index():
    return "TODO: admin dashboard"
