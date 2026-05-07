import os


RESET_TOKEN_HOURS = 2
INVITE_TOKEN_HOURS = 72


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    # MAIL_* settings are stored in AppSettings (DB) and applied at runtime
    # via AppSettings.apply_to_app(). No env-var mail config needed.
    # DEV_LOGIN_ENABLED is intentionally hardcoded False in base and production.
    # Only DevelopmentConfig reads the env var — belt-and-suspenders protection.
    DEV_LOGIN_ENABLED = False


class DevelopmentConfig(Config):
    DEBUG = True
    DEV_LOGIN_ENABLED = os.getenv("DEV_LOGIN_ENABLED", "false").lower() == "true"


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://medcover:testpassword@localhost:5432/medcover_test"
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
