"""
Výkaz práce — monthly work-report xlsx generation and download.

Routes
------
GET  /vykaz/           — form: pick year + month, generate
POST /vykaz/generate   — build xlsx, redirect to download
GET  /vykaz/download   — stream the generated file to the browser
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from app.utils import require_permission
from app.vykaz_generator import generate_vykaz

vykaz_bp = Blueprint("vykaz", __name__, url_prefix="/vykaz")


@vykaz_bp.route("/", methods=["GET"])
@login_required
def index() -> str:
    require_permission("vykaz.generate")
    now = datetime.now(tz=timezone.utc)
    return render_template(
        "vykaz/index.html",
        current_year=now.year,
        current_month=now.month,
    )


@vykaz_bp.route("/generate", methods=["POST"])
@login_required
def generate() -> object:
    require_permission("vykaz.generate")
    from flask import request

    try:
        year = int(request.form["year"])
        month = int(request.form["month"])
    except (KeyError, ValueError):
        flash("Neplatné hodnoty formuláře.", "danger")
        return redirect(url_for("vykaz.index"))

    now = datetime.now(tz=timezone.utc)
    if not (2020 <= year <= now.year + 1):
        flash("Rok je mimo povolený rozsah.", "danger")
        return redirect(url_for("vykaz.index"))
    if not (1 <= month <= 12):
        flash("Měsíc musí být v rozsahu 1–12.", "danger")
        return redirect(url_for("vykaz.index"))

    try:
        generate_vykaz(current_user, year, month)
    except Exception as exc:  # pragma: no cover
        flash(f"Chyba při generování souboru: {exc}", "danger")
        return redirect(url_for("vykaz.index"))

    from app.vykaz_generator import CZ_MONTH_NAMES
    return render_template(
        "vykaz/result.html",
        year=year,
        month=month,
        month_name=CZ_MONTH_NAMES[month],
    )


@vykaz_bp.route("/download")
@login_required
def download() -> object:
    require_permission("vykaz.generate")
    from flask import current_app, request
    from pathlib import Path

    try:
        year = int(request.args["year"])
        month = int(request.args["month"])
    except (KeyError, ValueError):
        flash("Neplatné parametry.", "danger")
        return redirect(url_for("vykaz.index"))

    filename = f"{year}-{month:02d}.xlsx"
    user_dir = Path(current_app.instance_path) / "vykaz" / str(current_user.id)

    if not (user_dir / filename).exists():
        flash("Soubor nenalezen. Vygenerujte výkaz znovu.", "warning")
        return redirect(url_for("vykaz.index"))

    download_name = f"vykaz_{year}_{month:02d}_{current_user.name.replace(' ', '_')}.xlsx"
    return send_from_directory(
        directory=str(user_dir),
        path=filename,
        as_attachment=True,
        download_name=download_name,
    )
