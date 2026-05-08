from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, mail
from app.models.invite import RegistrationInvite
from app.models.role import Role
from app.models.user import UserAccount
from app.models.audit import AuditLogEntry
from app.utils import external_url_for

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_RESET_SALT = "pw-reset"
_INVITE_SALT = "invite"


def _safe_next(next_url: str | None) -> str:
    """Return next_url only if it is same-origin, else fall back to dashboard."""
    if not next_url:
        return url_for("main.dashboard")
    parsed = urlsplit(next_url)
    # Reject anything with a scheme or netloc (external URL or protocol-relative)
    if parsed.scheme or parsed.netloc:
        return url_for("main.dashboard")
    return next_url


def _send_mail(to: str, subject: str, template: str, **ctx: Any) -> None:
    """Render a plain-text email template and send it. Silent on misconfigured mail."""
    from flask import render_template as rt
    from flask_mail import Message

    body = rt(template, **ctx)
    msg = Message(subject=subject, recipients=[to], body=body)
    try:
        mail.send(msg)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("Mail send failed: %s", exc)


def _make_signed_token(payload: str, salt: str, hours: int) -> str:
    from itsdangerous import URLSafeTimedSerializer

    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps(payload, salt=salt)


def _load_signed_token(token: str, salt: str, hours: int) -> str | None:
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        return s.loads(token, salt=salt, max_age=hours * 3600)
    except (SignatureExpired, BadSignature):
        return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> str | Response:
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == email))

        if user and user.check_password(password):
            if not user.is_active:
                flash("Váš účet čeká na aktivaci administrátorem.", "warning")
                return redirect(url_for("auth.login"))
            login_user(user)
            return redirect(_safe_next(request.args.get("next")))

        flash("Nesprávný e-mail nebo heslo.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout() -> Response:
    logout_user()
    flash("Byli jste odhlášeni.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password() -> str | Response:
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = db.session.scalar(db.select(UserAccount).where(UserAccount.email == email))
        # Always show the same message to prevent user enumeration.
        flash("Pokud je e-mail registrován, byl odeslán odkaz pro obnovení hesla.", "info")
        if user:
            from app.config import RESET_TOKEN_HOURS

            token = _make_signed_token(str(user.id), _RESET_SALT, RESET_TOKEN_HOURS)
            reset_url = external_url_for("auth.reset_password", token=token)
            _send_mail(
                to=user.email,
                subject="MedCover — obnovení hesla",
                template="email/reset_password.txt",
                reset_url=reset_url,
                hours=RESET_TOKEN_HOURS,
            )
            db.session.add(AuditLogEntry(
                actor_id=user.id,
                action_type="password_reset_requested",
                entity_type="UserAccount",
                entity_id=str(user.id),
                summary=f"Požadavek na obnovení hesla pro {user.email}",
                changes_json={},
            ))
            db.session.commit()
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str) -> str | Response:
    from app.config import RESET_TOKEN_HOURS
    import uuid

    user_id_str = _load_signed_token(token, _RESET_SALT, RESET_TOKEN_HOURS)
    if not user_id_str:
        flash("Odkaz pro obnovení hesla je neplatný nebo vypršel.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = db.session.get(UserAccount, uuid.UUID(user_id_str))
    if not user:
        flash("Uživatel nenalezen.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if len(password) < 8:
            flash("Heslo musí mít alespoň 8 znaků.", "warning")
        elif password != password2:
            flash("Hesla se neshodují.", "warning")
        else:
            user.set_password(password)
            db.session.add(AuditLogEntry(
                actor_id=user.id,
                action_type="password_reset_completed",
                entity_type="UserAccount",
                entity_id=str(user.id),
                summary=f"Heslo obnoveno pro {user.email}",
                changes_json={},
            ))
            db.session.commit()
            flash("Heslo bylo změněno. Přihlaste se.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")


@auth_bp.route("/register/<token>", methods=["GET", "POST"])
def register(token: str) -> str | Response:
    invite = db.session.scalar(db.select(RegistrationInvite).where(RegistrationInvite.token == token))
    if not invite or not invite.is_valid:
        flash("Pozvánka je neplatná nebo vypršela.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "GET" and invite.link_clicked_at is None:
        invite.link_clicked_at = datetime.now(timezone.utc)
        db.session.add(AuditLogEntry(
            actor_id=None,
            action_type="link_clicked",
            entity_type="RegistrationInvite",
            entity_id=str(invite.id),
            summary=f"Registrační odkaz otevřen pro {invite.email}",
            changes_json={},
        ))
        db.session.commit()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not full_name:
            flash("Zadejte celé jméno.", "warning")
        elif len(password) < 8:
            flash("Heslo musí mít alespoň 8 znaků.", "warning")
        elif password != password2:
            flash("Hesla se neshodují.", "warning")
        elif db.session.scalar(db.select(UserAccount).where(UserAccount.email == invite.email)):
            flash("Účet s tímto e-mailem již existuje.", "danger")
        else:
            user = UserAccount(email=invite.email, name=full_name, is_active=False)
            user.set_password(password)
            member_role = db.session.scalar(db.select(Role).where(Role.name == Role.MEMBER))
            if member_role:
                user.roles.append(member_role)
            invite.used_at = datetime.now(timezone.utc)
            db.session.add(user)
            db.session.flush()
            db.session.add(AuditLogEntry(
                actor_id=user.id,
                action_type="complete",
                entity_type="RegistrationInvite",
                entity_id=str(invite.id),
                summary=f"Registrace dokončena pro {invite.email} jako '{full_name}'",
                changes_json={},
            ))
            db.session.commit()
            flash("Registrace dokončena. Účet aktivuje administrátor.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", invite=invite)
