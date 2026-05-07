"""
Import blueprint — batch import of events from a JSON payload.

Routes:
  GET  /import/events/           paste form
  POST /import/events/preview    validate JSON + show editable preview
  POST /import/events/confirm    create events in one transaction
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.audit import AuditLogEntry
from app.models.event import Event, EventSpot, EventStatus
from app.models.master_event import MasterEvent
from app.models.qualification import Qualification
from app.models.user import UserAccount

import_bp = Blueprint("import_events", __name__, url_prefix="/import")

_PRAGUE_TZ = ZoneInfo("Europe/Prague")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _require_import_permission() -> None:
    """Abort 403 unless the current user may import events."""
    if not current_user.has_permission("event.create"):
        abort(403)


def _match_responsible_person(
    name_str: str | None,
    users: list[UserAccount],
) -> tuple[UserAccount | None, str]:
    """Try to match a name string to a UserAccount.

    Returns (user_or_None, confidence) where confidence is one of:
      "exact"   – matched by exact full name
      "iexact"  – matched case-insensitively
      "reversed"– matched by reversing "Lastname Firstname" → "Firstname Lastname"
      "none"    – no match found
    """
    if not name_str or not name_str.strip():
        return None, "none"

    name_str = name_str.strip()

    # Build lookup maps
    by_name: dict[str, UserAccount] = {u.name: u for u in users}
    by_name_lower: dict[str, UserAccount] = {u.name.lower(): u for u in users}

    # 1. Exact
    if name_str in by_name:
        return by_name[name_str], "exact"

    # 2. Case-insensitive
    if name_str.lower() in by_name_lower:
        return by_name_lower[name_str.lower()], "iexact"

    # 3. Reversed — GS stores "Lastname Firstname", DB stores "Firstname Lastname"
    parts = name_str.split()
    if len(parts) == 2:
        reversed_name = f"{parts[1]} {parts[0]}"
        if reversed_name in by_name:
            return by_name[reversed_name], "reversed"
        if reversed_name.lower() in by_name_lower:
            return by_name_lower[reversed_name.lower()], "reversed"

    return None, "none"


def _parse_datetime(date_str: str, time_str: str | None, tz: ZoneInfo) -> datetime:
    """Combine a YYYY-MM-DD date and HH:MM time string into a UTC-aware datetime."""
    t = time_str or "00:00"
    local = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return local.astimezone(timezone.utc)


def _validate_row(row: Any, idx: int) -> tuple[dict | None, list[str]]:
    """Validate a single event dict from the JSON payload.

    Returns (cleaned_dict, errors).  If errors is non-empty, cleaned_dict is None.
    """
    errors: list[str] = []

    if not isinstance(row, dict):
        return None, [f"Řádek {idx + 1}: není objekt (dict)."]

    name = str(row.get("name", "")).strip()
    if not name:
        errors.append("Chybí název akce.")

    date_str = str(row.get("date", "")).strip()
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        errors.append(f"Neplatné datum: '{date_str}' (očekáváno YYYY-MM-DD).")

    start_time = row.get("start_time")
    if start_time is not None:
        try:
            datetime.strptime(str(start_time), "%H:%M")
        except ValueError:
            errors.append(f"Neplatný čas začátku: '{start_time}'.")

    end_time = row.get("end_time")
    if end_time is not None:
        try:
            datetime.strptime(str(end_time), "%H:%M")
        except ValueError:
            errors.append(f"Neplatný čas konce: '{end_time}'.")

    if errors:
        return None, errors

    return {
        "name": name,
        "date": date_str,
        "start_time": start_time,
        "end_time": end_time,
        "location": str(row.get("location") or "").strip() or None,
        "paid": bool(row.get("paid", False)),
        "responsible_person": str(row.get("responsible_person") or "").strip() or None,
        "contact_person": str(row.get("contact_person") or "").strip() or None,
        "description": str(row.get("description") or "").strip(),
        "time_missing": bool(row.get("time_missing", False)),
    }, []


# ── Routes ────────────────────────────────────────────────────────────────────

@import_bp.get("/events/")
@login_required
def events_paste() -> str:
    _require_import_permission()
    return render_template("import/events.html")


@import_bp.post("/events/preview")
@login_required
def events_preview() -> str | Response:
    _require_import_permission()

    raw = request.form.get("json_data", "").strip()
    if not raw:
        flash("Vložte JSON data.", "warning")
        return redirect(url_for("import_events.events_paste"))

    # ── Parse JSON ─────────────────────────────────────────────────────────
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        flash(f"Neplatný JSON: {exc}", "danger")
        return render_template("import/events.html", json_data=raw)

    if not isinstance(payload, list):
        flash("JSON musí být pole (array) objektů.", "danger")
        return render_template("import/events.html", json_data=raw)

    # ── Load DB lookups ─────────────────────────────────────────────────────
    users = list(db.session.scalars(
        db.select(UserAccount).where(UserAccount.is_active == True).order_by(UserAccount.name)  # noqa: E712
    ).all())
    master_events = list(db.session.scalars(
        db.select(MasterEvent).order_by(MasterEvent.name)
    ).all())
    qualifications = list(db.session.scalars(
        db.select(Qualification).where(Qualification.is_deleted == False).order_by(Qualification.name)  # noqa: E712
    ).all())

    # Pre-build set of existing (name, date) pairs for duplicate detection
    existing: set[tuple[str, str]] = set()
    for ev in db.session.scalars(db.select(Event.name, Event.start_datetime)).all():
        dt = ev[1]
        if dt:
            date_part = dt[:10] if isinstance(dt, str) else dt.strftime("%Y-%m-%d")
        else:
            date_part = ""
        existing.add((ev[0], date_part))

    # ── Validate each row + match RP ─────────────────────────────────────────
    parse_errors: list[tuple[int, list[str]]] = []
    preview_rows: list[dict] = []

    for idx, raw_row in enumerate(payload):
        cleaned, errs = _validate_row(raw_row, idx)
        if errs or cleaned is None:
            parse_errors.append((idx + 1, errs))
            continue
        assert cleaned is not None  # help mypy narrow past the guard

        rp_user, rp_confidence = _match_responsible_person(cleaned["responsible_person"], users)

        warnings: list[str] = []
        if cleaned["time_missing"]:
            warnings.append("Čas akce nebyl zadán — akce bude vytvořena bez pozic.")
        if cleaned["responsible_person"] and rp_confidence == "none":
            rp_name = cleaned["responsible_person"]
            warnings.append(
                f'Zodpovědný zdravotník "{rp_name}" nebyl nalezen v databázi. Přiřaďte ručně.'
            )
        elif rp_confidence in ("iexact", "reversed"):
            rp_name_found = rp_user.name if rp_user else ""
            warnings.append(
                f'Zodpovědný zdravotník spárován přibližně: "{rp_name_found}". Zkontrolujte.'
            )

        is_duplicate = (cleaned["name"], cleaned["date"]) in existing
        if is_duplicate:
            warnings.append(
                "Akce se stejným názvem a datem již v databázi existuje."
            )

        preview_rows.append({
            **cleaned,
            "rp_user": rp_user,
            "rp_confidence": rp_confidence,
            "warnings": warnings,
            "is_duplicate": is_duplicate,
        })

    if parse_errors:
        flash(
            f"V importních datech bylo nalezeno {len(parse_errors)} chybných řádků. "
            "Opravte chyby a vložte data znovu.",
            "danger",
        )
        return render_template(
            "import/events.html",
            json_data=raw,
            parse_errors=parse_errors,
        )

    # ── Guess default qualifications by name ──────────────────────────────
    def _qual_by_name(keyword: str) -> Qualification | None:
        keyword_lower = keyword.lower()
        return next(
            (q for q in qualifications if keyword_lower in q.name.lower()),
            None,
        )

    default_zdravotnik_qual = _qual_by_name("zdravotník") or _qual_by_name("zdravotnik")
    default_zelenac_qual = _qual_by_name("zelenáč") or _qual_by_name("zelenac")

    return render_template(
        "import/preview.html",
        preview_rows=preview_rows,
        users=users,
        master_events=master_events,
        qualifications=qualifications,
        default_zdravotnik_qual=default_zdravotnik_qual,
        default_zelenac_qual=default_zelenac_qual,
        total=len(preview_rows),
        warnings_count=sum(1 for r in preview_rows if r["warnings"]),
        duplicates_count=sum(1 for r in preview_rows if r["is_duplicate"]),
    )


@import_bp.post("/events/confirm")
@login_required
def events_confirm() -> Response:
    _require_import_permission()

    form = request.form

    # Global qualification IDs (may be empty string)
    def _get_int(key: str) -> int | None:
        val = form.get(key, "").strip()
        return int(val) if val.isdigit() else None

    global_zdravotnik_qual_id = _get_int("global_zdravotnik_qual_id")
    global_zelenac_qual_id = _get_int("global_zelenac_qual_id")
    global_master_event_id = _get_int("global_master_event_id")

    # Preload qualifications and master events once
    qual_cache: dict[int, Qualification] = {}
    me_cache: dict[int, MasterEvent] = {}

    def _qual(qid: int | None) -> Qualification | None:
        if qid is None:
            return None
        if qid not in qual_cache:
            q = db.session.get(Qualification, qid)
            if q:
                qual_cache[qid] = q
        return qual_cache.get(qid)

    def _me(mid: int | None) -> MasterEvent | None:
        if mid is None:
            return None
        if mid not in me_cache:
            m = db.session.get(MasterEvent, mid)
            if m:
                me_cache[mid] = m
        return me_cache.get(mid)

    # ── Count events ──────────────────────────────────────────────────────
    count_str = form.get("event_count", "0")
    try:
        event_count = int(count_str)
    except ValueError:
        flash("Neplatný počet akcí.", "danger")
        return redirect(url_for("import_events.events_paste"))

    created = 0
    skipped = 0

    try:
        for i in range(event_count):
            prefix = f"ev_{i}_"

            include = form.get(f"{prefix}include") == "1"
            if not include:
                skipped += 1
                continue

            name = form.get(f"{prefix}name", "").strip()
            date_str = form.get(f"{prefix}date", "")
            start_time_str = form.get(f"{prefix}start_time", "").strip() or None
            end_time_str = form.get(f"{prefix}end_time", "").strip() or None
            location = form.get(f"{prefix}location", "").strip() or None
            paid = form.get(f"{prefix}paid") == "1"
            contact_person = form.get(f"{prefix}contact_person", "").strip() or None
            description = form.get(f"{prefix}description", "").strip() or None
            time_missing = form.get(f"{prefix}time_missing") == "1"

            # Per-row master event (override or fallback to global)
            row_me_id = _get_int(f"{prefix}master_event_id") or global_master_event_id
            master_event = _me(row_me_id)
            if not master_event:
                flash(f"Řádek {i + 1} ({name}): nadřazená akce není vybrána. Import přerušen.", "danger")
                db.session.rollback()
                return redirect(url_for("import_events.events_paste"))

            # Responsible person
            rp_id_str = form.get(f"{prefix}responsible_person_id", "").strip()
            responsible_person_id = rp_id_str if rp_id_str else None

            # Datetimes (Prague → UTC)
            start_dt = _parse_datetime(date_str, start_time_str, _PRAGUE_TZ)
            if end_time_str:
                end_dt = _parse_datetime(date_str, end_time_str, _PRAGUE_TZ)
                # Handle overnight events
                if end_dt <= start_dt:
                    from datetime import timedelta
                    end_dt += timedelta(days=1)
            else:
                # Default: start + 2 hours
                from datetime import timedelta
                end_dt = start_dt + timedelta(hours=2)

            event = Event(
                name=name,
                master_event_id=master_event.id,
                status=EventStatus.DRAFT,
                start_datetime=start_dt,
                end_datetime=end_dt,
                address=location,
                contact_person=contact_person,
                paid=paid,
                description=description,
                responsible_person_id=responsible_person_id or None,
                created_by_id=current_user.id,
            )
            db.session.add(event)
            db.session.flush()  # get event.id

            # ── Spots (unless time_missing) ────────────────────────────────
            if not time_missing:
                zdravotnik_qual_id = _get_int(f"{prefix}zdravotnik_qual_id") or global_zdravotnik_qual_id
                zelenac_qual_id = _get_int(f"{prefix}zelenac_qual_id") or global_zelenac_qual_id

                zdravotnik_qual = _qual(zdravotnik_qual_id)
                zelenac_qual = _qual(zelenac_qual_id)

                spots_def = [
                    ("Zdravotník", False, zdravotnik_qual),
                    ("Zelenáč", False, zelenac_qual),
                    ("Zelenáč", True, zelenac_qual),
                ]
                for desc, is_optional, qual in spots_def:
                    spot = EventSpot(
                        event_id=event.id,
                        description=desc,
                        is_optional=is_optional,
                    )
                    if qual:
                        spot.required_qualifications = [qual]
                    db.session.add(spot)

            # ── Audit log ─────────────────────────────────────────────────
            db.session.add(AuditLogEntry(
                actor_id=current_user.id,
                action_type="import",
                entity_type="Event",
                entity_id=str(event.id),
                summary=f"Akce importována z Google Sheets: {name}",
                changes_json=None,
            ))

            created += 1

        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        flash(f"Import selhal: {exc}", "danger")
        return redirect(url_for("import_events.events_paste"))

    flash(
        f"Import dokončen: vytvořeno {created} akcí"
        + (f", přeskočeno {skipped}" if skipped else "") + ".",
        "success",
    )
    return redirect(url_for("events.index"))
