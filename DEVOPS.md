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
│   ├── __init__.py             # Flask app factory: create_app(); CSP headers; custom filters
│   ├── config.py               # Config classes: DevelopmentConfig, ProductionConfig
│   ├── extensions.py           # Flask extensions (db, migrate, mail, login_manager, csrf)
│   ├── utils.py                # Shared helpers: require_permission, audit, diff_changes, …
│   ├── queries.py              # Reusable DB queries (active_master_events_list, …)
│   ├── mail.py                 # Email sending helpers (outbox-backed)
│   ├── scheduler_tasks.py      # Task implementations called by scheduler/main.py
│   ├── work_report_generator.py# Výkaz práce XLSX generator
│   ├── models/                 # SQLAlchemy models (one file per domain entity)
│   │   ├── __init__.py         # Imports all models so Alembic auto-detects them
│   │   ├── user.py             # UserAccount, has_permission(), has_any_permission()
│   │   ├── role.py             # Role enum, ALL_PERMISSIONS, ROLE_PERMISSIONS
│   │   ├── event.py            # Event, EventSpot, EventStatus, EventTemplate
│   │   ├── master_event.py     # MasterEvent (hierarchy for yearly reporting)
│   │   ├── assignment.py       # Assignment (user ↔ spot)
│   │   ├── equipment.py        # EquipmentType, EquipmentItem, plans, assignments
│   │   ├── qualification.py    # Qualification, UserQualification (credentials)
│   │   ├── audit.py            # AuditLogEntry
│   │   ├── settings.py         # AppSettings (SMTP, setup flag, Fernet-encrypted creds)
│   │   ├── invite.py           # Invite (invite-only registration tokens)
│   │   ├── outbox.py           # EmailOutbox (queued emails, retry logic)
│   │   ├── digest.py           # DigestSubscription (weekly overview email)
│   │   ├── debriefing.py       # DebriefingRecord, DebriefingQuestion
│   │   └── feedback.py         # UserFeedback
│   ├── routes/                 # Flask blueprints (one per feature area)
│   │   ├── __init__.py
│   │   ├── auth.py             # Login, logout, password reset, registration
│   │   ├── setup.py            # First-run setup wizard
│   │   ├── admin.py            # Dashboard, audit log, permissions overview
│   │   ├── admin_digest.py     # Weekly digest subscription management
│   │   ├── app_settings.py     # SMTP & app settings (admin)
│   │   ├── backup.py           # DB backup/restore (admin)
│   │   ├── users.py            # User management, invites, credentials
│   │   ├── master_events.py    # Master Event CRUD
│   │   ├── events.py           # Event CRUD, lifecycle, spot assignment, calendar feed
│   │   ├── assignments.py      # Assignment claim/release
│   │   ├── templates.py        # Event template CRUD
│   │   ├── qualifications.py   # Qualification (credential type) CRUD
│   │   ├── equipment.py        # Equipment types, items, issuance, event plans
│   │   ├── import_events.py    # Bulk event import from paste
│   │   ├── reports.py          # Reports (staffing, statistics, glossary)
│   │   ├── debriefing.py       # Post-event debriefing forms
│   │   ├── work_report.py      # Výkaz práce (monthly work-report XLSX)
│   │   ├── feedback.py         # User feedback submission
│   │   ├── main.py             # Dashboard, health check
│   │   └── dev.py              # Dev-only routes (disabled in production)
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── base.html           # Base layout with nav, CSP-safe JS config
│   │   ├── macros/             # Reusable macros (help_icon, pagination, …)
│   │   ├── auth/
│   │   ├── events/
│   │   ├── equipment/
│   │   └── …
│   ├── static/
│   │   ├── css/main.css        # Custom utility classes (no inline styles — CSP)
│   │   ├── js/                 # FullCalendar, per-page JS modules
│   │   └── img/
│   └── email/                  # Email templates (Jinja2, plain-text + HTML)
│
├── scheduler/
│   └── main.py                 # Background task runner (schedule library)
│                               # Tasks: event auto-transitions, reminder emails,
│                               #        digest emails, work-report cleanup
│
├── migrations/                 # Flask-Migrate (Alembic) migration scripts
│   └── versions/
│
├── tests/
│   ├── conftest.py             # Fixtures: app, DB, client per role; AppSettings seed
│   ├── test_auth.py
│   ├── test_events.py
│   ├── test_assignments.py
│   ├── test_equipment.py
│   ├── test_admin.py
│   ├── test_admin_digest.py
│   ├── test_debriefing.py
│   ├── test_import_events.py
│   ├── test_master_events.py
│   ├── test_qualifications.py
│   ├── test_reports.py
│   ├── test_templates.py
│   ├── test_users.py
│   ├── test_work_report.py
│   └── …
│
├── scripts/
│   ├── seed_dev.py             # Populates DB with realistic mock data for local dev
│   └── e2e-entrypoint.sh       # Docker entrypoint for E2E web container
│
├── e2e_tests/                  # Playwright browser tests (NOT run by default pytest)
│   ├── conftest.py             # Fixtures: base_url, logged_in_page
│   ├── test_login_flow.py
│   ├── test_create_event.py
│   └── test_smoke_navigation.py
│
├── Dockerfile                  # Single image for both web and scheduler containers
├── docker-compose.yml          # Local dev: web + scheduler + postgres (hot reload)
├── docker-compose.e2e.yml      # E2E tests: db-e2e + web-e2e + playwright runner
├── render.yaml                 # Render.com Blueprint: all services as code
├── .env.example                # Template for required env vars — COMMIT THIS
├── .env                        # Actual secrets — NEVER COMMIT (in .gitignore)
├── .dockerignore
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Dev/test extras: pytest, faker, pytest-cov
├── requirements-e2e.txt        # E2E test deps: pytest-playwright
├── Makefile                    # Shortcuts: make e2e, make test
├── tox.ini                     # tox envs: py314 (unit), e2e (playwright)
├── architecture.md
└── DEVOPS.md                   # This file
```

---

## Container Architecture

Two containers share a single Docker image; they run different commands:

| Container | Dev command (docker-compose) | Prod command (Dockerfile CMD) | Purpose |
|---|---|---|---|
| `web` | `flask run --host=0.0.0.0 --debug` | `gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} "app:create_app()"` | Serves the Flask web application |
| `scheduler` | `python scheduler/main.py` | `python scheduler/main.py` | Background tasks: auto-transitions, reminders, digests, file cleanup |

Both containers share the same codebase and connect to the same PostgreSQL database via `DATABASE_URL`.
The `docker-entrypoint.sh` runs `flask db upgrade` + `flask verify-schema` before starting either process.

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

This creates realistic test users, credentials, master events, events, assignments, and equipment. Running it multiple times is safe (idempotent).

### Run database migrations

```bash
# Create a new migration after model changes
docker compose exec web flask db migrate -m "describe the change"

