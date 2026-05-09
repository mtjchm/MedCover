# MedCover — Copilot Instructions

## Project Overview
MedCover is a Flask web application for the **Czech Red Cross** that replaces a Google Sheets medical cover planning solution. It manages events, spot assignments, user roles, equipment and reporting.

**Stack:** Python 3.14 · Flask 3 · PostgreSQL 17 · SQLAlchemy / Flask-Migrate · Flask-Login · Flask-Mail · Bootstrap 5.3 · Docker Compose · GitHub Actions CI · Render.com (future production)

**Architecture doc:** `architecture.md` — always keep it up-to-date when making decisions or implementing requirements. Every significant decision must be reflected there (as an AD entry if applicable).

---

## Always-On Requirements

### Language
- All UI text, flash messages, form labels, email body text must be in **Czech**.
- Code, comments, commit messages, and documentation are in **English**.

### Concurrency — CRITICAL
> **The app is used by 10+ people simultaneously.**

Race conditions are a first-class concern, especially for spot assignment:

- **Spot assignment (pessimistic locking):** When claiming or releasing an EventSpot, always use `query.with_for_update()` to lock the row inside a transaction before checking availability. Never check then write without the lock.
- **General entity edits (optimistic locking):** Entities that may be edited by multiple admins/coordinators simultaneously (Event, UserAccount, AppSettings, MasterEvent) should carry a `version` integer column. Increment it on every write. Catch `sqlalchemy.exc.StaleDataError` and return a 409 with a user-friendly message ("Záznam byl mezitím změněn, načtěte stránku znovu.").
- **Database constraints as last resort:** `assignment.spot_id` has a UNIQUE constraint — this is a safety net, not the primary defence. Do not rely on it instead of proper locking.
- **Transactions:** Every write that reads-then-writes (check eligibility → create assignment) must happen in a single DB transaction. Never commit partial state.
- **Never** use `db.session.add()` + `db.session.commit()` for spot assignment without first acquiring a row-level lock.

### Security
- Never expose SMTP password, SECRET_KEY, or DATABASE_URL in logs, templates, or API responses.
- SMTP password is stored Fernet-encrypted in `AppSettings`; decrypt only at send time.
- `DEV_LOGIN_ENABLED` is hardcoded `False` in base `Config` and `ProductionConfig`. Only `DevelopmentConfig` reads the env var.
- All write routes must be protected by `@login_required` + `has_permission()` check.
- Registration is invite-only. No open self-registration.
- **CSRF:** All POST forms must include `{{ csrf_token() }}` as a hidden field (Flask-WTF). AJAX POST requests must send the token in the `X-CSRFToken` header. Never skip CSRF on a state-changing route.
- **Input validation:** Every route that accepts user input must validate server-side (type, length, range, business rules). Client-side JS validation (validate.js) is for UX only — never the sole check.
- **XSS:** Jinja2 auto-escape is always on. Never use `{{ var | safe }}` for user-supplied content.
- **SQL injection:** All DB access via SQLAlchemy ORM. Raw `text()` with string interpolation is prohibited.
- **Transport:** Production `DATABASE_URL` must include `?sslmode=require`. See AD13.

### Audit Log
- Every create, edit, delete, and status change on every entity must produce an `AuditLogEntry` row. This is a hard requirement, not optional.
- Include `actor_id`, `action_type`, `entity_type`, `entity_id`, `summary`, and `changes_json` (before/after dict for edits).

### Testing
- Run `pytest tests/` before every commit. All tests must pass.
- For multi-Python testing use `tox -e py314` (or just `tox`).
- Tests use the dev DB (`medcover_dev`) pointed to by `DATABASE_URL` env var.
- The `conftest.py` fixture seeds `AppSettings(id=1, setup_complete=True)` so the setup guard doesn't block tests.
- When adding new routes, add corresponding smoke/integration tests.

### Documentation
- After every change, check whether it affects `README.md`, `DEVOPS.md`, `architecture.md`, or `mvp.md` and update them immediately.
- Never leave these files out of sync with the actual implementation — outdated documentation is worse than no documentation.

### Tests
- After every change, check whether a test should be added or updated. Coverage must not decrease.
- JS-only validation must be backed by matching server-side validation so it is testable and cannot be bypassed.

### Code Style
- Type hints on all function signatures.
- Use `db.session.get(Model, pk)` instead of `.query.get(pk)` (deprecated).
- Use `lazy="selectin"` for relationships loaded in list views to avoid N+1.
- Permission checks via `current_user.has_permission("code")` or `has_any_permission(...)`.
- Abort with `abort(403)` on permission failure, not redirect.
- SQL boolean comparisons: write `col.is_(True)` / `col.is_(False)`, **not** `col == True` / `col == False`. Never silence E712 with `# noqa`.

### Shared Helpers — use these, do not reinvent
Two modules hold all reusable building blocks. **Always import the existing helper instead of writing the inline pattern.** If a duplication appears in 3+ places, lift it into one of these modules.

**`app/utils.py` — request-handling helpers**
- `audit(action, entity_type, entity_id, summary, changes=None)` — the only sanctioned way to write an `AuditLogEntry`. Hardcodes `actor_id=current_user.id`. Use raw `db.session.add(AuditLogEntry(...))` only when the actor is `None` (pre-login flows like password reset) or differs from `current_user` (e.g. backup restore writing as a saved actor_id after session wipe).
- `require_permission(*codes)` — replaces `if not current_user.has_permission("X"): abort(403)`. Pass multiple codes for any-of semantics. Call at the top of every protected view.
- `get_or_404(Model, pk)` — replaces `obj = db.session.get(Model, pk); if obj is None: abort(404)`.
- `check_version_conflict(obj, form_value)` — optimistic-locking check for edit forms. Returns `True` on conflict; caller flashes `RECORD_MODIFIED_MSG` and re-renders the form.
- `parse_enum(enum_class, value, default=None)` — safe coercion of form values to enum members.
- `RECORD_MODIFIED_MSG` — the canonical Czech flash message for stale-data conflicts. Do not hand-write this string.
- `external_url_for(endpoint, **values)` — absolute URLs that honour `AppSettings.app_base_url`. Use for any URL embedded in outbound email.
- `diff_changes(before, after)` — produces the `changes_json` dict for `audit(..., changes=...)`.

