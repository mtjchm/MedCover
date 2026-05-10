"""
Výkaz práce (employee work report) xlsx generator.

Generates a single-sheet openpyxl workbook that matches the layout of the
legacy Google-Sheets "Dozory YYYY.xlsx" monthly report used by Czech Red
Cross members to document worked hours for DPP payroll purposes.

Public entry point::

    path = generate_work_report(user, year, month)

The file is written to  instance/work_report/<user_id>/<year>-<MM>.xlsx
and is overwritten on each call.  Callers are responsible for serving
the file and scheduling cleanup (files older than 1 day should be removed).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import holidays
import sqlalchemy as sa
from flask import current_app
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

if TYPE_CHECKING:
    from app.models import UserAccount

# ── Czech locale constants ────────────────────────────────────────────────────

CZ_MONTH_NAMES = [
    "", "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
    "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
]

CZ_WEEKDAY_ABBR = ["PO", "ÚT", "ST", "ČT", "PÁ", "SO", "NE"]  # Mon=0 … Sun=6

# ── Colours ──────────────────────────────────────────────────────────────────

_BLUE_FILL = PatternFill("solid", fgColor="FF99CCFF")   # header row
_YELLOW_FILL = PatternFill("solid", fgColor="FFFFFF00")  # public holiday
_WHITE_FILL = PatternFill("solid", fgColor="FFFFFFFF")  # normal day
_RED_FONT = Font(name="Calibri", size=10, color="FFFF0000")   # weekend day name
_STD_FONT = Font(name="Calibri", size=10)
_BOLD_FONT = Font(name="Calibri", size=10, bold=True)

# ── Borders ──────────────────────────────────────────────────────────────────


def _side(style: str) -> Side:
    return Side(border_style=style)


_HDR_BORDER_A = Border(
    left=_side("medium"), right=_side("thin"),
    top=_side("medium"), bottom=_side("medium"),
)
_HDR_BORDER_B = Border(
    left=_side("thin"), right=_side("thin"),
    top=_side("medium"), bottom=_side("medium"),
)
_HDR_BORDER_C = Border(
    left=_side("thin"), right=_side("thin"),
    top=_side("medium"), bottom=_side("medium"),
)
_HDR_BORDER_D = Border(
    left=_side("thin"), right=_side("medium"),
    top=_side("medium"), bottom=_side("medium"),
)
_DAY_BORDER_A = Border(
    left=_side("medium"), right=_side("thin"),
    top=_side("thin"), bottom=_side("thin"),
)
_DAY_BORDER_B = Border(
    left=_side("thin"), right=_side("thin"),
    top=_side("thin"), bottom=_side("thin"),
)
_DAY_BORDER_C = Border(
    left=_side("thin"), right=_side("thin"),
    top=_side("thin"), bottom=_side("thin"),
)
_DAY_BORDER_D = Border(
    left=_side("thin"), right=_side("medium"),
    top=_side("thin"), bottom=_side("thin"),
)
_TOTAL_BORDER_A = Border(
    left=_side("medium"), right=_side("thin"),
    top=_side("medium"), bottom=_side("medium"),
)
_TOTAL_BORDER_C = Border(
    left=_side("thin"), right=_side("thin"),
    top=_side("medium"), bottom=_side("medium"),
)
_TOTAL_BORDER_D = Border(
    left=_side("thin"), right=_side("medium"),
    top=_side("medium"), bottom=_side("medium"),
)

# ── Layout constants ──────────────────────────────────────────────────────────

_ROW_HEIGHT = 15.75
_COL_WIDTHS = {
    "A": 6.86,   # date number
    "B": 6.43,   # day abbreviation
    "C": 9.43,   # hours
    "D": 20.29,  # description (merged D:E)
    "E": 22.43,
}

_FIRST_DATA_ROW = 10  # row index of day-1 (1-based)
_HEADER_ROW = 9  # column header row


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_row_height(ws: Worksheet, row: int, height: float = _ROW_HEIGHT) -> None:
    ws.row_dimensions[row].height = height


def _write_cell(
    ws: Worksheet,
    row: int,
    col: int,
    value: object = None,
    *,
    font: Font | None = None,
    fill: PatternFill | None = None,
    alignment: Alignment | None = None,
    border: Border | None = None,
    number_format: str | None = None,
) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    if font is not None:
        cell.font = font
    if fill is not None:
        cell.fill = fill
    if alignment is not None:
        cell.alignment = alignment
    if border is not None:
        cell.border = border
    if number_format is not None:
        cell.number_format = number_format


def _fetch_events_for_month(
    user_id: str, year: int, month: int
) -> dict[int, tuple[Decimal, list[str]]]:
    """Return {day: (total_hours, [event_names])} for the user's paid completed events."""
    from app.extensions import db
    from app.models import Assignment, Event, EventSpot, EventStatus

    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    period_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    rows = db.session.execute(
        sa.select(Event)
        .join(EventSpot, EventSpot.event_id == Event.id)
        .join(Assignment, Assignment.spot_id == EventSpot.id)
        .where(
            Assignment.user_id == user_id,
            Event.status == EventStatus.COMPLETED,
            Event.paid.is_(True),
            Event.start_datetime >= period_start,
            Event.start_datetime <= period_end,
        )
    ).scalars().all()

    result: dict[int, tuple[Decimal, list[str]]] = {}
    for ev in rows:
        hours = ev.actual_hours or ev.planned_hours or Decimal("0")
        day = ev.start_datetime.day
        if day in result:
            prev_hours, prev_names = result[day]
            result[day] = (prev_hours + hours, prev_names + [ev.name])
        else:
            result[day] = (hours, [ev.name])
    return result


