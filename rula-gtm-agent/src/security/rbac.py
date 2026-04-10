from __future__ import annotations

"""Role-to-permission mapping for pipeline actions.

This module is **not** a complete authentication system. In non-production
environments the Streamlit app may let a user *select* a role for demos; that
selection must not be treated as a verified identity claim.

When ``ENVIRONMENT=production``, :func:`resolve_role` returns ``viewer`` so the
UI cannot self-escalate—but real deployments should inject roles from an IdP
or server-side session, not from client-side widgets.
"""

from dataclasses import dataclass

VALID_ROLES = ("admin", "user", "analyst", "viewer")


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: str


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "prospecting:run",
        "map:run",
        "lineage:view",
        "retention:run",
        "incident:view",
    },
    "user": {"prospecting:run", "map:run", "lineage:view"},
    "analyst": {"prospecting:run", "map:run", "lineage:view"},
    "viewer": {"lineage:view"},
    "system": {
        "prospecting:run",
        "map:run",
        "lineage:view",
        "retention:run",
        "incident:view",
    },
}


def resolve_role(requested: str, *, environment: str = "local") -> str:
    """Return a safe effective role.

    In production, the role must come from an identity provider; self-service
    selection is only allowed in local/dev environments.
    """
    if environment == "production":
        return "viewer"
    if requested not in VALID_ROLES:
        return "user"
    return requested


def require_permission(role: str, permission: str) -> None:
    allowed = ROLE_PERMISSIONS.get(role, set())
    if permission not in allowed:
        raise PermissionError(f"Role '{role}' lacks permission '{permission}'.")
