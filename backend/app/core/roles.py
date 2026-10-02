"""Organization-level RBAC roles (single source of truth).

A user has exactly one org role. ``owner`` is the org creator (from signup);
``admin`` and ``member`` are assigned by an owner/admin. ``owner`` and ``admin``
are the "org admin" set used by privileged operations.
"""

from __future__ import annotations

from typing import Literal, get_args

Role = Literal["owner", "admin", "member"]

ROLES: tuple[Role, ...] = get_args(Role)

#: Roles that count as organization administrators.
ADMIN_ROLES: frozenset[Role] = frozenset({"owner", "admin"})

DEFAULT_ROLE: Role = "member"
OWNER_ROLE: Role = "owner"
