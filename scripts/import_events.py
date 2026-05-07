#!/usr/bin/env python3
"""
MedCover – Google Sheets Event Extraction Script
=================================================
Reads a downloaded .xlsx export of the "Dozory" Google Sheet and produces
a JSON file suitable for pasting into the MedCover import page.

Usage
-----
    python scripts/import_events.py [--input <file.xlsx>] [--output <file.json>]

Defaults:
    --input   Dozory 2026.xlsx  (relative to CWD)
    --output  import_events.json (relative to CWD)

Requirements
------------
    pip install openpyxl

Column mapping (GS "Dozory" sheet, row 2 = headers, data from row 3):
    A (0)  Akce                  → name
    B (1)  Datum                 → date  (datetime.datetime)
    C (2)  Místo konání          → location
    D (3)  Vozidlo/stan          → description snippet
    E (4)  Osvěta pp / dozor     → description snippet
    F (5)  kontakt pořadatel     → contact_person
    G (6)  Začátek               → start_time  (datetime.time or None)
    H (7)  Konec                 → end_time    (datetime.time or None)
    I (8)  Hlídky zdravotníků    → (ignored – we always create 3 spots)
    J (9)  Počet ošetření        → (ignored)
    K (10) Placený               → paid  (bool)
    L (11) Doba trvání           → (ignored – computed by DB)
    M (12) Zodpovědný zdravotník → responsible_person (name string)
    N+ (13+) Přihlášení         → description snippet (text only)

Output JSON schema (one object per event):
    {
        "name":               str,
        "date":               "YYYY-MM-DD",
        "start_time":         "HH:MM" or null,
        "end_time":           "HH:MM" or null,
        "location":           str or null,
        "paid":               bool,
        "responsible_person": str or null,
        "contact_person":     str or null,
        "description":        str,
        "time_missing":       bool
    }

Notes
-----
- Past events (before today) are filtered out.
- Duplicate event names get the date appended: "Vítání občánků 22.1."
- If start_time is missing, start_time/end_time are null and time_missing is true.
  The web app will create the event without spots and add a note to the description.
- Signups from col N+ are appended to the description as plain text so no
  information from the original sheet is lost.
- The script is idempotent: running it multiple times on the same file produces
  the same output. Duplicate detection is handled by the web app at import time.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _fmt_time(t: Any) -> str | None:
    """Return 'HH:MM' string from a datetime.time object, or None."""
    if t is None:
        return None
    try:
        return t.strftime("%H:%M")
    except AttributeError:
        return None


def _fmt_date(dt: Any) -> str | None:
    """Return 'YYYY-MM-DD' string from a datetime.datetime object, or None."""
    if not isinstance(dt, datetime):
        return None
    return dt.strftime("%Y-%m-%d")


def _build_description(
    vehicle: str | None,
    event_type: str | None,
    contact: str | None,
    signups: list[str],
    time_missing: bool,
) -> str:
    """Assemble the description field from GS columns that have no dedicated field."""
    parts: list[str] = []
    if event_type:
        parts.append(f"Typ: {event_type.strip()}")
    if vehicle:
        parts.append(f"Vozidlo/stan: {vehicle.strip()}")
    if contact:
        parts.append(f"Kontakt pořadatel: {contact.strip()}")
    if signups:
        names = ", ".join(n.strip() for n in signups if n and str(n).strip())
        if names:
            parts.append(f"Přihlášení (import z GS): {names}")
    if time_missing:
        parts.append(
            "UPOZORNĚNÍ: Čas akce nebyl v importních datech uveden. "
            "Akce byla vytvořena bez pozic. Doplňte čas a přidejte pozice ručně."
        )
    return " | ".join(parts)


def extract(xlsx_path: Path, cutoff: date | None = None) -> list[dict]:
    """Read the xlsx and return a list of event dicts.

    Args:
        xlsx_path: Path to the .xlsx file.
        cutoff:    Only include events with date >= cutoff.  Defaults to today.

    Returns:
        List of event dicts in the interchange JSON schema.
    """
    try:
        import openpyxl  # noqa: PLC0415 – optional dep, import inside to give clear error
    except ImportError:
        print(
            "ERROR: openpyxl is not installed.  Run:  pip install openpyxl",
            file=sys.stderr,
        )
        sys.exit(1)

    if cutoff is None:
        cutoff = date.today()

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active

    # Count occurrences of each name among future events so we know
    # which names need the date suffix to stay unique.
    name_counts: dict[str, int] = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        name = row[0]
        dt = row[1]
        if not name or not isinstance(dt, datetime):
            continue
        if dt.date() < cutoff:
            continue
        name_counts[str(name)] = name_counts.get(str(name), 0) + 1

    events: list[dict] = []
    seen_names: dict[str, int] = {}  # track how many times we've used a name+suffix

    for row in ws.iter_rows(min_row=3, values_only=True):
        name = row[0]
        dt = row[1]

        # Skip rows without a name or a valid date
        if not name or not isinstance(dt, datetime):
            continue

        # Filter past events
        if dt.date() < cutoff:
            continue

        name = str(name).strip()
        raw_date = dt.date()

        # --- Name uniqueness ---
        if name_counts.get(name, 1) > 1:
            suffix = raw_date.strftime("%-d.%-m.")
            unique_name = f"{name} {suffix}"
        else:
            unique_name = name

        # If even after appending date there's a clash (same event name on same date
        # listed twice – shouldn't happen but be safe), add a counter.
        if unique_name in seen_names:
            seen_names[unique_name] += 1
            unique_name = f"{unique_name} ({seen_names[unique_name]})"
        else:
            seen_names[unique_name] = 1

        # --- Times ---
        start_time = row[6]
        end_time = row[7]
        time_missing = start_time is None

        # Treat midnight end as "end not specified"
        if end_time is not None:
            from datetime import time as _time  # noqa: PLC0415
            if end_time == _time(0, 0):
                end_time = None

        # --- Signups (col N onwards = index 13+) ---
        signup_values = [str(v) for v in row[13:] if v is not None and str(v).strip()]

        description = _build_description(
            vehicle=row[3],
            event_type=row[4],
            contact=row[5],
            signups=signup_values,
            time_missing=time_missing,
        )

        paid_raw = row[10]
        # GS stores as bool True/False; some rows may have None or 0/1
        if isinstance(paid_raw, bool):
            paid = paid_raw
        elif isinstance(paid_raw, (int, float)):
            paid = bool(paid_raw)
        else:
            paid = False

        responsible_person = row[12]
        if responsible_person is not None:
            responsible_person = str(responsible_person).strip() or None

        location = row[2]
        if location is not None:
            location = str(location).strip() or None

        contact_person = row[5]
        if contact_person is not None:
            contact_person = str(contact_person).strip() or None

        events.append(
            {
                "name": unique_name,
                "date": raw_date.strftime("%Y-%m-%d"),
                "start_time": _fmt_time(start_time),
                "end_time": _fmt_time(end_time),
                "location": location,
                "paid": paid,
                "responsible_person": responsible_person,
                "contact_person": contact_person,
                "description": description,
                "time_missing": time_missing,
            }
        )

    return events


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract future events from a Google Sheets .xlsx export to JSON."
    )
    parser.add_argument(
        "--input",
        default="Dozory 2026.xlsx",
        help="Path to the .xlsx file (default: 'Dozory 2026.xlsx')",
    )
    parser.add_argument(
        "--output",
        default="import_events.json",
        help="Output JSON file path (default: 'import_events.json'). Use '-' for stdout.",
    )
    parser.add_argument(
        "--cutoff",
        default=None,
        help="Only include events on or after this date (YYYY-MM-DD). Default: today.",
    )
    args = parser.parse_args()

    cutoff: date | None = None
    if args.cutoff:
        try:
            cutoff = date.fromisoformat(args.cutoff)
        except ValueError:
            print(f"ERROR: Invalid --cutoff date: {args.cutoff}", file=sys.stderr)
            sys.exit(1)

    xlsx_path = Path(args.input)
    if not xlsx_path.exists():
        print(f"ERROR: File not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    events = extract(xlsx_path, cutoff=cutoff)

    output_json = json.dumps(events, ensure_ascii=False, indent=2)

    if args.output == "-":
        print(output_json)
    else:
        out_path = Path(args.output)
        out_path.write_text(output_json, encoding="utf-8")
        print(
            f"✓ Extracted {len(events)} future events → {out_path}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
