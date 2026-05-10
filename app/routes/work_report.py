"""
Výkaz práce — employee work report xlsx generation and download.

Routes
------
GET  /work-report/           — form: pick year + month, generate
POST /work-report/generate   — build xlsx, redirect to download
GET  /work-report/download   — stream the generated file to the browser
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
from app.work_report_generator import generate_work_report

work_report_bp = Blueprint("work_report", __name__, url_prefix="/work-report")


@work_report_bp.route("/", methods=["GET"])
@login_required
def index() -> str:
    require_permission("work_report.generate")
    now = datetime.now(tz=timezone.utc)
    return render_template(
        "work_report/index.html",
        current_year=now.year,
        current_month=now.month,
    )


@work_report_bp.route("/generate", methods=["POST"])
@login_required
def generate() -> object:
    require_permission("work_report.generate")
    from flask import request

    try:
        year = int(request.form["year"])
        month = int(request.form["month"])
    except (KeyError, ValueError):
        flash("Neplatné hodnoty formuláře.", "danger")
        return redirect(url_for("work_report.index"))

    now = datetime.now(tz=timezone.utc)
    if not (2020 <= year <= now.year + 1):
        flash("Rok je mimo povolený rozsah.", "danger")
        return redirect(url_for("work_report.index"))
    if not (1 <= month <= 12):
        flash("Měsíc musí být v rozsahu 1–12.", "danger")
        return redirect(url_for("work_report.index"))

    try:
        generate_work_report(current_user, year, month)
    except Exception as exc:  # pragma: no cover
        flash(f"Chyba při generování souboru: {exc}", "danger")
        return redirect(url_for("work_report.index"))

    from app.work_report_generator import CZ_MONTH_NAMES
    return render_template(
        "work_report/result.html",
        year=year,
        month=month,
        month_name=CZ_MONTH_NAMES[month],
    )


@work_report_bp.route("/download")
@login_required
def download() -> object:
    require_permission("work_report.generate")
    from flask import current_app, request
    from pathlib import Path

    try:
        year = int(request.args["year"])
        month = int(request.args["month"])
    except (KeyError, ValueError):
        flash("Neplatné parametry.", "danger")
        return redirect(url_for("work_report.index"))

    filename = f"{year}-{month:02d}.xlsx"
    user_dir = Path(current_app.instance_path) / "work_report" / str(current_user.id)

    if not (user_dir / filename).exists():
        flash("Soubor nenalezen. Vygenerujte výkaz znovu.", "warning")
        return redirect(url_for("work_report.index"))

    download_name = f"work_report_{year}_{month:02d}_{current_user.name.replace(' ', '_')}.xlsx"
    return send_from_directory(
        directory=str(user_dir),
        path=filename,
        as_attachment=True,
        download_name=download_name,
    )
