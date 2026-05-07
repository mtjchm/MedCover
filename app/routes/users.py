from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from flask import (
    Blueprint, Response, abort, current_app, flash,
    redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from flask_mail import Message
from sqlalchemy.orm import selectinload

from app.extensions import db, mail
from app.models.user import UserAccount, CalendarView
from app.models.role import Role
from app.models.invite import RegistrationInvite
from app.models.audit import AuditLogEntry
from app.utils import diff_changes
from app.config import INVITE_TOKEN_HOURS

users_bp = Blueprint("users", __name__, url_prefix="/users")

_PAGE_SIZE = 30

# Phone: 9 bare digits, OR +/00 followed by 10-15 digits (spaces stripped before check)
_PHONE_RE = re.compile(r"^\d{9}$|^(\+|00)\d{10,15}$")


def _validate_phone(raw: str) -> bool:
    """Return True if raw phone is empty (optional) or matches allowed formats."""
    stripped = raw.strip().replace(" ", "")
    return stripped == "" or bool(_PHONE_RE.match(stripped))


def _require_permission(code: str) -> None:
    if not current_user.has_permission(code):
        abort(403)


# ── Own profile ───────────────────────────────────────────────────────────────

@users_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile() -> str | Response:
    user: UserAccount = current_user  # type: ignore[assignment]

    if request.method == "POST":
        action = request.form.get("action", "profile")
        if action == "profile":
            return _update_profile(user)
        if action == "password":
            return _change_password(user)
    from app.models.equipment import EquipmentItem
    issued_items = db.session.scalars(
        db.select(EquipmentItem).where(EquipmentItem.issued_to_id == user.id)
    ).all()
    from app.models.assignment import Assignment
    from app.models.event import EventSpot, Event, EventStatus
    now = datetime.now(timezone.utc)
    upcoming = db.session.scalars(
        db.select(Assignment)
        .join(Assignment.spot)
        .join(EventSpot.event)
        .where(
            Assignment.user_id == user.id,
            Event.start_datetime >= now,
            Event.status != EventStatus.CANCELLED,
        )
        .order_by(Event.start_datetime)
        .options(selectinload(Assignment.spot).selectinload(EventSpot.event))  # type: ignore[arg-type]
        .limit(10)
    ).all()
    return render_template(
        "users/profile.html",
        user=user,
        calendar_views=CalendarView,
        issued_items=issued_items,
        upcoming=upcoming,
    )


def _update_profile(user: UserAccount) -> Response:
    before: dict[str, Any] = {
        "name": user.name,
        "phone": user.phone,
        "preferred_calendar_view": user.preferred_calendar_view.value if user.preferred_calendar_view else None,
        "dashboard_horizon_days": user.dashboard_horizon_days,
        "dark_mode": user.dark_mode,
    }
    name = request.form.get("name", "").strip()
    if not name:
        flash("Jméno nesmí být prázdné.", "danger")
        return redirect(url_for("users.profile"))
    phone_raw = request.form.get("phone", "").strip()
    if not _validate_phone(phone_raw):
        flash("Neplatný formát telefonního čísla.", "danger")
        return redirect(url_for("users.profile"))
    user.name = name
    user.phone = phone_raw or None
    cv = request.form.get("preferred_calendar_view", CalendarView.LIST.value)
    try:
        user.preferred_calendar_view = CalendarView(cv)
    except ValueError:
        user.preferred_calendar_view = CalendarView.LIST
    try:
        user.dashboard_horizon_days = max(1, min(365, int(request.form.get("dashboard_horizon_days", 30))))
    except ValueError:
        user.dashboard_horizon_days = 30
    user.dark_mode = request.form.get("dark_mode") == "1"
    user.version += 1
    after: dict[str, Any] = {
        "name": user.name,
        "phone": user.phone,
        "preferred_calendar_view": user.preferred_calendar_view.value,
        "dashboard_horizon_days": user.dashboard_horizon_days,
        "dark_mode": user.dark_mode,
    }
    db.session.add(AuditLogEntry(
        actor_id=user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Uživatel {user.name} upravil svůj profil",
        changes_json=diff_changes(before, after),
    ))
    db.session.commit()
    flash("Profil byl uložen.", "success")
    return redirect(url_for("users.profile"))


def _change_password(user: UserAccount) -> Response:
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    if not user.check_password(current_pw):
        flash("Současné heslo je nesprávné.", "danger")
        return redirect(url_for("users.profile"))
    if len(new_pw) < 8:
        flash("Nové heslo musí mít alespoň 8 znaků.", "danger")
        return redirect(url_for("users.profile"))
    if new_pw != confirm:
        flash("Hesla se neshodují.", "danger")
        return redirect(url_for("users.profile"))
    user.set_password(new_pw)
    user.version += 1
    db.session.add(AuditLogEntry(
        actor_id=user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Uživatel {user.name} změnil heslo",
        changes_json={},  # passwords never logged
    ))
    db.session.commit()
    flash("Heslo bylo změněno.", "success")
    return redirect(url_for("users.profile"))


# ── Admin: user list ──────────────────────────────────────────────────────────

@users_bp.route("/")
@login_required
def index() -> str:
    _require_permission("user.view")
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    query = db.select(UserAccount).order_by(UserAccount.name)
    if q:
        query = query.where(
            db.or_(
                UserAccount.name.ilike(f"%{q}%"),
                UserAccount.email.ilike(f"%{q}%"),
            )
        )
    total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    users = db.session.scalars(
        query.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE)
    ).all()
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    roles = db.session.scalars(db.select(Role).order_by(Role.name)).all()
    return render_template(
        "users/index.html",
        users=users,
        page=page,
        total=total,
        total_pages=total_pages,
        q=q,
        roles=roles,
    )


