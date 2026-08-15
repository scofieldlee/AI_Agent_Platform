"""
Workflow repository: data access for workflow definitions.
"""

from typing import List, Optional, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow
from app.models.agent import AgentWorkflowBinding


async def list_workflows(db: AsyncSession) -> List[Workflow]:
    """List all workflows ordered by most recent."""
    result = await db.execute(
        select(Workflow).order_by(Workflow.id.desc())
    )
    return list(result.scalars().all())


async def get_workflow(db: AsyncSession, workflow_id: int) -> Optional[Workflow]:
    """Get a workflow by ID."""
    return await db.get(Workflow, workflow_id)


async def get_default_workflow(db: AsyncSession) -> Optional[Workflow]:
    """Get the default workflow.

    Priority: published + active -> any active -> any workflow.
    Falls back to None when no workflow exists.
    """
    # 1. published + active
    result = await db.execute(
        select(Workflow)
        .where(Workflow.status == "published")
        .where(Workflow.is_active.is_(True))
        .order_by(Workflow.id.asc())
        .limit(1)
    )
    wf = result.scalar_one_or_none()
    if wf:
        return wf

    # 2. any active
    result = await db.execute(
        select(Workflow)
        .where(Workflow.is_active.is_(True))
        .order_by(Workflow.id.asc())
        .limit(1)
    )
    wf = result.scalar_one_or_none()
    if wf:
        return wf

    # 3. any workflow
    result = await db.execute(
        select(Workflow).order_by(Workflow.id.asc()).limit(1)
    )
    return result.scalar_one_or_none()


async def get_agent_bound_workflow(db: AsyncSession, agent_id: int) -> Optional[Workflow]:
    """Get the primary workflow bound to an agent.

    Priority: is_primary binding -> any binding. Returns None when the agent
    has no workflow binding (caller falls back to the global default).
    """
    # 1. primary binding
    result = await db.execute(
        select(Workflow)
        .join(AgentWorkflowBinding, AgentWorkflowBinding.workflow_id == Workflow.id)
        .where(AgentWorkflowBinding.agent_id == agent_id)
        .where(AgentWorkflowBinding.is_primary.is_(True))
        .order_by(Workflow.id.asc())
        .limit(1)
    )
    wf = result.scalar_one_or_none()
    if wf:
        return wf

    # 2. any binding (secondary fallback)
    result = await db.execute(
        select(Workflow)
        .join(AgentWorkflowBinding, AgentWorkflowBinding.workflow_id == Workflow.id)
        .where(AgentWorkflowBinding.agent_id == agent_id)
        .order_by(Workflow.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_workflow(
    db: AsyncSession,
    name: str,
    code: str,
    description: Optional[str] = None,
    workflow_type: str = "hybrid",
    graph_config: Optional[dict] = None,
) -> Workflow:
    """Create a new workflow."""
    wf = Workflow(
        name=name,
        code=code,
        description=description,
        workflow_type=workflow_type,
        graph_config=graph_config or {},
        status="draft",
    )
    db.add(wf)
    await db.flush()
    await db.refresh(wf)
    return wf


async def update_workflow(
    db: AsyncSession,
    workflow: Workflow,
    updates: Dict[str, Any],
) -> Workflow:
    """Update a workflow's fields. Only non-None values are applied."""
    for field in ("name", "description", "workflow_type", "graph_config", "is_active"):
        if field in updates and updates[field] is not None:
            setattr(workflow, field, updates[field])
    await db.flush()
    await db.refresh(workflow)
    return workflow


async def delete_workflow(db: AsyncSession, workflow: Workflow) -> None:
    """Delete a workflow."""
    await db.delete(workflow)
    await db.flush()


async def publish_workflow(db: AsyncSession, workflow: Workflow) -> Workflow:
    """Publish a workflow (draft -> published)."""
    workflow.status = "published"
    await db.flush()
    await db.refresh(workflow)
    return workflow


async def count_agent_bindings(db: AsyncSession, workflow_id: int) -> int:
    """Count agent bindings referencing this workflow."""
    result = await db.execute(
        select(func.count(AgentWorkflowBinding.id)).where(
            AgentWorkflowBinding.workflow_id == workflow_id
        )
    )
    return result.scalar_one() or 0


async def code_exists(db: AsyncSession, code: str, exclude_id: Optional[int] = None) -> bool:
    """Check whether a workflow code is already taken."""
    stmt = select(Workflow).where(Workflow.code == code)
    if exclude_id is not None:
        stmt = stmt.where(Workflow.id != exclude_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
