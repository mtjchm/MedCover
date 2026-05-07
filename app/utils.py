"""Shared utility helpers for the MedCover application."""
from __future__ import annotations


def diff_changes(before: dict, after: dict) -> dict:
    """Return {field: [old_val, new_val]} for fields whose values changed.

    Compares using string representation so None and '' differences are caught.
    Only includes fields that actually changed — fields with identical values
    before and after are omitted.

    Example:
        before = {"name": "Old", "desc": None}
        after  = {"name": "New", "desc": None}
        → {"name": ["Old", "New"]}
    """
    all_keys = set(list(before.keys()) + list(after.keys()))
    return {
        k: [before.get(k), after.get(k)]
        for k in sorted(all_keys)
        if str(before.get(k)) != str(after.get(k))
    }