@users_bp.route("/<uuid:user_id>")
@login_required
def detail(user_id: uuid.UUID) -> str:
    _require_permission("user.view")
    user = db.session.get(UserAccount, user_id)
    if not user:
        abort(404)
    roles = db.session.scalars(db.select(Role).order_by(Role.name)).all()
    from app.models.qualification import Qualification
    qualifications = db.session.scalars(
        db.select(Qualification).order_by(Qualification.name)
    ).all()
    return render_template("users/detail.html", user=user, all_roles=roles, all_qualifications=qualifications)


@users_bp.route("/<uuid:user_id>/edit", methods=["POST"])
@login_required
def edit_user(user_id: uuid.UUID) -> Response:
    _require_permission("user.edit_any")
    user = db.session.get(UserAccount, user_id)
    if not user:
        abort(404)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone_raw = request.form.get("phone", "").strip()
    phone = phone_raw or None

    if not name:
        flash("Jméno nesmí být prázdné.", "danger")
        return redirect(url_for("users.detail", user_id=user_id))
    if not email:
        flash("E-mail nesmí být prázdný.", "danger")
        return redirect(url_for("users.detail", user_id=user_id))
    if not _validate_phone(phone_raw):
        flash("Neplatný formát telefonního čísla.", "danger")
        return redirect(url_for("users.detail", user_id=user_id))

    if email != user.email:
        duplicate = db.session.scalar(
            db.select(UserAccount).where(
                UserAccount.email == email,
                UserAccount.id != user.id,
            )
        )
        if duplicate:
            flash(f"E-mail {email} je již použit jiným uživatelem.", "danger")
            return redirect(url_for("users.detail", user_id=user_id))

    before: dict[str, Any] = {"name": user.name, "email": user.email, "phone": user.phone}
    user.name = name
    user.email = email
    user.phone = phone
    user.version += 1
    after: dict[str, Any] = {"name": user.name, "email": user.email, "phone": user.phone}

    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Admin upravil údaje uživatele {user.name}",
        changes_json=diff_changes(before, after),
    ))
    db.session.commit()
    flash("Údaje uživatele byly uloženy.", "success")
    return redirect(url_for("users.detail", user_id=user_id))


@users_bp.route("/<uuid:user_id>/activate", methods=["POST"])
@login_required
def activate(user_id: uuid.UUID) -> Response:
    _require_permission("user.activate")
    user = db.session.get(UserAccount, user_id)
    if not user:
        abort(404)
    user.is_active = True
    user.version += 1
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Účet {user.name} ({user.email}) byl aktivován",
        changes_json={"is_active": [False, True]},
    ))
    db.session.commit()
    _send_activation_email(user)
    flash(f"Účet {user.name} byl aktivován.", "success")
    return redirect(request.referrer or url_for("users.index"))


@users_bp.route("/<uuid:user_id>/deactivate", methods=["POST"])
@login_required
def deactivate(user_id: uuid.UUID) -> Response:
    _require_permission("user.deactivate")
    user = db.session.get(UserAccount, user_id)
    if not user:
        abort(404)
    if str(user.id) == str(current_user.id):
        flash("Nelze deaktivovat vlastní účet.", "danger")
        return redirect(url_for("users.detail", user_id=user_id))
    user.is_active = False
    user.version += 1
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Účet {user.name} ({user.email}) byl deaktivován",
        changes_json={"is_active": [True, False]},
    ))
    db.session.commit()
    flash(f"Účet {user.name} byl deaktivován.", "warning")
    return redirect(url_for("users.detail", user_id=user_id))


