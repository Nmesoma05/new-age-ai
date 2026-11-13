"""Role-based permissions. The API checks these; row-level security enforces the tenant boundary underneath."""
from __future__ import annotations

ORG_PERMISSIONS: dict[str, frozenset[str]] = {
    "org.read": frozenset({"owner", "admin", "member", "billing"}),
    "org.update": frozenset({"owner", "admin"}),
    "org.members.manage": frozenset({"owner", "admin"}),
    "org.teams.manage": frozenset({"owner", "admin"}),
    "org.products.manage": frozenset({"owner", "admin"}),
    "org.workspaces.create": frozenset({"owner", "admin"}),
    "org.billing.read": frozenset({"owner", "admin", "billing"}),
    "org.usage.read": frozenset({"owner", "admin", "billing"}),
    "org.integrations.manage": frozenset({"owner", "admin"}),
    "org.audit.read": frozenset({"owner", "admin"}),
}

# Effective workspace roles (org owners/admins are implicit workspace admins).
# client_approver is deliberately absent: approvers only see items explicitly shared with them.
WORKSPACE_PERMISSIONS: dict[str, frozenset[str]] = {
    "ws.read": frozenset({"admin", "editor", "viewer"}),
    "ws.write": frozenset({"admin", "editor"}),
    "ws.ai.run": frozenset({"admin", "editor"}),
    "ws.manage": frozenset({"admin"}),
}


def org_can(role: str | None, permission: str) -> bool:
    return role is not None and role in ORG_PERMISSIONS[permission]


def ws_can(role: str | None, permission: str) -> bool:
    return role is not None and role in WORKSPACE_PERMISSIONS[permission]
