# MedCover

[![CI](https://github.com/spidermila/MedCover/actions/workflows/ci.yml/badge.svg)](https://github.com/spidermila/MedCover/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-68%20passed-brightgreen)](https://github.com/spidermila/MedCover/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-59%25-yellow)](https://github.com/spidermila/MedCover/actions/workflows/ci.yml)

MedCover is a web application for the **Czech Red Cross** that replaces a Google Sheets–based medical cover planning solution.
It manages events, spot assignments, user roles, equipment, and reporting — all in Czech, tailored to the organisation's workflows.

**For architecture and design decisions, see [architecture.md](architecture.md).**
**For DevOps, local setup, CI/CD, and deployment, see [DEVOPS.md](DEVOPS.md).**
**For the MVP feature checklist and progress tracker, see [MVP.md](MVP.md).**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.14 |
| Web framework | Flask 3 |
| Database | PostgreSQL 17 |
| ORM / migrations | SQLAlchemy · Flask-Migrate (Alembic) |
| Auth | Flask-Login · Flask-Mail |
| Frontend | Jinja2 · Bootstrap 5.3 · FullCalendar |
| Infrastructure | Docker Compose (web + scheduler + db) |
| CI | GitHub Actions (lint + test) |
| Hosting (target) | Render.com |

---

## Quick Start

> Full setup instructions are in [DEVOPS.md](DEVOPS.md).

```bash
# 1. Clone and create virtual environment
git clone git@github.com:spidermila/MedCover.git && cd MedCover
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 3. Configure environment
cp .env.example .env  # then fill in your values

# 4. Start containers
docker compose up -d

# 5. Install pre-commit hooks
pre-commit install

# 6. Run tests
DATABASE_URL="postgresql://medcover:devpassword@localhost:5432/medcover_test" \
  SECRET_KEY="test-secret" FLASK_ENV=testing pytest tests/
```

---

## Running Tests

Tests run automatically on every commit via the pre-commit `pytest` hook.
To run manually:

```bash
DATABASE_URL="postgresql://medcover:devpassword@localhost:5432/medcover_test" \
  SECRET_KEY="test-secret" FLASK_ENV=testing pytest tests/
```

Coverage report is written to `htmlcov/` after each run.
