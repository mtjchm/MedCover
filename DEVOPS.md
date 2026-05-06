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
docker compose exec web pytest
```

Or without Docker (requires a local Python env):

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
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
FROM python:3.12-slim

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
| `MAIL_SERVER` | SMTP relay hostname | `smtp.example.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USERNAME` | SMTP auth username | `noreply@example.com` |
| `MAIL_PASSWORD` | SMTP auth password | *(secret)* |
| `MAIL_DEFAULT_SENDER` | From address for all outbound email | `MedCover <noreply@example.com>` |

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
      - key: MAIL_SERVER
        sync: false          # Set manually in Render dashboard
      - key: MAIL_PORT
        sync: false
      - key: MAIL_USERNAME
        sync: false
      - key: MAIL_PASSWORD
        sync: false
      - key: MAIL_DEFAULT_SENDER
        sync: false

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
      - key: MAIL_SERVER
        sync: false
      - key: MAIL_PORT
        sync: false
      - key: MAIL_USERNAME
        sync: false
      - key: MAIL_PASSWORD
        sync: false
      - key: MAIL_DEFAULT_SENDER
        sync: false

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
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt -r requirements-dev.txt

      - name: Run migrations
        run: flask db upgrade

      - name: Run tests
        run: pytest --cov=app --cov-report=term-missing
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
