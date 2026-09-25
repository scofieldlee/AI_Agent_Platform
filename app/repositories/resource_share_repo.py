"""Repository for resource_shares (user/role level ACL grants)."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import now
from app.models.resource_share import ResourceShare


async def list_shares(
    db: AsyncSession, resource_type: str, resource_id: int
) -> List[ResourceShare]:
    result = await db.execute(
        select(ResourceShare)
        .where(ResourceShare.resource_type == resource_type,
               ResourceShare.resource_id == resource_id)
        .order_by(ResourceShare.id)
    )
    return list(result.scalars().all())


async def get_share(
    db: AsyncSession, resource_type: str, resource_id: int, share_id: int
) -> Optional[ResourceShare]:
    result = await db.execute(
        select(ResourceShare).where(
            ResourceShare.id == share_id,
            ResourceShare.resource_type == resource_type,
            ResourceShare.resource_id == resource_id,
        )
    )
    return result.scalar_one_or_none()


async def find_by_principal(
    db: AsyncSession, resource_type: str, resource_id: int,
    principal_type: str, principal_id: int,
) -> Optional[ResourceShare]:
    result = await db.execute(
        select(ResourceShare).where(
            ResourceShare.resource_type == resource_type,
            ResourceShare.resource_id == resource_id,
            ResourceShare.principal_type == principal_type,
            ResourceShare.principal_id == principal_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_share(
    db: AsyncSession, resource_type: str, resource_id: int,
    principal_type: str, principal_id: int, permission: str,
    granted_by: int,
) -> ResourceShare:
    share = await find_by_principal(
        db, resource_type, resource_id, principal_type, principal_id)
    if share:
        share.permission = permission
        share.granted_by = granted_by
    else:
        share = ResourceShare(
            resource_type=resource_type,
            resource_id=resource_id,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
            granted_by=granted_by,
            created_at=now(),
        )
        db.add(share)
    await db.flush()
    return share


async def delete_share(db: AsyncSession, share: ResourceShare) -> None:
    await db.delete(share)
    await db.flush()
