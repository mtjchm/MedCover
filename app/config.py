import os


RESET_TOKEN_MINUTES = 10
INVITE_TOKEN_HOURS = 72


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    # Development and production configs require DATABASE_URL to be set.
    # TestingConfig overrides this with TEST_DATABASE_URL so this may be empty
    # during test runs — that is fine as long as TestingConfig is used.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    DEV_LOGIN_ENABLED = False
    # Short git commit hash injected at Docker build time via ARG GIT_COMMIT.
    # Falls back to "dev" when running outside of Docker (local dev, tests).
    GIT_COMMIT: str = os.environ.get("GIT_COMMIT", "dev")


class DevelopmentConfig(Config):
    DEBUG = True
    DEV_LOGIN_ENABLED = os.getenv("DEV_LOGIN_ENABLED", "false").lower() == "true"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    @classmethod
    def init_app(cls, app: object) -> None:  # type: ignore[override]
        if not os.environ.get("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL environment variable is required.")
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY environment variable is required.")


class TestingConfig(Config):
    TESTING = True
    # Always use the dedicated test database — never the dev/prod DATABASE_URL.
    # This ensures that conftest.py's drop_all() teardown cannot wipe the dev DB.
    SECRET_KEY = os.getenv("SECRET_KEY", "test-secret-not-for-production")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://medcover:devpassword@localhost:5432/medcover_test",
    )
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    # DEV_LOGIN_ENABLED is hardcoded False in base Config — no env var override possible

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    @classmethod
    def init_app(cls, app: object) -> None:  # type: ignore[override]
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url and "sslmode" not in db_url:
            import warnings
            warnings.warn(
                "DATABASE_URL does not include sslmode=require. "
                "Add ?sslmode=require for production security.",
                stacklevel=2,
            )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