# Apply pending migrations
docker compose exec web flask db upgrade
```

### Run tests

```bash
# Inside the running web container (day-to-day dev)
docker compose exec web pytest

# Via tox (mirrors CI — same pinned deps)
docker compose exec web tox -e py314
```

Or directly on the host with a local Python venv (`requirements-dev.txt` installed)
and `DATABASE_URL` / `TEST_DATABASE_URL` pointing at a running Postgres:

```bash
pip install -r requirements-dev.txt

# Run directly — set TEST_DATABASE_URL to use an existing DB,
# or let testcontainers auto-spin a postgres:17 container if not set
pytest

# Via tox — same behaviour
tox -e py314
```

### Run E2E browser tests (Playwright)

End-to-end tests use real browsers (Chromium, Firefox, WebKit) driven by
[Playwright](https://playwright.dev/python/) to test rendered pages, JS
validation, form submission, and navigation. Everything runs in Docker
containers — nothing is installed on the host.

**Architecture:** `docker-compose.e2e.yml` spins up three containers:

| Container | Image | Purpose |
|-----------|-------|---------|
| `db-e2e` | `postgres:17-alpine` | Fresh Postgres on tmpfs (destroyed after each run) |
| `web-e2e` | App Dockerfile | Runs migrations, seeds data (`seed_dev.py`), serves Flask |
| `e2e` | `mcr.microsoft.com/playwright/python` | Runs Playwright tests against `http://web-e2e:5000` |

**How to run:**

