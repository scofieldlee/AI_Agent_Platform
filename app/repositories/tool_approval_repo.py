"""Repository for tool approval requests (approval gate)."""

from datetime import timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import now
from app.models.tool import ToolApproval


async def create_approval(
    db: AsyncSession,
    tool_name: str,
    params: dict,
    agent_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    trace_id: Optional[str] = None,
    requester: Optional[str] = None,
) -> ToolApproval:
    approval = ToolApproval(
        tool_name=tool_name,
        params=params,
        agent_id=agent_id,
        conversation_id=conversation_id,
        trace_id=trace_id,
        requester=requester,
        status="pending",
    )
    db.add(approval)
    await db.flush()
    return approval


async def get_approval(db: AsyncSession, approval_id: int) -> Optional[ToolApproval]:
    return await db.get(ToolApproval, approval_id)


async def list_approvals(
    db: AsyncSession,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[ToolApproval]:
    stmt = select(ToolApproval).order_by(ToolApproval.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(ToolApproval.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def review_approval(
    db: AsyncSession,
    approval: ToolApproval,
    action: str,
    reviewer_id: int,
    comment: Optional[str] = None,
) -> ToolApproval:
    """Set approval to approved/rejected. Only pending can be reviewed."""
    approval.status = action  # "approved" | "rejected"
    approval.reviewer_id = reviewer_id
    approval.comment = comment
    approval.reviewed_at = now()
    await db.flush()
    return approval


async def expire_if_stale(
    db: AsyncSession,
    approval: ToolApproval,
    timeout_minutes: int,
) -> ToolApproval:
    """Mark a pending approval as expired when older than the timeout."""
    if approval.status == "pending" and approval.created_at:
        if approval.created_at <= now() - timedelta(minutes=timeout_minutes):
            approval.status = "expired"
            approval.comment = f"审批超时（{timeout_minutes} 分钟）自动拒绝"
            approval.reviewed_at = now()
            await db.flush()
    return approval
