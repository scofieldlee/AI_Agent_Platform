"""Resource share endpoints: grant/revoke user & role level permissions over
owned resources (agents / AI employees).

Rules:
  - Only the resource owner or an admin can manage shares.
  - Role-level grants are restricted to superusers (影响面大，权限收敛).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.resource_share import ResourceShare
from app.models.user import User, Role
from app.repositories import resource_share_repo
from app.services.resource_acl import get_resource_permission

router = APIRouter()

VALID_PERMISSIONS = {"chat", "view", "manage"}


async def _require_owner_or_admin(
    db: AsyncSession, user: User, resource_type: str, resource_id: int
) -> None:
    """Owner or admin only (higher than manage-share: 授权权不外放)."""
    from app.models.agent import Agent
    from app.models.ai_employee import AIEmployee

    model = Agent if resource_type == "agent" else AIEmployee
    row = await db.get(model, resource_id)
    if not row:
        raise HTTPException(status_code=404, detail="资源不存在")
    perm = await get_resource_permission(db, user, resource_type, resource_id, row.created_by)
    if perm != "manage" or (row.created_by not in (None, user.id) and not user.is_superuser):
        # owner / admin only: a manage-share holder cannot re-share
        is_owner = row.created_by == user.id
        from app.services.resource_acl import is_admin_user
        if not (is_owner or await is_admin_user(db, user)):
            raise HTTPException(status_code=403, detail="仅资源所有者或管理员可管理授权")


async def _resolve_principal(
    db: AsyncSession, principal_type: str, identifier: str
) -> int:
    if principal_type == "user":
        result = await db.execute(select(User).where(User.username == identifier))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail=f"用户「{identifier}」不存在")
        return user.id
    else:
        result = await db.execute(select(Role).where(Role.code == identifier))
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=404, detail=f"角色「{identifier}」不存在")
        return role.id


class ShareCreateRequest(BaseModel):
    principal_type: str  # user | role
    identifier: str      # username 或 role code
    permission: str      # chat | view | manage


@router.get("/{resource_type}/{resource_id}/shares")
async def list_shares_endpoint(
    resource_type: str,
    resource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if resource_type not in ("agent", "employee"):
        raise HTTPException(status_code=400, detail="不支持的资源类型")
    await _require_owner_or_admin(db, current_user, resource_type, resource_id)

    shares = await resource_share_repo.list_shares(db, resource_type, resource_id)
    items = []
    for s in shares:
        principal_name = None
        if s.principal_type == "user":
            u = await db.get(User, s.principal_id)
            principal_name = u.username if u else f"user#{s.principal_id}"
        else:
            r = await db.get(Role, s.principal_id)
            principal_name = (r.name if r else f"role#{s.principal_id}")
        items.append({
            "id": s.id,
            "principal_type": s.principal_type,
            "principal_id": s.principal_id,
            "principal_name": principal_name,
            "permission": s.permission,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return {"items": items}


@router.post("/{resource_type}/{resource_id}/shares")
async def create_share_endpoint(
    resource_type: str,
    resource_id: int,
    payload: ShareCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if resource_type not in ("agent", "employee"):
        raise HTTPException(status_code=400, detail="不支持的资源类型")
    if payload.principal_type not in ("user", "role"):
        raise HTTPException(status_code=400, detail="principal_type 必须是 user 或 role")
    if payload.permission not in VALID_PERMISSIONS:
        raise HTTPException(status_code=400, detail="permission 必须是 chat/view/manage")

    # 角色级授权仅超级管理员（影响面大，权限收敛）
    if payload.principal_type == "role" and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="角色级授权仅超级管理员可操作")

    await _require_owner_or_admin(db, current_user, resource_type, resource_id)
    principal_id = await _resolve_principal(db, payload.principal_type, payload.identifier)

    share = await resource_share_repo.upsert_share(
        db, resource_type, resource_id,
        payload.principal_type, principal_id,
        payload.permission, current_user.id,
    )
    await db.commit()
    return {"id": share.id, "permission": share.permission, "principal_id": principal_id}


@router.delete("/{resource_type}/{resource_id}/shares/{share_id}")
async def delete_share_endpoint(
    resource_type: str,
    resource_id: int,
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_owner_or_admin(db, current_user, resource_type, resource_id)
    share = await resource_share_repo.get_share(db, resource_type, resource_id, share_id)
    if not share:
        raise HTTPException(status_code=404, detail="授权记录不存在")
    await resource_share_repo.delete_share(db, share)
    await db.commit()
    return {"deleted": True}