```bash
# Using Make (recommended)
make e2e

# Or using tox
tox -e e2e

# Or directly with Docker Compose
docker compose -f docker-compose.e2e.yml up --build --abort-on-container-exit --exit-code-from e2e
docker compose -f docker-compose.e2e.yml down -v
```

**Cleanup after a failed run:**

```bash
make e2e-down
# or: docker compose -f docker-compose.e2e.yml down -v
```

**Test files** live in `e2e_tests/` (separate from `tests/`) and are never
included in the regular `pytest` or CI runs.

**First run** pulls the Playwright Docker image (~1.5 GB) and builds the app
image. Subsequent runs are faster thanks to Docker layer caching.

**Adding new E2E tests:** create a `test_*.py` file in `e2e_tests/`. Use the
`logged_in_page` fixture from `e2e_tests/conftest.py` for tests that need an
authenticated session (logs in as the admin dev user automatically).

---

## docker-compose.yml

The embedded summary below reflects the actual file. Key points:

- `web` uses `flask run --debug` (hot reload) in dev; production uses gunicorn via `CMD` in the Dockerfile
- Both containers mount `.:/app` so local code changes reflect immediately
- Both containers have healthchecks; the scheduler checks a heartbeat file written every ~10 s
- `db` uses **postgres:17-alpine** and a custom `postgres.conf` (tuned checkpoint settings for WSL2 stability — see Known Issues)
- `stop_grace_period: 60s` on `db` gives PostgreSQL time to checkpoint cleanly on shutdown

```yaml
services:
  web:
    build:
      context: .
      args:
        GIT_COMMIT: ${GIT_COMMIT:-dev}
    command: flask run --host=0.0.0.0 --debug
    restart: unless-stopped
    volumes:
      - .:/app          # Hot reload: local code changes reflect immediately
    env_file: .env
    ports:
      - "5000:5000"
    depends_on:
      db:
        condition: service_healthy

  scheduler:
    build:
      context: .
      args:
        GIT_COMMIT: ${GIT_COMMIT:-dev}
    command: python scheduler/main.py
    restart: unless-stopped
    volumes:
      - .:/app
    env_file: .env
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:17-alpine
    restart: unless-stopped
    stop_grace_period: 60s   # Gives PostgreSQL time to checkpoint cleanly
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db-init:/docker-entrypoint-initdb.d:ro
      - ./postgres.conf:/etc/postgresql/postgresql.conf:ro
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
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
      - "5432:5432"

volumes:
  postgres_data:
```

---

## Dockerfile

```dockerfile
FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY . .

# Embed git commit hash at build time:
#   docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) .
ARG GIT_COMMIT=dev
ENV GIT_COMMIT=${GIT_COMMIT}

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} \"app:create_app()\""]
```

`docker-entrypoint.sh` runs `flask db upgrade` then `flask verify-schema` on every container start before handing off to the CMD process. If `verify-schema` detects missing tables/columns the container exits immediately rather than serving broken traffic.

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

## Render.com Deployment

