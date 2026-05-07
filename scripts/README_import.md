# Event Import Script — README

## Overview

`import_events.py` extracts future events from the Czech Red Cross "Dozory" Google Sheet
(downloaded as `.xlsx`) and converts them to a JSON file that can be pasted into the
MedCover import page (`/import/events/`).

---

## Prerequisites

Python 3.10+ with **openpyxl** installed:

```bash
pip install openpyxl
```

---

## How to Download the Source Sheet

1. Open the Google Sheet "Dozory YYYY" in Google Drive.
2. **File → Download → Microsoft Excel (.xlsx)**.
3. Save the file (e.g. `Dozory 2026.xlsx`) in the same directory where you will run the script.

> ⚠️ Do **not** use CSV export — the CSV format from this sheet has inconsistent line endings.

---

## Usage

```bash
# Basic usage — reads "Dozory 2026.xlsx" in the current directory,
# writes "import_events.json"
python scripts/import_events.py

# Custom input/output paths
python scripts/import_events.py --input /path/to/Dozory2026.xlsx --output /tmp/out.json

# Only include events from a specific date onwards
python scripts/import_events.py --cutoff 2026-06-01

# Print JSON to stdout (for piping)
python scripts/import_events.py --output -
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--input` | `Dozory 2026.xlsx` | Path to the `.xlsx` file |
| `--output` | `import_events.json` | Output JSON path. Use `-` for stdout |
| `--cutoff` | today | Exclude events before this date (ISO format `YYYY-MM-DD`) |

---

## Column Mapping

| GS Column | Letter | Maps to |
|---|---|---|
| Akce | A | `name` |
| Datum | B | `date` |
| Místo konání | C | `location` |
| Vozidlo/stan | D | `description` (text snippet) |
| Osvěta pp / zdravotní dozor | E | `description` (text snippet) |
| kontakt pořadatel | F | `contact_person` + `description` |
| Začátek | G | `start_time` |
| Konec | H | `end_time` |
| Hlídky zdravotníků | I | *(ignored — spots created automatically)* |
| Počet ošetření | J | *(ignored)* |
| Placený | K | `paid` |
| Doba trvání | L | *(ignored — computed)* |
| Zodpovědný zdravotník | M | `responsible_person` |
| Přihlášení (col N+) | N… | `description` (text snippet — not imported as assignments) |

---

## Output JSON Format

```json
[
  {
    "name":               "Extraliga házená",
    "date":               "2026-02-08",
    "start_time":         "16:00",
    "end_time":           "18:00",
    "location":           "Sportovní hala FM",
    "paid":               true,
    "responsible_person": "Vykydal Roman",
    "contact_person":     "Verlík Zdeněk 603 123 456",
    "description":        "Typ: zdravotní dozor | Kontakt pořadatel: Verlík Zdeněk",
    "time_missing":       false
  }
]
```

`start_time` / `end_time` are `"HH:MM"` strings or `null`.

---

## Automatic Adjustments

| Situation | Behaviour |
|---|---|
| Event date before today | **Filtered out** |
| Duplicate event names (same name, different dates) | Date appended: *"Vítání občánků 22.1."* |
| Missing start time | `start_time: null`, `time_missing: true`, warning added to `description` |
| Midnight end time (00:00) | Treated as "end not specified" → `end_time: null` |
| Signups (col N+) | Preserved as text in `description` — not imported as assignments |

---

## What Happens Next

Once you have `import_events.json`:

1. Open MedCover and go to **Import → Akce** (`/import/events/`).
2. Open the JSON file in any text editor, select all, and paste into the text box.
3. Click **Zkontrolovat** — the app will validate the data, check for duplicates,
   and attempt to match responsible persons to known users.
4. Review the editable preview table. Correct any issues (RP assignment, master event, etc.).
5. Click **Importovat** to create all events in one transaction.

---

## Spot Creation Rules

Unless `time_missing` is true, the import creates **3 spots per event**:

| # | Description | Type |
|---|---|---|
| 1 | Zdravotník | Mandatory |
| 2 | Zelenáč | Mandatory |
| 3 | Zelenáč | Optional |

Qualifications for these spots are configured on the import preview page before confirming.
If none are chosen, spots are created without qualification requirements.

---

## Notes

- The script is **idempotent** — running it multiple times on the same file produces
  the same output.
- Duplicate detection (same name + date already in the DB) is handled by the web app,
  not this script.
- The `.xlsx` file should **not** be committed to the repository (it may contain
  personal data — names, phone numbers). Add it to `.gitignore` if necessary.