**`app/queries.py` — reusable SELECT builders**
- `active_users_list()` / `active_users_query()` — active users ordered by name. Use everywhere a coordinator/spot-assignment dropdown is rendered.
- `active_master_events_list()` — non-archived master events, general-first then by name.
- Add new helpers here whenever a non-trivial query appears in 3+ routes; keep return types and ordering uniform.

**Model-level helpers** — when a query/eligibility check is *about a single entity*, put it on the model (e.g. `Event.eligible_unfilled_spots_for(user, excluded_ids)`), not in the route. Routes should be thin glue between request parsing, model calls, helpers and templates.

### Refactoring Patterns (apply continuously, not as a one-off)
- **Early return over deep nesting.** Maximum 3 indent levels in view functions. If `request.method != "POST"` wraps the entire body, invert it: handle the GET path first, return, then write the POST path flat.
- **Extract helpers when a function exceeds ~60 lines or 3 nesting levels.** Prefer module-private `_parse_*`, `_apply_*`, `_validate_*` helpers in the same file over class methods, unless the helper logically belongs on a model.
- **No duplicated SELECT statements.** If you see the same `db.select(...)` shape in two routes, lift it to `app/queries.py` before adding the third copy.
- **No duplicated `_audit` / `_require_permission` / `_get_or_404` defined inside route modules.** They already exist in `app/utils.py` — import them.
- **One transaction per write.** Read-then-write sequences (eligibility check → insert) must be inside a single `db.session` transaction with proper locking (see Concurrency section).


---

## Architecture Decisions Summary (quick reference)

| AD | Decision |
|---|---|
| AD01 | Roles hardcoded (Admin, Coordinator, Member, Viewer) |
| AD02 | Maximum-granularity object permissions (53 codes) |
| AD03 | Invite-only registration; admin activates accounts |
| AD04 | Flask + PostgreSQL + Docker Compose + Render |
| AD05 | Email + password auth; forgot-password flow |
| AD06 | TBD (assignment handover) |
| AD07 | Unified Credential hierarchy (self-referential M2M); `can_be_filled_by()` |
| AD08 | FullCalendar JS (Phase 2) |
| AD09 | Docker Compose; 3 containers: web, scheduler, db |
| AD10 | Separate scheduler container (`schedule` lib) |
| AD11 | DB-backed AppSettings; SMTP creds Fernet-encrypted; setup wizard on first run |
| AD12 | Concurrency: pessimistic locking for spot assignment; optimistic locking (version column) for general edits |
| AD13 | Transport security: TLS at Render edge + `sslmode=require` for DB; no mTLS between containers (Render private network isolation sufficient) |
| AD14 | CSRF: Flask-WTF tokens on all POST forms; server-side validation primary; client-side JS (validate.js) for UX; CSP header in production |

---

## Copilot Agent Behaviour
- **Never use background agents / background tasks.** All work must be done synchronously in the current session so the user can follow along. Do not use `mode="background"` on the task tool.

---

## Branch & PR Convention
- One feature branch per logical unit: `feat/<short-name>`
- CI must pass before merging (GitHub Actions: lint-free import, `flask db upgrade`, `pytest`; locally use `tox` for multi-Python validation)
- Never commit directly to `main`
- Co-author all Copilot commits: `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

---

## Key Files
| File | Purpose |
|---|---|
| `architecture.md` | Living architecture document — update on every significant decision |
| `app/models/` | SQLAlchemy models; `__init__.py` must import all models for Alembic |
| `app/routes/` | Flask blueprints; one file per feature area |
| `app/templates/` | Jinja2 templates; extend `base.html`; Czech UI text |
| `app/models/settings.py` | `AppSettings` + `get_settings()`; SMTP password encrypted here |
| `app/utils.py` | Shared helpers: `audit`, `require_permission`, `get_or_404`, `check_version_conflict`, `parse_enum`, `external_url_for`, `diff_changes`, `RECORD_MODIFIED_MSG` |
| `app/queries.py` | Reusable SELECT builders (`active_users_list`, `active_master_events_list`, …) |
| `app/models/role.py` | `ALL_PERMISSIONS` list + `ROLE_PERMISSIONS` mapping — source of truth for seeding |
| `migrations/versions/` | Alembic migrations; generated via `flask db migrate`, applied via `flask db upgrade` |
| `scripts/seed_dev.py` | Idempotent dev seeder — permissions, roles, 5 dev accounts |
| `docker-entrypoint.sh` | Runs `flask db upgrade` on every container start |
| `tests/conftest.py` | Pytest fixtures; seeds AppSettings for test isolation |
| `.env` | Local secrets (gitignored); see `.env.example` for required keys |

---

## MVP Phase Tracker
- ✅ Phase 1: Models, auth flow, setup wizard, admin activation
- 🔲 Phase 2: Event CRUD, Master Event CRUD, event list, FullCalendar, spot assignment
- 🔲 Phase 3: Email notifications, scheduler tasks, debriefing
- 🔲 Phase 4: Audit log UI, equipment inventory, event templates, reports
- 🔲 Phase 5: Admin panel, user profile, mobile polish, full dev seed