MedCover deploys to [Render.com](https://render.com) using the **Blueprint** (`render.yaml`) for infrastructure-as-code. All three services (web, scheduler, managed Postgres) are defined in the file.

### Services

| Service | Type | Command |
|---|---|---|
| `medcover-web` | Web (Docker) | `gunicorn -w 2 -b 0.0.0.0:$PORT "app:create_app()"` |
| `medcover-scheduler` | Background Worker (Docker) | `python scheduler/main.py` |
| `medcover-db` | Managed PostgreSQL 17 | — |

Both `web` and `scheduler` are built from the same `Dockerfile`. Render injects `$PORT` for the web service; gunicorn binds to it. The scheduler receives no external traffic so `$PORT` is irrelevant for it.

### First-time deploy

1. **Create a Render account** and connect it to the GitHub repository (`spidermila/MedCover`).
2. **Apply the Blueprint:** Render Dashboard → Blueprints → Connect Repository → `render.yaml` will provision all services automatically.
3. **Database migrations** run automatically via `docker-entrypoint.sh` (`flask db upgrade`) on every container start.
4. **First-run setup wizard:** after the web service is live, navigate to the app URL. The setup wizard will appear on first visit — configure the application name, admin account, and SMTP settings there.

### Continuous deployment

Every merge to `main` can trigger a Render deploy via the deploy hook. To enable:

1. Copy the deploy hook URL from Render Dashboard → `medcover-web` → Settings → Deploy Hook.
2. Add it as a GitHub secret: `Settings → Secrets → Actions → RENDER_DEPLOY_HOOK_URL`.
3. Remove the `if: false` condition from `.github/workflows/deploy.yml`.

Once enabled, every merge to `main` triggers:
```bash
curl -f -X POST "${{ secrets.RENDER_DEPLOY_HOOK_URL }}"
```

### Environment variables

Render's Blueprint auto-provisions:

| Variable | Source |
|---|---|
| `FLASK_ENV` | Hardcoded `production` in render.yaml |
| `SECRET_KEY` | Auto-generated by Render on first deploy |
| `DATABASE_URL` | Injected from managed Postgres (includes `?sslmode=require`) |

SMTP credentials are **not** environment variables — they are configured through the web UI setup wizard and stored Fernet-encrypted in the database.

### Ephemeral filesystem — important limitations

Render's filesystem is **wiped on every deploy**. Two features are affected:

- **Scheduled backups** (`backup_dir`, default `"backups"`): backup zip files written to the local filesystem will not survive a redeploy. For production use, change `backup_dir` in Admin → Settings to a mounted persistent path — or use the manual backup/restore feature and store the zip externally.
- **Work report files** (`instance_path/work_report/`): these xlsx files are already cleaned up after 1 day, so ephemeral storage is acceptable.

> **Managed Postgres is not affected** — Render's managed database is persistent and fully backed up by Render independently of the filesystem.

---

## Render.com Blueprint (render.yaml)

`render.yaml` defines all Render services as code. Committing this file means the entire infrastructure can be recreated from the repo.

```yaml
services:
  - name: medcover-web
    type: web
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: gunicorn -w 2 -b 0.0.0.0:$PORT "app:create_app()"
    branch: main
    autoDeploy: true
    healthCheckPath: /health
    envVars:
      - key: FLASK_ENV
        value: production
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: medcover-db
          property: connectionString

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
      - key: SECRET_KEY
        fromService:
          name: medcover-web
          type: web
          property: environmentVariableValue
          envVarKey: SECRET_KEY
      - key: DATABASE_URL
        fromDatabase:
          name: medcover-db
          property: connectionString

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
  ├── lint job: pre-commit (flake8, mypy, pyupgrade, whitespace)
  └── test job: postgres:17 service → pytest --cov
      ↓
Review, approve, merge
```

### On merge to main (`deploy.yml`)

```
Merge to main
      ↓
GitHub Actions: deploy.yml  ← currently disabled (Render not yet configured)
  - Trigger Render deploy via POST to deploy hook
      ↓
Render: pulls latest image, runs migrations via entrypoint, restarts web + scheduler
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
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - name: Install pre-commit
        run: pip install pre-commit
      - name: Run pre-commit hooks
        run: pre-commit run --all-files
    # Runs: trailing-whitespace, end-of-file-fixer, check-yaml,
    #       flake8, pyupgrade, mypy

  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:17-alpine
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
      TEST_DATABASE_URL: postgresql://medcover:testpassword@localhost:5432/medcover_test
      FLASK_ENV: testing
      SECRET_KEY: ci-test-secret-not-real

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - name: Install dependencies
        run: pip install --require-hashes -r requirements-dev.txt
      - name: Run tests with coverage
        run: pytest --cov=app --cov-report=term-missing --cov-report=xml
      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-report
          path: htmlcov/
```

### .github/workflows/deploy.yml

**Currently disabled** (`if: false`). Render deployment is not yet configured. To enable:

1. Create a Render account and set up services per the render.yaml Blueprint
2. Copy the deploy hook URL from Render Dashboard → your service → Settings
3. Add it as GitHub secret: Settings → Secrets → Actions → `RENDER_DEPLOY_HOOK_URL`
4. Remove the `if: false` condition from `deploy.yml`

Once enabled, every merge to `main` triggers a Render deploy via:

```bash
curl -f -X POST "${{ secrets.RENDER_DEPLOY_HOOK_URL }}"
```

---

## Versioning & Changelog

This project uses **[Semantic Versioning](https://semver.org/)** (`MAJOR.MINOR.PATCH`).

| Bump | When |
|---|---|
| `PATCH` | Bug fixes, small UI tweaks, no new features |
| `MINOR` | New features, backwards-compatible |
| `MAJOR` | Breaking changes or a major milestone (e.g. production launch) |

### Files

| File | Purpose |
|---|---|
| `VERSION` | Single source of truth — one line, e.g. `0.9.1` |
| `CHANGELOG.md` | English, [Keep a Changelog](https://keepachangelog.com) format — for developers and GitHub |
| `app/templates/main/changelog.html` | Czech *Změny ve verzích* — rendered in the app at `/changelog` for all logged-in users |

### APP_VERSION vs GIT_COMMIT

Both are available in `app.config` and in Jinja2 templates as `config.APP_VERSION` / `config.GIT_COMMIT`:

| Key | Value | Purpose |
|---|---|---|
| `APP_VERSION` | `0.9.0` (from `VERSION` file) | Human-readable semantic version; shown in admin dashboard; stored in `UserFeedback.app_version` |
| `GIT_COMMIT` | `abc1234` (from Docker build arg) | Exact commit; used for static file cache-busting in `app/__init__.py`; shown in admin dashboard as a GitHub link |

`GIT_COMMIT` defaults to `"dev"` outside Docker (local dev, tests).

### Release process

```
1. Create a feature branch (or use the last feature branch for the release)

2. Update VERSION
   echo "0.9.1" > VERSION

3. Update CHANGELOG.md (English)
   - Move items from [Unreleased] into a new [0.9.1] - YYYY-MM-DD section
   - Keep the [Unreleased] section at the top (empty for now)
   - Update the compare URLs at the bottom

4. Update app/templates/main/changelog.html (Czech)
   - Add a new card for version 0.9.1 above the previous release card
   - Keep the "Chystané změny" card at the top (empty)

5. Commit:
   git add VERSION CHANGELOG.md app/templates/main/changelog.html
   git commit -m "chore: release v0.9.1"

6. Open PR, merge to main

7. Tag the merge commit on main:
   git checkout main && git pull
   git tag v0.9.1
   git push origin v0.9.1
```

### Keeping changelogs in sync

Both the English `CHANGELOG.md` and the Czech `changelog.html` must be updated together on every release.

**Different audiences, different content:**

| File | Audience | What to include |
|---|---|---|
| `CHANGELOG.md` | Developers, GitHub | Everything: features, bug fixes, security changes, infra, refactors, migrations |
| `changelog.html` | End users (Czech) | **Only changes that affect the user's workflow or are visible in the UI** |

**Czech changelog rules** — include only if the user would notice or care:
- New features and screens they can interact with
- Changes to existing workflows (e.g. a form field added/removed, a step changed)
- Bug fixes that were visibly wrong to the user
- New or changed automatic emails they receive

**Never include** in the Czech changelog:
- Security hardening (CSRF, CSP, TLS, encryption algorithms) — implement silently
- Performance optimisations, caching, query improvements
- Refactors, code cleanup, constant extractions
- Database migrations, Alembic, infrastructure changes
- Developer tooling, CI, test additions
- Internal admin features invisible to regular members (audit log internals, outbox traceability)
- Version bumps, changelog metadata itself

---

## Notification Catalog

The app sends 10 types of email notifications.  The **authoritative source of truth** is
`NOTIFICATION_CATALOG` in `app/mail.py`.  The admin UI at `/admin/notifications/` renders
this list and exposes per-type toggles stored in `AppSettings`.

### Rule: always update the catalog when changing notifications

**Whenever you add, rename, remove, or change the recipients/trigger of any `send_*`
function in `app/mail.py`, you MUST:**

1. Update or add the corresponding entry in `NOTIFICATION_CATALOG` (same file).
2. If the new notification should be togglable: add a `notify_<code>` boolean column
   to `AppSettings` (model + Alembic migration, default `True`) and set `settings_field`
   in the catalog entry accordingly.
3. Call `_is_notify_enabled("notify_<code>")` at the top of the new `send_*` function.
4. Pass `notification_type="<code>"` to `_enqueue()`.
5. Update `CHANGELOG.md` and `app/templates/main/changelog.html`.

Failure to update the catalog means the admin page will be out of sync with the actual
behaviour of the application.

### Notification toggles

Five toggle groups are stored in `AppSettings`:

| Field | Controls |
|---|---|
| `notify_assignment` | `send_assignment_confirmed`, `send_assignment_released` |
| `notify_event_lifecycle` | `send_event_published`, `send_assignments_opened` |
| `notify_event_cancelled` | `send_event_cancelled` |
| `notify_unfilled_reminder` | `send_unfilled_spots_reminder` (scheduler) |
| `notify_debriefing` | `send_debriefing_invitation` |

Auth-related notifications (`account_activated`, invite, password reset, admin digest)
are always-on and cannot be toggled.

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

## Security Notes

### Content Security Policy (CSP)

The app sets a CSP header in all non-dev environments via `@app.after_request` in `app/__init__.py`:

```
default-src 'self';
script-src  'self' https://cdn.jsdelivr.net;
style-src   'self' https://cdn.jsdelivr.net 'unsafe-inline';
font-src    'self' https://cdn.jsdelivr.net;
img-src     'self' data:;
connect-src 'self' https://cdn.jsdelivr.net;
```

**Why `style-src` includes `'unsafe-inline'`:** FullCalendar v6 injects inline styles at runtime to render its calendar grid. There is no practical workaround without abandoning FullCalendar or adding per-request nonces. CSS `'unsafe-inline'` does not enable script execution, so the security impact is limited.

**Why `script-src` does NOT include `'unsafe-inline'`:** All JS is in external files. There are no `onclick`/`onchange`/`onsubmit` attributes in any template — inline handlers were removed in PR #93 and kept clean thereafter. This is the more important constraint to maintain.

**Why `https://` is explicit:** The scheme-free `cdn.jsdelivr.net` form is interpreted as the current page's scheme. Over HTTP it works, but the app is served over HTTPS in production, and an HTTP CDN resource would be blocked as mixed content. Always use `https://cdn.jsdelivr.net` in the CSP.

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

`scripts/seed_dev.py` creates a realistic dataset. Safe to run multiple times — idempotent.

**Dev accounts** (password: `devpassword`, email format: `dev.<role>@medcover.local`):

| Role | Email | Description |
|---|---|---|
| Admin | `dev.admin@medcover.local` | Full system access |
| Coordinator | `dev.coordinator@medcover.local` | Create/manage events |
| Member | `dev.member@medcover.local` | Join events, submit debriefings |
| Viewer | `dev.viewer@medcover.local` | Read-only access |
| Debrief Manager | `dev.debrief@medcover.local` | View/manage confidential debriefing records |
| Inactive | `dev.inactive@medcover.local` | Registered but not yet activated |

**Also seeded:**
- All Roles, Permissions (synced to `ROLE_PERMISSIONS` in `role.py`)
- Standard credential hierarchy (Záchranář, Zdravotník, Řidič, etc.)
- 2 named Master Events + the default General ME
- ~10 Events in various lifecycle states (planned, published, completed, cancelled)
- Assignments, equipment types, personal and shared items
- Completed events with DebriefingRecords
- AppSettings (id=1, setup_complete=True)

**After changing role permissions in `role.py`,** re-run the seeder to sync:

```bash
docker compose exec web python scripts/seed_dev.py
```

Or on the test server:
```bash
ssh <user>@<host> "cd /path/to/MedCover && docker compose exec web python scripts/seed_dev.py"
```

---

## Temporary File Storage

### Výkaz práce xlsx files

Generated monthly work-report files are stored in the Flask `instance/` directory:

```
instance/
  work_report/
    <user-uuid>/
      <year>-<MM>.xlsx   (e.g. 2026-05.xlsx)
```

- Each user has their own subdirectory; generating a new report for the same month overwrites the previous file.
- Files are **automatically deleted after 1 day** by the `cleanup_work_report` scheduler task (runs hourly in the `scheduler` container).
- **Do not commit these files** — the `instance/` directory is gitignored.
- The `holidays` Python package (Czech locale) is used to detect Czech public holidays for correct cell colouring. It is declared in `requirements.txt`.

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
