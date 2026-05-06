from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login")
def login():
    return "TODO: login"


@auth_bp.route("/logout")
def logout():
    return "TODO: logout"


@auth_bp.route("/forgot-password")
def forgot_password():
    return "TODO: forgot password"


@auth_bp.route("/register/<token>")
def register(token: str):
    return f"TODO: register with token {token}"
