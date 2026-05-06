import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        # Ensure AppSettings exists with setup_complete=True so the setup
        # guard doesn't redirect tests to /setup/step1
        from app.models.settings import AppSettings
        row = _db.session.get(AppSettings, 1)
        if row is None:
            _db.session.add(AppSettings(id=1, org_name="Test Org", setup_complete=True))
        else:
            row.setup_complete = True
            row.org_name = row.org_name or "Test Org"
        _db.session.commit()
        _db.session.remove()
        yield app
        # Dispose all connections before dropping tables to avoid hang
        _db.session.remove()
        _db.engine.dispose()
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    """Provide a clean DB transaction per test, rolled back after each test."""
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        yield _db
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()
