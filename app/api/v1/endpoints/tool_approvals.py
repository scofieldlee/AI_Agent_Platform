"""Tool approval endpoints: list pending approvals, approve/reject.

The approval gate pauses sensitive tool executions in the workflow until a
human reviews them here (or they expire).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission, get_current_user
from app.database.session import get_db
from app.models.user import User
from app.repositories import tool_approval_repo
from app.repositories.tool_approval_repo import expire_if_stale

router = APIRouter()


class ApprovalResponse(BaseModel):
    id: int
    tool_name: str
    status: str
    params: Optional[dict] = None
    agent_id: Optional[int] = None
    conversation_id: Optional[int] = None
    trace_id: Optional[str] = None
    requester: Optional[str] = None
    reviewer_id: Optional[int] = None
    comment: Optional[str] = None
    created_at: Optional[str] = None
    reviewed_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ApprovalReviewRequest(BaseModel):
    action: str  # approved | rejected
    comment: Optional[str] = None


@router.get("", dependencies=[Depends(require_permission("ticket:view"))])
async def list_approvals_endpoint(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List tool approval requests (filter by status, e.g. pending)."""
    # Lazily expire stale pending approvals for the queried status
    if status == "pending" or status is None:
        from sqlalchemy import select
        from app.models.tool import ToolApproval
        result = await db.execute(
            select(ToolApproval).where(ToolApproval.status == "pending")
        )
        for approval in result.scalars().all():
            await expire_if_stale(db, approval, timeout_minutes=30)
        await db.commit()

    approvals = await tool_approval_repo.list_approvals(db, status=status, limit=limit)
    return {
        "items": [
            {
                "id": a.id,
                "tool_name": a.tool_name,
                "status": a.status,
                "params": a.params,
                "agent_id": a.agent_id,
                "conversation_id": a.conversation_id,
                "trace_id": a.trace_id,
                "requester": a.requester,
                "reviewer_id": a.reviewer_id,
                "comment": a.comment,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
            }
            for a in approvals
        ]
    }


@router.post("/{approval_id}/review", dependencies=[Depends(require_permission("ticket:manage"))])
async def review_approval_endpoint(
    approval_id: int,
    payload: ApprovalReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.action not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="action 必须是 approved 或 rejected")

    approval = await tool_approval_repo.get_approval(db, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批单不存在")
    if approval.status != "pending":
        # Expired approvals are treated as final
        raise HTTPException(status_code=409, detail=f"该审批单已处理（{approval.status}）")

    approval = await tool_approval_repo.review_approval(
        db, approval, payload.action, current_user.id, payload.comment
    )
    await db.commit()
    return {"id": approval.id, "status": approval.status}
