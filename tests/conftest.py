from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from app import create_app
from app.extensions import db as _db
from app.models.role import ALL_PERMISSIONS, ROLE_PERMISSIONS, Permission, Role
from app.models.settings import AppSettings
from app.models.user import UserAccount

# All mutable tables — reference data (role, permission, role_permissions,
# app_settings, alembic_version) is preserved across the suite.
_MUTABLE_TABLES = " ,".join([
    "event_equipment_assignment",
    "event_equipment_plan",
    "equipment_item",
    "equipment_type",
    "debriefing_record",
    "assignment",
    "event_spot",
    "spot_qualifications",
    "spot_template_qualifications",
    "event_spot_template",
    "event_template",
    "event",
    "master_event",
    "user_qualifications",
    "qualification_parents",
    "qualification",
    "registration_invite",
    "digest_metric_snapshot",
    "digest_block",
    "digest_schedule",
    "outbox_email",
    "audit_log_entry",
    "user_feedback",
    "user_roles",
    "user_account",
])

# Base test DB URL (set by pytest-env via pyproject.toml)
_BASE_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://medcover:devpassword@localhost:5432/medcover_test",
)


def _worker_db_url(worker_id: str) -> str:
    """Return a worker-specific DB URL for xdist parallelism.

    Each xdist worker (gw0, gw1, …) gets its own database so that
    concurrent TRUNCATE operations never conflict.  Non-parallel runs
    (worker_id == 'master') use the base URL unchanged.
    """
    if worker_id == "master":
        return _BASE_TEST_DB_URL
    # e.g. medcover_test → medcover_test_gw0
    base, db_name = _BASE_TEST_DB_URL.rsplit("/", 1)
    return f"{base}/{db_name}_{worker_id}"


def _ensure_db_exists(db_url: str) -> None:
    """Create the database if it does not already exist."""
    base, db_name = db_url.rsplit("/", 1)
    maintenance_url = f"{base}/postgres"
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        ).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    engine.dispose()


def _drop_db(db_url: str) -> None:
    """Drop the worker database (only called for worker-specific DBs)."""
    base, db_name = db_url.rsplit("/", 1)
    maintenance_url = f"{base}/postgres"
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        # Terminate open connections before dropping
        conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = :n AND pid <> pg_backend_pid()"
        ), {"n": db_name})
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def app(worker_id: str):
    """Create Flask test application with a worker-specific DB.

    With pytest-xdist each worker gets its own database (medcover_test_gw0,
    medcover_test_gw1, …) so parallel TRUNCATE operations never conflict.
    Without xdist the plain medcover_test DB is used.
    """
    db_url = _worker_db_url(worker_id)
    _ensure_db_exists(db_url)

    flask_app = create_app("testing", db_url=db_url)

    with flask_app.app_context():
        _db.drop_all()   # clear leftover types/tables from previous runs
        _db.create_all()
        _seed_reference_data()
        _db.session.remove()

    yield flask_app

    with flask_app.app_context():
        _db.drop_all()

    # Clean up worker-specific DB; leave the base medcover_test intact
    if worker_id != "master":
        _drop_db(db_url)


@pytest.fixture(scope="session")
def worker_id(request: pytest.FixtureRequest) -> str:
    """Return the xdist worker ID ('gw0', 'gw1', …) or 'master'."""
    return getattr(request.config, "workerinput", {}).get("workerid", "master")


def _seed_reference_data() -> None:
    """Seed roles, permissions and AppSettings — stable data tests depend on."""
    if not _db.session.get(AppSettings, 1):
        _db.session.add(AppSettings(id=1, org_name="Test Org", setup_complete=True))

    for perm_data in ALL_PERMISSIONS:
        if not _db.session.scalar(_db.select(Permission).where(Permission.code == perm_data["code"])):
            _db.session.add(Permission(code=perm_data["code"], description=perm_data["description"]))
    _db.session.flush()

    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        role = _db.session.scalar(_db.select(Role).where(Role.name == role_name))
        if not role:
            role = Role(name=role_name)
            _db.session.add(role)
            _db.session.flush()
        existing_codes = {p.code for p in role.permissions}
        for code in perm_codes:
            if code not in existing_codes:
                perm = _db.session.scalar(_db.select(Permission).where(Permission.code == code))
                if perm:
                    role.permissions.append(perm)

    _db.session.commit()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Truncate all mutable tables after every test to keep tests isolated.

    TRUNCATE ... CASCADE handles FK ordering automatically. The app fixture no
    longer holds a persistent connection, so the ACCESS EXCLUSIVE lock is safe.

    AppSettings is NOT truncated (it is reference data seeded once) but any
    fields that tests may mutate are explicitly reset to their defaults so that
    test order does not matter.
    """
    yield
    with app.app_context():
        _db.session.remove()
        with _db.engine.connect() as conn:
            conn.execute(_db.text(
                f"TRUNCATE TABLE {_MUTABLE_TABLES} RESTART IDENTITY CASCADE"
            ))
            conn.commit()
        # Reset mutable AppSettings fields to their defaults
        settings = _db.session.get(AppSettings, 1)
        if settings:
            settings.dev_email_block = False
            settings.dev_email_allowlist = None
            settings.feedback_enabled = True
            settings.app_base_url = None
            _db.session.commit()
        _db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(app, client):
    """Test client pre-logged in as an activated admin user."""
    with app.app_context():
        _make_user("admin@test.com", "Test Admin", Role.ADMIN)
    _login(client, "admin@test.com")
    return client


@pytest.fixture
def coordinator_client(app, client):
    """Test client pre-logged in as an activated coordinator user."""
    with app.app_context():
        _make_user("coordinator@test.com", "Test Coordinator", Role.COORDINATOR)
    _login(client, "coordinator@test.com")
    return client


@pytest.fixture
def member_client(app, client):
    """Test client pre-logged in as an activated member user."""
    with app.app_context():
        _make_user("member@test.com", "Test Member", Role.MEMBER)
    _login(client, "member@test.com")
    return client


def _make_user(
    email: str,
    name: str,
    role_name: str,
    password: str = "testpass123",
) -> UserAccount:
    """Create a user in the current app context and return it."""
    role = _db.session.scalar(_db.select(Role).where(Role.name == role_name))
    user = UserAccount(email=email, name=name, is_active=True)
    user.set_password(password)
    user.roles = [role]
    _db.session.add(user)
    _db.session.commit()
    return user


def _login(client, email: str, password: str = "testpass123") -> None:
    """Log in via the auth endpoint."""
    client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
