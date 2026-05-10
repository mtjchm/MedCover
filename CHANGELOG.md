# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.10.0] - 2026-05-10

### Added
- Notification catalog: admin page (`/admin/notifications/`) listing all 10 email notification types with trigger, recipient scope, and email template names
- Per-type notification toggles: admins can enable/disable 5 operational notification groups (assignment, event lifecycle, event cancelled, unfilled spots reminder, debriefing invitation) directly from the catalog page
- `OutboxEmail.notification_type` field: every enqueued email now records which `send_*` function created it, enabling outbox filtering by notification type
- Welcome email on registration: `send_account_activated` is now called automatically when a user completes invite-link registration (previously only sent on manual admin activation)
- Catalog rule: added documentation requiring the notification catalog to be updated whenever any email notification is added, changed, or removed (DEVOPS.md + copilot-instructions)
- Event change notification (closes #103): assigned users now receive an email when any event detail (name, time, location, description, etc.) is changed; includes old and new values with Czech field labels; controllable via the notification catalog toggle

### Fixed
- Backup timestamps displayed in CET (Europe/Prague) instead of UTC in both the backup management page and the admin digest email (closes #110)

## [0.9.0] - 2026-05-10

### Added
- Authentication: invite-only registration, password reset, auto-activation on invite-link completion
- Brute-force login protection: account lockout after 5 failed attempts (15-minute cooldown)
- User management: roles (Admin, Coordinator, Member, Viewer), 53-code permission system, activate/deactivate
- User profile: dark mode toggle, dashboard horizon setting
- Events: full CRUD, status machine (Draft → Published → Assignments Open → In Progress → Completed / Cancelled)
- Master Events with hierarchy for yearly reporting
- Spot management and assignments with pessimistic row-level locking (no race conditions)
- Responsible Person (RP): assignment, dashboard warning for upcoming events without RP
- Optional spots on events and templates
- Qualifications: CRUD, self-referential hierarchy (`can_be_filled_by`), soft-delete with tombstone
- Event templates: save spot structure for recurring events
- Debriefing: two-stage form (quick + final), Debriefing Manager role, auto-trigger on event completion
- Work report (Výkaz práce): pre-filled xlsx export per month, 24-hour file retention
- User feedback: submit from any page, admin management list
- Admin digest email: configurable block-based content, scheduled delivery
- Equipment management: types and items
- Import: events and users from xlsx/CSV, idempotent, preview + confirm flow
- Reports & statistics: per-user, per-master-event, date-range, CSV export
- Database backup and restore
- Permission matrix page in admin
- Audit log: every create/edit/delete on every entity recorded
- FullCalendar integration: calendar view of events
- Dark mode: full Bootstrap 5.3 CSS-variable support, safe utility class conventions documented
- Badge macros (`macros/badges.html`): centralised, dark-mode-safe badge patterns
- Mobile navigation and responsive layout
- Version and changelog page ("Změny ve verzích") visible to all logged-in users
- App version (`APP_VERSION`) read from `VERSION` file; stored with each feedback submission
- Semantic version shown in admin dashboard alongside git commit hash

### Security
- CSRF protection on all forms (Flask-WTF) and AJAX requests (`X-CSRFToken` header)
- Content Security Policy response headers (production)
- SMTP password stored Fernet-encrypted in `AppSettings`
- Open redirect protection on all `next=` parameters
- `sslmode=require` enforced for production `DATABASE_URL`
- Feedback deletion blocked when `DEV_LOGIN_ENABLED=True` (test environment guard)

[Unreleased]: https://github.com/spidermila/MedCover/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/spidermila/MedCover/releases/tag/v0.9.0