@users_bp.route("/<uuid:user_id>/roles", methods=["POST"])
@login_required
def update_roles(user_id: uuid.UUID) -> Response:
    _require_permission("user.assign_role")
    user = db.session.get(UserAccount, user_id)
    if not user:
        abort(404)
    role_ids = [int(r) for r in request.form.getlist("role_ids")]
    before_roles = sorted(r.name for r in user.roles)
    new_roles = db.session.scalars(
        db.select(Role).where(Role.id.in_(role_ids))
    ).all() if role_ids else []
    user.roles = list(new_roles)
    user.version += 1
    after_roles = sorted(r.name for r in user.roles)
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Role uživatele {user.name} aktualizovány",
        changes_json=diff_changes({"roles": before_roles}, {"roles": after_roles}),
    ))
    db.session.commit()
    flash("Role byly aktualizovány.", "success")
    return redirect(url_for("users.detail", user_id=user_id))


@users_bp.route("/<uuid:user_id>/qualifications", methods=["POST"])
@login_required
def update_qualifications(user_id: uuid.UUID) -> Response:
    _require_permission("user.assign_qualification")
    user = db.session.get(UserAccount, user_id)
    if not user:
        abort(404)
    from app.models.qualification import Qualification
    cred_ids = [int(c) for c in request.form.getlist("qualification_ids")]
    before_quals = sorted(c.name for c in user.qualifications)
    new_creds = db.session.scalars(
        db.select(Qualification).where(Qualification.id.in_(cred_ids))
    ).all() if cred_ids else []
    user.qualifications = list(new_creds)
    user.version += 1
    after_quals = sorted(c.name for c in user.qualifications)
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type="edit",
        entity_type="UserAccount",
        entity_id=str(user.id),
        summary=f"Kvalifikace uživatele {user.name} aktualizovány",
        changes_json=diff_changes({"qualifications": before_quals}, {"qualifications": after_quals}),
    ))
    db.session.commit()
    flash("Kvalifikace byly aktualizovány.", "success")
    return redirect(url_for("users.detail", user_id=user_id))


# ── Invites ───────────────────────────────────────────────────────────────────

@users_bp.route("/invites")
@login_required
def invites() -> str:
    _require_permission("invite.create")
    items = db.session.scalars(
        db.select(RegistrationInvite).order_by(RegistrationInvite.created_at.desc())
    ).all()
    return render_template("users/invites.html", invites=items)


@users_bp.route("/invites/create", methods=["POST"])
@login_required
def create_invite() -> Response:
    _require_permission("invite.create")
    email = request.form.get("email", "").strip().lower()
    if not email or "@" not in email:
        flash("Zadejte platnou e-mailovou adresu.", "danger")
        return redirect(url_for("users.invites"))

    existing = db.session.scalar(
        db.select(RegistrationInvite).where(
            RegistrationInvite.email == email,
            RegistrationInvite.used_at.is_(None),
        )
    )
    if existing and existing.is_valid:
        flash(f"Platná pozvánka pro {email} již existuje.", "warning")
        return redirect(url_for("users.invites"))

    invite = RegistrationInvite(
        email=email,
        created_by_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITE_TOKEN_HOURS),
    )
    db.session.add(invite)
    db.session.add(AuditLogEntry(
        actor_id=current_user.id,
        action_type="create",
        entity_type="RegistrationInvite",
        entity_id=email,
        summary=f"Pozvánka vytvořena pro {email}",
        changes_json={},
    ))
    db.session.commit()

    _send_invite_email(invite)
    flash(f"Pozvánka odeslána na {email}.", "success")
    return redirect(url_for("users.invites"))


def _send_invite_email(invite: RegistrationInvite) -> None:
    register_url = url_for("auth.register", token=invite.token, _external=True)
    body = render_template("email/invite.txt", invite=invite, register_url=register_url)
    msg = Message(
        subject="MedCover — pozvánka k registraci",
        recipients=[invite.email],
        body=body,
    )
    try:
        mail.send(msg)
    except Exception as exc:
        current_app.logger.warning("Invite email failed for %s: %s", invite.email, exc)


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
