from app.extensions import db


# Many-to-many: Role ↔ Permission
role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permission.id"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "role"

    ADMIN = "Admin"
    COORDINATOR = "Coordinator"
    MEMBER = "Member"
    VIEWER = "Viewer"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    permissions = db.relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )
    # Back-ref to UserAccount via string table name to avoid circular import
    users = db.relationship(
        "UserAccount",
        secondary="user_roles",
        back_populates="roles",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class Permission(db.Model):
    __tablename__ = "permission"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    roles = db.relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


# All permission codes defined in the RBAC table in architecture.md
ALL_PERMISSIONS: list[dict] = [
    # Users
    {"code": "user.view", "description": "View user profiles"},
    {"code": "user.edit_own", "description": "Edit own profile"},
    {"code": "user.edit_any", "description": "Edit any user's profile"},
    {"code": "user.activate", "description": "Activate a user account"},
    {"code": "user.deactivate", "description": "Deactivate a user account"},
    {"code": "user.assign_role", "description": "Assign/unassign roles to users"},
    {"code": "user.assign_credential", "description": "Assign/unassign credentials to users"},
    {"code": "invite.create", "description": "Create registration invites"},
    # Credentials
    {"code": "credential.view", "description": "View credentials"},
    {"code": "credential.create", "description": "Create credentials"},
    {"code": "credential.edit", "description": "Edit credentials"},
    {"code": "credential.delete", "description": "Delete credentials"},
    # Master Events
    {"code": "master_event.view", "description": "View master events"},
    {"code": "master_event.create", "description": "Create master events"},
    {"code": "master_event.edit", "description": "Edit master events"},
    {"code": "master_event.archive", "description": "Archive master events"},
    {"code": "master_event.unarchive", "description": "Unarchive master events"},
    # Events
    {"code": "event.view", "description": "View published events"},
    {"code": "event.view_draft", "description": "View draft events"},
    {"code": "event.create", "description": "Create events"},
    {"code": "event.edit", "description": "Edit events"},
    {"code": "event.publish", "description": "Publish events"},
    {"code": "event.assignments.open", "description": "Open event assignments"},
    {"code": "event.assignments.close", "description": "Close event assignments"},
    {"code": "event.cancel", "description": "Cancel events"},
    {"code": "event.restore", "description": "Restore cancelled events"},
    {"code": "event.delete", "description": "Permanently delete archived events"},
    {"code": "event.assign_own", "description": "Join/leave an event spot"},
    {"code": "event.assign_other", "description": "Assign another user to an event spot"},
    {"code": "event.set_responsible_person", "description": "Set the responsible person for an event"},
    {"code": "event.notification.send", "description": "Manually send event notifications"},
    # Event Templates
    {"code": "event_template.view", "description": "View event templates"},
    {"code": "event_template.create", "description": "Create event templates"},
    {"code": "event_template.edit", "description": "Edit event templates"},
    {"code": "event_template.delete", "description": "Delete event templates"},
    # Equipment
    {"code": "equipment.view", "description": "View equipment"},
    {"code": "equipment_type.create", "description": "Create equipment types"},
    {"code": "equipment_type.edit", "description": "Edit equipment types"},
    {"code": "equipment_type.delete", "description": "Delete equipment types"},
    {"code": "equipment_item.create", "description": "Create equipment items"},
    {"code": "equipment_item.edit", "description": "Edit equipment items"},
    {"code": "equipment_item.delete", "description": "Delete equipment items"},
    {"code": "equipment_item.issue_personal", "description": "Issue personal equipment to a member"},
    {"code": "equipment_item.report_own", "description": "Report status of own issued personal items"},
    {"code": "event.equipment.plan", "description": "Plan required equipment for an event"},
    {"code": "event.equipment.assign", "description": "Assign shared equipment items to an event"},
    # Debriefing
    {"code": "debriefing.submit_own", "description": "Submit own debriefing record"},
    {"code": "debriefing.view_own", "description": "View own debriefing records"},
    {"code": "debriefing.view_all", "description": "View all debriefing records"},
    # Reports
    {"code": "report.view", "description": "View reports"},
    # Audit
    {"code": "audit.view", "description": "View audit log"},
]

# Permissions per role (from RBAC table in architecture.md)
ROLE_PERMISSIONS: dict[str, list[str]] = {
    Role.ADMIN: [p["code"] for p in ALL_PERMISSIONS],  # Admin has all permissions
    Role.COORDINATOR: [
        "user.view", "user.edit_own",
        "invite.create",
        "credential.view",
        "master_event.view", "master_event.create", "master_event.edit",
        "event.view", "event.view_draft", "event.create", "event.edit",
        "event.publish", "event.assignments.open", "event.assignments.close",
        "event.cancel", "event.restore",
        "event.assign_own", "event.assign_other", "event.set_responsible_person",
        "event.notification.send",
        "event_template.view", "event_template.create", "event_template.edit", "event_template.delete",
        "equipment.view", "equipment_item.report_own",
        "event.equipment.plan", "event.equipment.assign",
        "debriefing.submit_own", "debriefing.view_own", "debriefing.view_all",
        "report.view",
    ],
    Role.MEMBER: [
        "user.view", "user.edit_own",
        "credential.view",
        "master_event.view",
        "event.view", "event.assign_own",
        "event_template.view",
        "equipment.view", "equipment_item.report_own",
        "debriefing.submit_own", "debriefing.view_own",
        "report.view",
    ],
    Role.VIEWER: [
        "user.view",
        "credential.view",
        "master_event.view",
        "event.view",
        "event_template.view",
        "equipment.view",
        "report.view",
    ],
}
