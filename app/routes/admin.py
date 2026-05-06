from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from flask_mail import Message

from app.extensions import db, mail
from app.models.user import UserAccount

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_permission(code: str):
    """Return 403 response if current user lacks the permission."""
    from flask import abort
    if not current_user.has_permission(code):
        abort(403)


@admin_bp.route("/")
@login_required
def index():
    _require_permission("admin.view")
    return render_template("admin/index.html")


@admin_bp.route("/pending-users")
@login_required
def pending_users():
    _require_permission("user.activate")
    users = UserAccount.query.filter_by(is_active=False).order_by(UserAccount.created_at).all()
    return render_template("admin/pending_users.html", users=users)


@admin_bp.route("/activate/<uuid:user_id>", methods=["POST"])
@login_required
def activate_user(user_id):
    _require_permission("user.activate")
    user = db.session.get(UserAccount, user_id)
    if not user:
        flash("Uživatel nenalezen.", "danger")
        return redirect(url_for("admin.pending_users"))
    if user.is_active:
        flash(f"{user.name} je již aktivní.", "info")
        return redirect(url_for("admin.pending_users"))

    user.is_active = True
    db.session.commit()

    _send_activation_email(user)
    flash(f"Účet {user.name} ({user.email}) byl aktivován.", "success")
    return redirect(url_for("admin.pending_users"))


def _send_activation_email(user: UserAccount) -> None:
    login_url = url_for("auth.login", _external=True)
    body = render_template("email/account_activated.txt", user=user, login_url=login_url)
    msg = Message(
        subject="MedCover — váš účet byl aktivován",
        recipients=[user.email],
        body=body,
    )
    try:
        mail.send(msg)
    except Exception as exc:
        current_app.logger.warning("Activation email failed for %s: %s", user.email, exc)
