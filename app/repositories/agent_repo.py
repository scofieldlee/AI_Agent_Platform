"""
Agent repository: data access for agents.
"""

from typing import List, Optional, Dict, Any
import secrets
import string
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import (
    Agent, AgentVersion, AgentToolBinding, AgentKnowledgeBinding,
    AgentWorkflowBinding,
)
from app.models.tool import Tool
from app.models.knowledge import KnowledgeBase
from app.models.workflow import Workflow


def _generate_chat_token(length: int = 8) -> str:
    """Generate a random alphanumeric chat token."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def list_agents(db: AsyncSession) -> List[Dict[str, Any]]:
    """List all non-archived agents ordered by most recent.

    Each item carries its primary workflow summary (if any) so the admin
    table can show the bound workflow without an extra request per row.
    """
    result = await db.execute(
        select(Agent)
        .where(Agent.status != "archived")
        .order_by(Agent.id.desc())
    )
    agents = list(result.scalars().all())

    # Bulk-load primary workflow bindings for all agents (one query)
    agent_ids = [a.id for a in agents]
    primary_workflow: Dict[int, Dict[str, Any]] = {}
    if agent_ids:
        wf_result = await db.execute(
            select(AgentWorkflowBinding, Workflow)
            .join(Workflow, Workflow.id == AgentWorkflowBinding.workflow_id)
            .where(AgentWorkflowBinding.agent_id.in_(agent_ids))
            .where(AgentWorkflowBinding.is_primary.is_(True))
        )
        for awb, wf in wf_result.all():
            primary_workflow[awb.agent_id] = {
                "workflow_id": wf.id,
                "name": wf.name,
                "code": wf.code,
                "status": wf.status,
            }

    return [
        {
            "id": a.id,
            "name": a.name,
            "code": a.code,
            "description": a.description,
            "agent_type": a.agent_type,
            "status": a.status,
            "version": a.version,
            "config": a.config,
            "is_active": a.is_active,
            "chat_token": a.chat_token,
            "workflow": primary_workflow.get(a.id),
        }
        for a in agents
    ]


async def get_agent(db: AsyncSession, agent_id: int) -> Optional[Agent]:
    """Get an agent by ID."""
    return await db.get(Agent, agent_id)


async def get_agent_by_token(db: AsyncSession, token: str) -> Optional[Agent]:
    """Get an agent by its chat_token. Only returns published and active agents."""
    result = await db.execute(
        select(Agent)
        .where(Agent.chat_token == token)
        .where(Agent.is_active.is_(True))
        .where(Agent.status == "published")
    )
    return result.scalar_one_or_none()


async def create_agent(
    db: AsyncSession,
    name: str,
    code: str,
    description: Optional[str] = None,
    agent_type: str = "config",
    config: Optional[dict] = None,
) -> Agent:
    """Create a new agent with auto-generated chat_token."""
    agent = Agent(
        name=name,
        code=code,
        description=description,
        agent_type=agent_type,
        config=config or {},
        chat_token=_generate_chat_token(),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def update_agent(
    db: AsyncSession,
    agent: Agent,
    updates: Dict[str, Any],
) -> Agent:
    """Update an agent's fields. Only non-None values are applied."""
    for field in ("name", "description", "agent_type", "status", "config", "is_active"):
        if field in updates and updates[field] is not None:
            setattr(agent, field, updates[field])
    await db.flush()
    await db.refresh(agent)
    return agent


async def archive_agent(db: AsyncSession, agent: Agent) -> Agent:
    """Soft-delete: mark agent as archived and inactive."""
    agent.status = "archived"
    agent.is_active = False
    await db.flush()
    await db.refresh(agent)
    return agent


async def regenerate_chat_token(db: AsyncSession, agent: Agent) -> str:
    """Generate a new chat_token for an agent. Returns the new token."""
    agent.chat_token = _generate_chat_token()
    await db.flush()
    await db.refresh(agent)
    return agent.chat_token


