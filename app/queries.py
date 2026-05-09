"""Reusable SQLAlchemy query builders.

Centralises common ``SELECT`` patterns that previously appeared inline in
multiple route modules.  Keeping them here makes it easier to reason about
performance (eager-load shapes, ordering) and to apply changes in one place.
"""
from __future__ import annotations

from collections.abc import Sequence

from app.extensions import db
from app.models.master_event import MasterEvent
from app.models.user import UserAccount


def active_users_query():  # type: ignore[no-untyped-def]
    """Return a :class:`Select` for active users ordered by name.

    Caller is responsible for executing the statement (``db.session.scalars``
    or :func:`active_users_list` for the common eager-loaded list).
    """
    return db.select(UserAccount).where(UserAccount.is_active.is_(True)).order_by(UserAccount.name)


def active_users_list() -> Sequence[UserAccount]:
    """Return all active :class:`UserAccount` rows ordered by name."""
    return db.session.scalars(active_users_query()).all()


def active_master_events_list() -> Sequence[MasterEvent]:
    """Return non-archived master events ordered (general first, then by name)."""
    return db.session.scalars(
        db.select(MasterEvent)
        .where(MasterEvent.archived.is_(False))
        .order_by(MasterEvent.is_general.desc(), MasterEvent.name)
    ).all()
