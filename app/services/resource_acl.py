"""Resource ACL service: ownership + share based data-level access control.

Two layers combine:
  1. Functional RBAC (agent:view / agent:manage ...) — feature gate
  2. Data-level ACL (this module) — who can see/manage which resource

Permission levels (higher includes lower): manage ⊃ view ⊃ chat.
"""

from typing import Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_user_role_codes
from app.models.resource_share import ResourceShare
from app.models.user import User

ADMIN_ROLES = {"super_admin", "ai_admin"}
PERM_ORDER = {"chat": 0, "view": 1, "manage": 2}


async def is_admin_user(db: AsyncSession, user: User) -> bool:
    """Superuser or holding an admin role sees/manages everything."""
    if user.is_superuser:
        return True
    roles = await get_user_role_codes(db, user.id)
    return any(r in ADMIN_ROLES for r in roles)


async def _best_share_permission(
    db: AsyncSession, user: User, resource_type: str, resource_id: int
) -> Optional[str]:
    """Best permission from user-level and role-level shares combined."""
    role_ids: list = []
    from app.models.user import UserRole
    result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user.id)
    )
    role_ids = [r[0] for r in result.fetchall()]

    stmt = select(ResourceShare).where(
        ResourceShare.resource_type == resource_type,
        ResourceShare.resource_id == resource_id,
    )
    result = await db.execute(stmt)
    best: Optional[str] = None
    for share in result.scalars().all():
        if share.principal_type == "user" and share.principal_id == user.id:
            pass
        elif share.principal_type == "role" and share.principal_id in role_ids:
            pass
        else:
            continue
        if best is None or PERM_ORDER[share.permission] > PERM_ORDER[best]:
            best = share.permission
    return best


async def get_resource_permission(
    db: AsyncSession,
    user: User,
    resource_type: str,
    resource_id: int,
    owner_id: Optional[int],
) -> Optional[str]:
    """Resolve the user's permission over a resource.

    Returns 'manage' | 'view' | 'chat' | None (not visible).
    Legacy resources (owner_id None) are public/manage.
    """
    if owner_id is None:
        return "manage"  # legacy public resource
    if await is_admin_user(db, user):
        return "manage"
    if owner_id == user.id:
        return "manage"
    return await _best_share_permission(db, user, resource_type, resource_id)


async def visible_resource_ids(
    db: AsyncSession, user: User, resource_type: str, owner_by_id: dict
) -> Tuple[bool, Set[int]]:
    """Compute the set of visible resource ids for list filtering.

    Returns (all_visible, visible_ids). When all_visible is True the set is
    meaningless and the list is unfiltered.
    """
    if await is_admin_user(db, user):
        return True, set()

    visible: Set[int] = set()
    for rid, owner_id in owner_by_id.items():
        if owner_id is None or owner_id == user.id:
            visible.add(rid)

    # Shares: user-level + role-level (any level >= chat makes it visible)
    from app.models.user import UserRole
    result = await db.execute(
        select(UserRole.role_id).where(UserRole.user_id == user.id)
    )
    role_ids = {r[0] for r in result.fetchall()}

    result = await db.execute(
        select(ResourceShare).where(ResourceShare.resource_type == resource_type)
    )
    for share in result.scalars().all():
        if share.resource_id in visible:
            continue
        if share.principal_type == "user" and share.principal_id == user.id:
            visible.add(share.resource_id)
        elif share.principal_type == "role" and share.principal_id in role_ids:
            visible.add(share.resource_id)

    return False, visible
