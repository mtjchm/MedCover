"""
Seed script for the development environment.

Creates roles, permissions, and one dev user account per role.
Safe to run multiple times — checks for existing data before inserting.

Usage:
    DATABASE_URL=... SECRET_KEY=... FLASK_ENV=development python scripts/seed_dev.py

Or from within the Docker web container:
    docker compose exec web python scripts/seed_dev.py
"""

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import UserAccount
from app.models.role import Role, Permission, ALL_PERMISSIONS, ROLE_PERMISSIONS
from app.routes.dev import DEV_ACCOUNTS


def seed():
    app = create_app("development")

    with app.app_context():
        if not app.config.get("DEV_LOGIN_ENABLED"):
            print("ERROR: DEV_LOGIN_ENABLED is not set. Refusing to seed.")
            print("Add DEV_LOGIN_ENABLED=true to your .env file.")
            sys.exit(1)

        print("Seeding permissions...")
        for perm_data in ALL_PERMISSIONS:
            if not db.session.scalar(db.select(Permission).where(Permission.code == perm_data["code"])):
                db.session.add(Permission(code=perm_data["code"], description=perm_data["description"]))
        db.session.flush()

        print("Seeding roles and assigning permissions...")
        for role_name, perm_codes in ROLE_PERMISSIONS.items():
            role = db.session.scalar(db.select(Role).where(Role.name == role_name))
            if not role:
                role = Role(name=role_name)
                db.session.add(role)
                db.session.flush()

            existing_codes = {p.code for p in role.permissions}
            for code in perm_codes:
                if code not in existing_codes:
                    perm = db.session.scalar(db.select(Permission).where(Permission.code == code))
                    if perm:
                        role.permissions.append(perm)

        db.session.flush()

        print("Seeding dev user accounts...")
        role_map = {
            "admin": Role.ADMIN,
            "coordinator": Role.COORDINATOR,
            "member": Role.MEMBER,
            "viewer": Role.VIEWER,
            "inactive": Role.MEMBER,  # inactive user has Member role but is_active=False
        }

        for account_def in DEV_ACCOUNTS:
            email = account_def["email"]
            existing = db.session.scalar(db.select(UserAccount).where(UserAccount.email == email))
            if existing:
                print(f"  {email} already exists, skipping.")
                continue

            user = UserAccount(
                email=email,
                name=f"Dev {account_def['label']}",
                is_active=(account_def["role"] != "inactive"),
            )
            user.set_password("devpassword")

            role_name = role_map[account_def["role"]]
            role = db.session.scalar(db.select(Role).where(Role.name == role_name))
            if role:
                user.roles.append(role)

            db.session.add(user)
            status = "inactive" if account_def["role"] == "inactive" else "active"
            print(f"  Created {email} ({status})")

        db.session.commit()
        print("\nDone. Dev accounts (password: devpassword):")
        for a in DEV_ACCOUNTS:
            print(f"  {a['role']:12s}  {a['email']}")


if __name__ == "__main__":
    seed()
