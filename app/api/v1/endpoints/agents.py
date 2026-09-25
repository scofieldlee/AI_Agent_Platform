"""Agent management endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission, get_current_user
from app.models.user import User
from app.core.audit import audit
from app.schemas.agent import (
    AgentCreate, AgentUpdate, AgentResponse, AgentDetailResponse,
    ToolBindingRequest, KnowledgeBindingRequest, WorkflowBindingRequest,
)
from app.repositories.agent_repo import (
    list_agents, get_agent, create_agent, update_agent, archive_agent,
    get_agent_detail, set_tool_bindings, set_knowledge_bindings,
    set_workflow_bindings, create_version, regenerate_chat_token,
)

router = APIRouter()


async def _check_agent_visibility(
    db: AsyncSession, user: User, agent_id: int, need: str = "view"
):
    """Data-level ACL check. 404 hides existence; 403 for insufficient level."""
    from app.services.resource_acl import get_resource_permission
    agent = await get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    perm = await get_resource_permission(db, user, "agent", agent_id, agent.created_by)
    order = {"chat": 0, "view": 1, "manage": 2}
    if perm is None or order.get(perm, -1) < order[need]:
        if perm is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        raise HTTPException(status_code=403, detail="无该 Agent 的管理权限，请联系创建者授权")
    return agent


@router.get("", response_model=List[AgentResponse], dependencies=[Depends(require_permission("agent:view"))])
async def list_agents_endpoint(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List agents visible to the current user (data-level ACL)."""
    from app.services.resource_acl import visible_resource_ids
    agents = await list_agents(db)
    all_visible, visible_ids = await visible_resource_ids(
        db, current_user, "agent", {a["id"]: a.get("created_by") for a in agents}
    )
    if all_visible:
        return agents
    filtered = [a for a in agents if a["id"] in visible_ids]
    # annotate creator name for management view
    return filtered


@router.post("", response_model=AgentResponse, status_code=201, dependencies=[Depends(require_permission("agent:manage"))])
@audit(action="create", resource_type="agent", resource_name=lambda ctx: getattr(ctx.get("data"), "name", None))
async def create_agent_endpoint(data: AgentCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a new agent (creator becomes owner)."""
    agent = await create_agent(
        db,
        name=data.name,
        code=data.code,
        description=data.description,
        agent_type=data.agent_type,
        config=data.config,
    )
    agent.created_by = current_user.id
    await db.commit()
    return agent


@router.get("/{agent_id}", response_model=AgentResponse, dependencies=[Depends(require_permission("agent:view"))])
async def get_agent_endpoint(agent_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get agent by ID (visibility-checked)."""
    agent = await _check_agent_visibility(db, current_user, agent_id, need="view")
    return agent


@router.get("/{agent_id}/detail", response_model=AgentDetailResponse, dependencies=[Depends(require_permission("agent:view"))])
async def get_agent_detail_endpoint(agent_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get agent detail with tool bindings, knowledge bindings, and version history."""
    await _check_agent_visibility(db, current_user, agent_id, need="view")
    detail = await get_agent_detail(db, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Agent not found")
    return detail


@router.patch("/{agent_id}", response_model=AgentResponse, dependencies=[Depends(require_permission("agent:manage"))])
@audit(
    action="update",
    resource_type="agent",
    get_resource=lambda db, agent_id: get_agent(db, agent_id),
    resource_name_attr="name",
    capture_changes=True,
    diff_before=lambda source: {
        "name": source.name,
        "description": source.description,
        "status": source.status,
        "is_active": source.is_active,
        "config": source.config,
    },
    diff_after=lambda result: {
        "name": getattr(result, "name", None),
        "description": getattr(result, "description", None),
        "status": getattr(result, "status", None),
        "is_active": getattr(result, "is_active", None),
        "config": getattr(result, "config", None),
    },
)
async def update_agent_endpoint(
    agent_id: int,
    data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent's configuration.

    Updates name, description, status, config, or is_active.
    Automatically creates a version snapshot when config changes.
    """
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    updates = data.model_dump(exclude_unset=True)

    # If config is being updated, create a version snapshot of the current config
    if "config" in updates and updates["config"] is not None:
        await create_version(
            db,
            agent_id=agent_id,
            version=agent.version,
            config=agent.config,
            changelog="Auto-snapshot before config update",
        )

    agent = await update_agent(db, agent, updates)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", dependencies=[Depends(require_permission("agent:manage"))])
@audit(
    action="delete",
    resource_type="agent",
    get_resource=lambda db, agent_id: get_agent(db, agent_id),
    resource_name_attr="name",
)
async def delete_agent_endpoint(agent_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Archive (soft-delete) an agent.

    Published agents cannot be deleted to prevent breaking live conversations.
    """
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    if agent.status == "published":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a published agent. Please unpublish or suspend it first.",
        )

    await archive_agent(db, agent)
    await db.commit()
    return {"status": "archived", "agent_id": agent_id}


@router.put("/{agent_id}/tools", dependencies=[Depends(require_permission("agent:manage"))])
async def set_tool_bindings_endpoint(
    agent_id: int,
    data: ToolBindingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set (replace) tool bindings for an agent."""
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    await set_tool_bindings(db, agent_id, data.tool_names)
    await db.commit()
    return {"status": "ok", "agent_id": agent_id, "tool_names": data.tool_names}


@router.put("/{agent_id}/knowledge", dependencies=[Depends(require_permission("agent:manage"))])
async def set_knowledge_bindings_endpoint(
    agent_id: int,
    data: KnowledgeBindingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set (replace) knowledge base bindings for an agent."""
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    await set_knowledge_bindings(db, agent_id, data.knowledge_base_ids)
    await db.commit()
    return {"status": "ok", "agent_id": agent_id, "knowledge_base_ids": data.knowledge_base_ids}


@router.put("/{agent_id}/workflow", dependencies=[Depends(require_permission("agent:manage"))])
async def set_workflow_bindings_endpoint(
    agent_id: int,
    data: WorkflowBindingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set (replace) workflow bindings for an agent.

    The first workflow_id becomes the primary workflow used by the runtime.
    Empty list unbinds all workflows (agent falls back to the global default).
    """
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    # Validate that all workflow IDs exist
    if data.workflow_ids:
        from app.repositories.workflow_repo import list_workflows
        existing = {wf.id for wf in await list_workflows(db)}
        missing = [wid for wid in data.workflow_ids if wid not in existing]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"工作流不存在: {missing}",
            )

    await set_workflow_bindings(db, agent_id, data.workflow_ids)
    # Workflow changes affect the runtime graph — drop the executor cache
    try:
        from app.runtime.executor import invalidate_workflow_cache
        invalidate_workflow_cache()
    except Exception:
        pass
    await db.commit()
    return {"status": "ok", "agent_id": agent_id, "workflow_ids": data.workflow_ids}


@router.post("/{agent_id}/regenerate-token", response_model=AgentResponse, dependencies=[Depends(require_permission("agent:manage"))])
async def regenerate_token_endpoint(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Regenerate the chat_token for an agent.

    The old URL will stop working immediately.
    """
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    new_token = await regenerate_chat_token(db, agent)
    await db.commit()
    await db.refresh(agent)
    return agent
