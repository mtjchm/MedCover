# MedCover — DevOps Reference

This document covers the development environment setup, repository structure, CI/CD pipeline, and deployment configuration for the MedCover application.

For architectural decisions behind these choices, see `architecture.md` (AD09, AD10, Deployment Model).

---

## Repository Structure

```
MedCover/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Run tests on every PR and push
│       └── deploy.yml          # Trigger Render production deploy on merge to main
│
├── app/
│   ├── __init__.py             # Flask app factory: create_app()
│   ├── config.py               # Config classes: DevelopmentConfig, ProductionConfig
│   ├── extensions.py           # Flask extensions (db, migrate, mail, login_manager)
│   ├── models/                 # SQLAlchemy models (one file per domain entity)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── event.py
│   │   ├── master_event.py
│   │   ├── assignment.py
│   │   ├── equipment.py
│   │   ├── credential.py
│   │   └── audit.py
│   ├── routes/                 # Flask blueprints (one per feature area)
│   │   ├── __init__.py
│   │   ├── auth.py             # Login, logout, password reset, registration
│   │   ├── events.py           # Event CRUD, lifecycle, assignments
│   │   ├── master_events.py
│   │   ├── equipment.py
│   │   ├── users.py            # User management, credentials
│   │   ├── reports.py
│   │   └── admin.py            # Admin-only: audit log, system config
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── auth/
│   │   ├── events/
│   │   └── ...
│   ├── static/
│   │   ├── css/
│   │   ├── js/                 # FullCalendar, custom JS
│   │   └── img/
│   └── email/                  # Email templates (Jinja2)
│
├── scheduler/
│   └── main.py                 # Background task runner (schedule library)
│                               # Tasks: event auto-transitions, reminder emails, digests
│
├── migrations/                 # Flask-Migrate (Alembic) migration scripts
│   └── versions/
│
├── tests/
│   ├── conftest.py             # pytest fixtures: test app, test DB, test client
│   ├── test_auth.py
│   ├── test_events.py
│   ├── test_assignments.py
│   └── ...
│
├── scripts/
│   └── seed_dev.py             # Populates DB with realistic mock data for local dev
│
├── Dockerfile                  # Single image for both web and scheduler containers
├── docker-compose.yml          # Local dev: web + scheduler + postgres (hot reload)
├── render.yaml                 # Render.com Blueprint: all services as code
├── .env.example                # Template for required env vars — COMMIT THIS
├── .env                        # Actual secrets — NEVER COMMIT (in .gitignore)
├── .dockerignore
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Dev/test extras: pytest, faker, pytest-cov
├── architecture.md
└── DEVOPS.md                   # This file
```

---

## Container Architecture

Two containers share a single Docker image; they run different commands:

| Container | Command | Purpose |
|---|---|---|
| `web` | `gunicorn -w 2 -b 0.0.0.0:5000 "app:create_app()"` | Serves the Flask web application |
| `scheduler` | `python scheduler/main.py` | Background tasks: auto-transitions, reminders, digests |

Both containers share the same codebase and connect to the same PostgreSQL database via `DATABASE_URL`.

---

## Local Development

### Prerequisites
- Docker Desktop (or Docker Engine + Docker Compose)
- Git

### Setup

```bash
git clone https://github.com/spidermila/MedCover.git
cd MedCover
cp .env.example .env          # Fill in your local secrets
docker compose up --build     # Starts web + scheduler + postgres
```

The app will be available at `http://localhost:5000`.

### Seed mock data

```bash
docker compose exec web python scripts/seed_dev.py
```

This creates realistic test users, credentials, master events, events, assignments, and equipment using the `Faker` library. Running it multiple times is safe (idempotent).

### Run database migrations

```bash
# Create a new migration after model changes
docker compose exec web flask db migrate -m "describe the change"

# Apply pending migrations
docker compose exec web flask db upgrade
```

### Run tests

```bash
# Plain pytest (fastest, day-to-day dev)
docker compose exec web pytest

# Via tox (recommended — mirrors CI exactly)
docker compose exec web tox -e py314
```

Or without Docker Compose (requires a local Python env with `requirements-dev.txt` installed
and a running Docker daemon for testcontainers):

```bash
pip install -r requirements.txt -r requirements-dev.txt

# Run directly — testcontainers auto-starts a postgres:17 container
pytest

# Run via tox — same behaviour
tox -e py314
```

To skip testcontainers and use an existing Postgres, set `TEST_DATABASE_URL` before running:

```bash
TEST_DATABASE_URL=postgresql://user:pass@host:5432/mydb pytest
```

---

## docker-compose.yml

