import pytest
from app import create_app
from app.extensions import db as _db
from app.models.role import ALL_PERMISSIONS, ROLE_PERMISSIONS, Permission, Role
from app.models.settings import AppSettings
from app.models.user import UserAccount

# All mutable tables — reference data (role, permission, role_permissions,
# app_settings, alembic_version) is preserved across the suite.
_MUTABLE_TABLES = " ,".join([
    "debriefing_record",
    "assignment",
    "event_spot",
    "spot_credentials",
    "spot_template_credentials",
    "event_spot_template",
    "event_template",
    "event",
    "master_event",
    "user_credentials",
    "credential_parents",
    "credential",
    "registration_invite",
    "outbox_email",
    "audit_log_entry",
    "user_roles",
    "user_account",
])


@pytest.fixture(scope="session")
def app():
    """Create Flask test application, set up schema and seed reference data once."""
    flask_app = create_app("testing")
    with flask_app.app_context():
        _db.create_all()
        _seed_reference_data()
        _db.session.remove()  # Release the connection — tests create their own contexts

    yield flask_app

    with flask_app.app_context():
        _db.drop_all()


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
    """
    yield
    with app.app_context():
        _db.session.remove()
        with _db.engine.connect() as conn:
            conn.execute(_db.text(
                f"TRUNCATE TABLE {_MUTABLE_TABLES} RESTART IDENTITY CASCADE"
            ))
            conn.commit()


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