async def get_agent_detail(db: AsyncSession, agent_id: int) -> Optional[Dict[str, Any]]:
    """Get agent with tool bindings, knowledge bindings, and version history."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        return None

    # Fetch tool bindings with tool details
    tool_result = await db.execute(
        select(Tool, AgentToolBinding)
        .join(AgentToolBinding, AgentToolBinding.tool_id == Tool.id)
        .where(AgentToolBinding.agent_id == agent_id)
    )
    tool_bindings = [
        {
            "tool_id": t.id,
            "tool_name": t.name,
            "tool_type": t.tool_type,
            "description": t.description,
            "permission": atb.permission,
        }
        for t, atb in tool_result.all()
    ]

    # Fetch knowledge bindings with KB details
    kb_result = await db.execute(
        select(KnowledgeBase, AgentKnowledgeBinding)
        .join(AgentKnowledgeBinding, AgentKnowledgeBinding.knowledge_base_id == KnowledgeBase.id)
        .where(AgentKnowledgeBinding.agent_id == agent_id)
    )
    knowledge_bindings = [
        {
            "knowledge_base_id": kb.id,
            "name": kb.name,
            "kb_type": kb.kb_type,
        }
        for kb, akbb in kb_result.all()
    ]

    # Fetch workflow bindings with workflow details
    wf_result = await db.execute(
        select(Workflow, AgentWorkflowBinding)
        .join(AgentWorkflowBinding, AgentWorkflowBinding.workflow_id == Workflow.id)
        .where(AgentWorkflowBinding.agent_id == agent_id)
        .order_by(AgentWorkflowBinding.is_primary.desc(), Workflow.id.asc())
    )
    workflow_bindings = [
        {
            "workflow_id": wf.id,
            "name": wf.name,
            "code": wf.code,
            "status": wf.status,
            "version": wf.version,
            "is_primary": awb.is_primary,
            "node_count": len((wf.graph_config or {}).get("nodes", [])),
        }
        for wf, awb in wf_result.all()
    ]

    # Fetch version history
    ver_result = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.id.desc())
        .limit(20)
    )
    versions = [
        {
            "id": v.id,
            "version": v.version,
            "changelog": v.changelog,
            "status": v.status,
            "created_at": v.created_at,
        }
        for v in ver_result.scalars().all()
    ]

    return {
        "id": agent.id,
        "name": agent.name,
        "code": agent.code,
        "description": agent.description,
        "agent_type": agent.agent_type,
        "status": agent.status,
        "version": agent.version,
        "config": agent.config,
        "is_active": agent.is_active,
        "chat_token": agent.chat_token,
        "tool_bindings": tool_bindings,
        "knowledge_bindings": knowledge_bindings,
        "workflow_bindings": workflow_bindings,
        "versions": versions,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


async def set_tool_bindings(
    db: AsyncSession,
    agent_id: int,
    tool_names: List[str],
) -> None:
    """Replace all tool bindings for an agent."""
    # Delete existing bindings
    await db.execute(
        delete(AgentToolBinding).where(AgentToolBinding.agent_id == agent_id)
    )

    # Find tool IDs by name
    if tool_names:
        result = await db.execute(
            select(Tool).where(Tool.name.in_(tool_names))
        )
        tools = result.scalars().all()
        for tool in tools:
            db.add(AgentToolBinding(
                agent_id=agent_id,
                tool_id=tool.id,
                permission="allow",
            ))

    await db.flush()


async def set_knowledge_bindings(
    db: AsyncSession,
    agent_id: int,
    knowledge_base_ids: List[int],
) -> None:
    """Replace all knowledge base bindings for an agent."""
    # Delete existing bindings
    await db.execute(
        delete(AgentKnowledgeBinding).where(AgentKnowledgeBinding.agent_id == agent_id)
    )

    # Create new bindings
    for kb_id in knowledge_base_ids:
        db.add(AgentKnowledgeBinding(
            agent_id=agent_id,
            knowledge_base_id=kb_id,
        ))

    await db.flush()


async def set_workflow_bindings(
    db: AsyncSession,
    agent_id: int,
    workflow_ids: List[int],
) -> None:
    """Replace all workflow bindings for an agent.

    The first element of ``workflow_ids`` is marked as the primary workflow
    (is_primary=True) that the runtime resolves first. Passing an empty list
    removes all bindings (the agent then falls back to the global default).
    """
    # Delete existing bindings
    await db.execute(
        delete(AgentWorkflowBinding).where(AgentWorkflowBinding.agent_id == agent_id)
    )

    # Create new bindings (first one is primary)
    for idx, wf_id in enumerate(workflow_ids):
        db.add(AgentWorkflowBinding(
            agent_id=agent_id,
            workflow_id=wf_id,
            is_primary=(idx == 0),
        ))

    await db.flush()


async def create_version(
    db: AsyncSession,
    agent_id: int,
    version: str,
    config: Optional[dict] = None,
    changelog: Optional[str] = None,
    created_by: Optional[int] = None,
) -> AgentVersion:
    """Create a version snapshot for an agent."""
    ver = AgentVersion(
        agent_id=agent_id,
        version=version,
        config=config or {},
        changelog=changelog,
        status="published",
        created_by=created_by,
    )
    db.add(ver)
    await db.flush()
    await db.refresh(ver)
    return ver