```yaml
services:
  web:
    build: .
    command: flask run --host=0.0.0.0 --debug
    volumes:
      - .:/app          # Hot reload: local code changes reflect immediately
    env_file: .env
    ports:
      - "5000:5000"
    depends_on:
      db:
        condition: service_healthy

  scheduler:
    build: .
    command: python scheduler/main.py
    volumes:
      - .:/app
    env_file: .env
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: medcover_dev
      POSTGRES_USER: medcover
      POSTGRES_PASSWORD: devpassword
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U medcover"]
      interval: 5s
      timeout: 5s
      retries: 5
    ports:
      - "5432:5432"    # Expose locally so you can connect with a DB GUI

volumes:
  postgres_data:
```

---

## Dockerfile

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install dependencies first (layer cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command (overridden by docker-compose or render.yaml)
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:create_app()"]
```

---

## Environment Variables

Copy `.env.example` to `.env` for local development. Never commit `.env`.

| Variable | Description | Example |
|---|---|---|
| `FLASK_ENV` | `development` or `production` | `development` |
| `SECRET_KEY` | Flask session secret — generate a strong random value | `openssl rand -hex 32` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://medcover:devpassword@db:5432/medcover_dev` |

> **Email / SMTP:** SMTP credentials are configured through the web UI setup wizard on first run and stored Fernet-encrypted in the `app_settings` database table. No `MAIL_*` environment variables are required.

---

## Render.com Blueprint (render.yaml)

`render.yaml` defines all Render services as code. Committing this file means the entire infrastructure can be recreated from the repo.

```yaml
services:
  - name: medcover-web
    type: web
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: gunicorn -w 2 -b 0.0.0.0:5000 "app:create_app()"
    branch: main
    autoDeploy: true
    envVars:
      - key: FLASK_ENV
        value: production
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: medcover-db
          property: connectionString
      # No MAIL_* vars needed — SMTP is configured via the setup wizard and stored encrypted in the DB

  - name: medcover-scheduler
    type: worker
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: python scheduler/main.py
    branch: main
    autoDeploy: true
    envVars:
      - key: FLASK_ENV
        value: production
      - key: DATABASE_URL
        fromDatabase:
          name: medcover-db
          property: connectionString
      # No MAIL_* vars needed — SMTP is configured via the setup wizard and stored encrypted in the DB

databases:
  - name: medcover-db
    databaseName: medcover
    user: medcover
    plan: free
```

### PR Preview environments

Render automatically spins up a full isolated environment (web + scheduler + fresh DB) for every pull request when PR Previews are enabled in the Render dashboard. The preview is torn down when the PR is merged or closed.

To enable: Render Dashboard → your service → Settings → Pull Request Previews → Enable.

---

## Type Checking (mypy)

MedCover uses **mypy 2.0** for static type checking. All production code in `app/` and `scheduler/` is annotated and must pass mypy on every commit.

### Running mypy manually

```bash
source .venv/bin/activate
mypy app/ scheduler/
```

A clean run prints `Success: no issues found in N source files`.

### Configuration

mypy is configured in `pyproject.toml` under `[tool.mypy]`:

- `disallow_untyped_defs = true` — **hard requirement**: every function must have full parameter and return type annotations
- `check_untyped_defs = true` — bodies of annotated functions are fully type-checked
- `ignore_missing_imports = true` — suppresses errors for third-party packages without stubs (Flask, SQLAlchemy, etc.)
- `exclude` — migrations, tests, htmlcov, and .venv are excluded

#### Key overrides

| Override | Reason |
|---|---|
| `app.models.*` — disables `name-defined`, `misc`, `assignment` | `db.Model` base class is not resolvable without full SQLAlchemy stubs; `db.relationship()` returns `RelationshipProperty[Any]` at the type level |
| `app.routes.*` — disables `union-attr`, `return-value`, `attr-defined` | Flask's `redirect()` returns `werkzeug.wrappers.Response` (not `flask.wrappers.Response`); `current_user` is a `LocalProxy` without union narrowing |
| `scripts.*` — `ignore_errors = true` | Seed scripts are not production code |

### Pre-commit hook

mypy runs automatically on every commit via `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: .venv/bin/mypy app/ scheduler/
      language: system
      pass_filenames: false
      always_run: true
```

It runs before pytest. A commit is rejected if mypy reports any errors.

### Model annotation pattern

SQLAlchemy models use the old-style `db.Column()` syntax (not `Mapped[]`-style declarative). To avoid converting models (which risks bugs), the pattern is:

1. Add `# type: ignore[misc]` to the class definition line: `class Event(db.Model):  # type: ignore[misc]`
2. Annotate relationship attributes with `Mapped[list[X]]` or `Mapped[X | None]` when they are iterated or accessed — **only the attribute declaration**, not the `db.relationship(...)` call
3. Import forward references under `TYPE_CHECKING` to avoid circular imports at runtime

---

## CI/CD Pipeline

### On every PR (`ci.yml`)

```
PR opened / updated
      ↓
GitHub Actions: ci.yml
  - Spin up PostgreSQL service container
  - Install dependencies
  - Run Flask-Migrate (flask db upgrade)
  - Run pytest
      ↓
Render: spin up PR Preview environment (if previews enabled)
      ↓
Review, approve, merge
```

### On merge to main (`deploy.yml`)

```
Merge to main
      ↓
GitHub Actions: deploy.yml
  - Trigger Render deploy via API (POST to deploy hook)
      ↓
Render: pulls latest image, runs migrations, restarts web + scheduler
```

### .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: medcover
          POSTGRES_PASSWORD: testpassword
          POSTGRES_DB: medcover_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql://medcover:testpassword@localhost:5432/medcover_test
      FLASK_ENV: testing
      SECRET_KEY: ci-test-secret-key

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Run migrations
        run: flask db upgrade

      - name: Run tests
        run: pytest --cov=app --cov-report=term-missing
        # Note: CI runs pytest directly. tox can be added here in future
        # once multiple Python versions are available on the runner.
```

### .github/workflows/deploy.yml

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    needs: []          # Could add 'test' job here if CI and deploy are in same workflow

    steps:
      - name: Trigger Render deploy
        run: |
          curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK_URL }}"
```

`RENDER_DEPLOY_HOOK_URL` is a secret stored in GitHub repository settings. Get it from Render Dashboard → your service → Settings → Deploy Hook.

---

## Database Migrations

This project uses **Flask-Migrate** (Alembic wrapper for Flask-SQLAlchemy).

```bash
# After changing a model:
flask db migrate -m "add preferred_calendar_view to user"

# Before committing: review the generated migration in migrations/versions/
# Then apply:
flask db upgrade

# Rollback one step:
flask db downgrade
```

Migrations run automatically on Render deploy via the deploy hook (or add `flask db upgrade` as a pre-deploy command in `render.yaml`).

---

## Known Issues & Mitigations

### WSL2 + Docker PostgreSQL schema loss

**Symptom:** After a Windows restart, hibernate, or `wsl --shutdown`, the
app fails to start (or shows login errors) even though `alembic_version`
reports the correct migration head. Running `flask verify-schema` reveals
that all application tables are missing.

**Root cause:** Docker named volumes on WSL2 live on `/dev/sdd`, the WSL2
virtual disk (a `.vhdx` file managed by Hyper-V). PostgreSQL writes
committed data to the **Linux kernel page cache** first — fsync flushes it
to the page cache, not directly to the VHD. The page cache is only written
through to the underlying VHD periodically by the kernel. When WSL2 is
force-terminated (Windows shutdown, hibernate, `wsl --shutdown`), it kills
all processes immediately without going through Docker's stop sequence.
PostgreSQL therefore never runs a final checkpoint, and any dirty pages
still in the kernel page cache at that moment are lost.

`alembic_version` survives because it was written early (during `flask db
upgrade`) and had time to be flushed to disk. The application tables, being
written later and containing more data, are typically still in the page
cache when the kill happens.

**Why the default settings make it worse:** PostgreSQL's default
`checkpoint_timeout` is **5 minutes**, meaning up to 5 minutes of dirty
pages can accumulate in RAM between disk flushes. The default `stop_grace_period`
in Docker Compose is **10 seconds**, which is often too short for PostgreSQL
to finish a checkpoint before receiving SIGKILL from `docker compose down`.

**Mitigations applied** (commit `4fd6d72`):

| File | Change | Effect |
|---|---|---|
| `postgres.conf` | `checkpoint_timeout = 30s` | Dirty-page window reduced from 5 min → 30 s |
| `postgres.conf` | `checkpoint_completion_target = 0.9` | Spreads checkpoint I/O to avoid spikes |
| `postgres.conf` | `listen_addresses = '*'` | Required when supplying a full custom config — PostgreSQL defaults to `localhost`-only, which blocks inter-container connections |
| `docker-compose.yml` | `stop_grace_period: 60s` on `db` | Gives PostgreSQL enough time to checkpoint cleanly on `docker compose down/stop` |

**Residual risk:** A hard WSL2 kill can still lose up to ~30 s of dev
writes. This is an inherent limitation of running PostgreSQL inside Docker
on WSL2 and cannot be fully eliminated without moving the database outside
Docker. For dev use this is acceptable; data can be re-seeded with
`python scripts/seed_dev.py`.

**Fast-fail guard:** `docker-entrypoint.sh` runs `flask verify-schema`
after every `flask db upgrade`. If any table or column is missing, the
container exits immediately with a clear diagnostic rather than serving
traffic with a broken database.

**Recovery procedure:**

```bash
# 1. Drop the stale migration marker
docker compose exec db psql -U medcover -d medcover_dev -c "DROP TABLE IF EXISTS alembic_version;"

# 2. Re-apply all migrations
docker compose exec web flask db upgrade

# 3. Verify
docker compose exec web flask verify-schema

# 4. Re-seed dev data
docker compose exec web python scripts/seed_dev.py
```

---

## Dev Data Seeding

`scripts/seed_dev.py` creates a realistic dataset using the `Faker` library:

- 1 admin user, 2 coordinator users, 10 member users, 2 viewer users
- Standard credentials hierarchy (Doctor, Nurse, First Aider, Trainee, Driver, etc.)
- 2 custom Master Events + the default General ME
- ~20 Events in various lifecycle states across the MEs
- Assignments, equipment types, personal items (issued to members), shared items
- Some completed Events with DebriefingRecords

Running the script on an already-seeded database is safe — it checks for existing data before inserting.

---

## Secrets Management

| Secret | Where stored |
|---|---|
| `.env` local secrets | Local only — in `.gitignore`, never committed |
| Render production secrets | Render Dashboard → Environment → Environment Variables |
| GitHub Actions secrets | GitHub repo → Settings → Secrets and variables → Actions |
| `RENDER_DEPLOY_HOOK_URL` | GitHub Actions secret |

The `.env.example` file is committed and documents every required variable with a description but no real values.

---

## Frontend Assets

### Help Icons — Standard Pattern

All user-facing labels, filters, buttons, and page section titles must include a help icon
whenever the concept or behaviour might not be immediately obvious to a new user.

**Macro:** `help_icon(text, title="Nápověda")` in `app/templates/macros/help.html`

```jinja
{% from 'macros/help.html' import help_icon %}

{# On a form label #}
<label class="form-label">Název {{ help_icon("Celý název akce, jak se zobrazí v přehledech.") }}</label>

{# On a page title #}
<h2 class="mb-0">Akce {{ help_icon("Vysvětlení konceptu...", "Nadpis nápovědy") }}</h2>

{# On a section header inside a card #}
<span class="fw-semibold">Moje akce {{ help_icon("Akce, na které jste přihlášeni...") }}</span>
```

The icon renders as a small `ⓘ` button that opens a Bootstrap popover on click/tap (works on
both desktop and mobile). Popovers are auto-initialized in `app-init.js`.

**When to add a help icon:**
- Every form field label that describes a non-trivial concept
- Page `<h2>` titles for main sections (Akce, Nadřazené akce, Vybavení, …)
- Dashboard section headings
- Filter controls that aren't self-explanatory
- Buttons with non-obvious side effects (e.g. status transitions)

**Text guidelines:**
- Write in Czech (all UI text is Czech)
- Be concise but complete — explain *why*, not just *what*
- For multi-line content use `\n•` bullet points within the string
- Keep under ~300 characters so the popover stays readable on mobile

**Do not add a help icon to:**
- Self-explanatory fields like "E-mail" or "Datum"
- Action buttons where the label is already fully descriptive ("Uložit", "Zrušit")

### Bootstrap

Bootstrap is loaded via CDN — no npm or build pipeline required.

| Asset | Version | CDN |
|---|---|---|
| `bootstrap.min.css` | 5.3.8 | jsDelivr |
| `bootstrap.bundle.min.js` | 5.3.8 | jsDelivr (includes Popper) |

SRI hashes in `app/templates/base.html` were generated directly from jsDelivr at the time of setup:

```
CSS sha384: sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB
JS  sha384: FKyoEForCGlyvwx9Hj09JcYn3nv7wiPVlz7YYwJrWVcXK/BmnVDxM+D2scQbITxI
```

When upgrading Bootstrap, regenerate the hashes:
```bash
curl -s "https://cdn.jsdelivr.net/npm/bootstrap@VERSION/dist/css/bootstrap.min.css" \
  | openssl dgst -sha384 -binary | openssl base64 -A

curl -s "https://cdn.jsdelivr.net/npm/bootstrap@VERSION/dist/js/bootstrap.bundle.min.js" \
  | openssl dgst -sha384 -binary | openssl base64 -A
```
Then update the `integrity` attributes in `base.html`.

### Jinja2 Custom Filters

#### `localdt` — datetime formatting
Converts a UTC `datetime` to Europe/Prague local time.
```jinja
{{ event.start_datetime | localdt }}          {# default: "23.04.2025 14:00" #}
{{ event.start_datetime | localdt("%d.%m.%Y") }}   {# date only #}
```

#### `cznum` — Czech decimal formatting
Czech locale uses a **comma** as the decimal separator, not a dot.
All decimal numbers displayed in templates **must** use this filter.

```jinja
{{ value | cznum }}        {# 1 decimal place → "3,5" #}
{{ value | cznum(2) }}     {# 2 decimal places → "3,50" #}
```

- Registered in `app/__init__.py` alongside `localdt`.
- **Never** use `"%.1f"|format(x)` — that produces an English dot separator.
- Handles `None` gracefully (returns `—`).