# ── Core generator ────────────────────────────────────────────────────────────

def generate_work_report(user: UserAccount, year: int, month: int) -> Path:
    """
    Build the výkaz práce xlsx for *user* for the given *year*/*month*.

    The file is written to  instance/work_report/<user_id>/<year>-<MM>.xlsx
    and is overwritten if it already exists.  Returns the absolute Path.
    """

    month_name = CZ_MONTH_NAMES[month]
    days_in_month = calendar.monthrange(year, month)[1]
    cz_holidays: set[date] = set(holidays.CZ(years=year).keys())

    events_by_day = _fetch_events_for_month(str(user.id), year, month)

    # ── Create workbook ───────────────────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = month_name

    # Column widths
    for col_letter, width in _COL_WIDTHS.items():
        ws.column_dimensions[col_letter].width = width

    # Page setup: landscape, A4, fit to 1 page
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = 9  # A4
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.page_margins.left = 0.7
    ws.page_margins.right = 0.7
    ws.page_margins.top = 0.787
    ws.page_margins.bottom = 0.787
    ws.page_margins.header = 0.0
    ws.page_margins.footer = 0.0

    # ── Header block (rows 1-8) ───────────────────────────────────────────────
    for r in range(1, 9):
        _apply_row_height(ws, r)

    # Row 3: title (merged A3:E3)
    ws.merge_cells("A3:E3")
    _write_cell(ws, 3, 1, "Výkaz práce / odpracovaných hodin",
                font=_BOLD_FONT, alignment=Alignment(horizontal="center"))

    # Row 4: worker name
    ws.merge_cells("A4:C4")
    ws.merge_cells("D4:E4")
    _write_cell(ws, 4, 1, "Jméno pracovníka:", font=_STD_FONT)
    _write_cell(ws, 4, 4, user.name, font=_STD_FONT)

    # Row 5: úvazek
    ws.merge_cells("A5:C5")
    ws.merge_cells("D5:E5")
    _write_cell(ws, 5, 1, "Pracovní úvazek:", font=_STD_FONT)
    _write_cell(ws, 5, 4, "DPP", font=_STD_FONT)

    # Row 6: pozice
    ws.merge_cells("A6:C6")
    ws.merge_cells("D6:E6")
    _write_cell(ws, 6, 1, "pozice:", font=_STD_FONT)
    _write_cell(ws, 6, 4, "zdravotní dozory", font=_STD_FONT)

    # Row 8: month + year
    _write_cell(ws, 8, 1, "Měsíc:", font=_STD_FONT)
    _write_cell(ws, 8, 3, month_name, font=_STD_FONT,
                alignment=Alignment(horizontal="left"))
    _write_cell(ws, 8, 4, "Rok:", font=_STD_FONT)
    _write_cell(ws, 8, 5, year, font=_STD_FONT)

    # ── Column headers (row 9) ────────────────────────────────────────────────
    _apply_row_height(ws, _HEADER_ROW)
    ws.merge_cells("D9:E9")
    _write_cell(ws, 9, 1, "Datum",
                font=_BOLD_FONT, fill=_BLUE_FILL,
                alignment=Alignment(horizontal="center"),
                border=_HDR_BORDER_A)
    _write_cell(ws, 9, 2, "Den",
                font=_BOLD_FONT, fill=_BLUE_FILL,
                alignment=Alignment(horizontal="center"),
                border=_HDR_BORDER_B)
    _write_cell(ws, 9, 3, "Počet hodin",
                font=_BOLD_FONT, fill=_BLUE_FILL,
                alignment=Alignment(horizontal="center", wrap_text=True),
                border=_HDR_BORDER_C)
    _write_cell(ws, 9, 4, "Popis činnosti",
                font=_BOLD_FONT, fill=_BLUE_FILL,
                alignment=Alignment(horizontal="center"),
                border=_HDR_BORDER_D)

    # ── Day rows ──────────────────────────────────────────────────────────────
    for day in range(1, days_in_month + 1):
        row = _FIRST_DATA_ROW + day - 1
        _apply_row_height(ws, row)

        d = date(year, month, day)
        weekday = d.weekday()  # 0=Mon … 6=Sun
        is_weekend = weekday >= 5  # Sat or Sun
        is_holiday = d in cz_holidays

        fill = _YELLOW_FILL if is_holiday else _WHITE_FILL
        day_font = _RED_FONT if is_weekend else _STD_FONT

        hours_val, names = events_by_day.get(day, (None, []))
        hours_display = float(hours_val) if hours_val else None
        description = ", ".join(names) if names else None

        ws.merge_cells(f"D{row}:E{row}")

        _write_cell(ws, row, 1, day,
                    font=_STD_FONT, fill=fill,
                    alignment=Alignment(horizontal="center"),
                    border=_DAY_BORDER_A)
        _write_cell(ws, row, 2, CZ_WEEKDAY_ABBR[weekday],
                    font=day_font,
                    alignment=Alignment(horizontal="center"),
                    border=_DAY_BORDER_B)
        _write_cell(ws, row, 3, hours_display,
                    font=_STD_FONT,
                    alignment=Alignment(horizontal="center"),
                    border=_DAY_BORDER_C,
                    number_format="0.##")
        _write_cell(ws, row, 4, description,
                    font=_STD_FONT,
                    alignment=Alignment(horizontal="left"),
                    border=_DAY_BORDER_D)

    # ── Totals row ────────────────────────────────────────────────────────────
    total_row = _FIRST_DATA_ROW + days_in_month
    _apply_row_height(ws, total_row)
    first_data = _FIRST_DATA_ROW
    last_data = total_row - 1
    ws.merge_cells(f"D{total_row}:E{total_row}")
    _write_cell(ws, total_row, 1, "Celkem hodin",
                font=_BOLD_FONT, border=_TOTAL_BORDER_A)
    _write_cell(ws, total_row, 2, None, font=_BOLD_FONT,
                border=Border(right=_side("thin"), top=_side("medium"), bottom=_side("medium")))
    _write_cell(ws, total_row, 3,
                f"=SUM(C{first_data}:C{last_data})",
                font=_BOLD_FONT,
                alignment=Alignment(horizontal="center"),
                border=_TOTAL_BORDER_C,
                number_format="0.##")
    _write_cell(ws, total_row, 4, None, border=_TOTAL_BORDER_D)

    # ── Signature rows ────────────────────────────────────────────────────────
    sig_worker = total_row + 4
    sig_boss = total_row + 7
    for r in (sig_worker, sig_boss):
        _apply_row_height(ws, r)

    _write_cell(ws, sig_worker, 1, "Datum a podpis pracovníka:", font=_BOLD_FONT)
    last_day_date = date(year, month, days_in_month)
    _write_cell(ws, sig_worker, 4, last_day_date, font=_STD_FONT,
                number_format="DD.MM.YYYY")
    _write_cell(ws, sig_boss, 1, "Datum a podpis nadřízeného pracovníka:", font=_BOLD_FONT)

    # ── Save ──────────────────────────────────────────────────────────────────
    instance_path = Path(current_app.instance_path)
    out_dir = instance_path / "work_report" / str(user.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{year}-{month:02d}.xlsx"

    wb.save(str(out_path))
    return out_path
