from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id: str):
    from app.models.user import UserAccount
    import uuid
    try:
        return db.session.get(UserAccount, uuid.UUID(user_id))
    except (ValueError, AttributeError):
        return None
