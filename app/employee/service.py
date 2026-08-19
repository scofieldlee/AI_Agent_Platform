"""
AI Employee service: CRUD, agent binding validation, publish checks,
and snapshot building for task execution.
"""

import logging
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_employee import AIEmployee, AIEmployeeAgent
from app.models.agent import Agent
from app.repositories import employee_repo

logger = logging.getLogger(__name__)


# ============================================================
# CRUD
# ============================================================

async def list_employees(
    db: AsyncSession,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return await employee_repo.list_employees(db, status=status, keyword=keyword)


async def get_employee_detail(
    db: AsyncSession, employee_id: int,
) -> Optional[Dict[str, Any]]:
    return await employee_repo.get_employee_detail(db, employee_id)


async def create_employee(
    db: AsyncSession,
    name: str,
    code: str,
    description: Optional[str] = None,
    role: Optional[str] = None,
    goal: Optional[str] = None,
    role_prompt: Optional[str] = None,
    orchestration_mode: str = "dag",
    supervisor_agent_id: Optional[int] = None,
    config: Optional[dict] = None,
    created_by: Optional[int] = None,
) -> AIEmployee:
    # Check code uniqueness
    existing = await employee_repo.get_employee_by_code(db, code)
    if existing:
        raise ValueError(f"Employee code '{code}' already exists")

    return await employee_repo.create_employee(
        db, name=name, code=code, description=description,
        role=role, goal=goal, role_prompt=role_prompt,
        orchestration_mode=orchestration_mode,
        supervisor_agent_id=supervisor_agent_id,
        config=config, created_by=created_by,
    )


async def update_employee(
    db: AsyncSession,
    employee_id: int,
    updates: Dict[str, Any],
) -> AIEmployee:
    employee = await employee_repo.get_employee(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")

    # Prevent editing published employees (must disable first)
    if employee.status == "published" and "status" not in updates:
        raise ValueError("Cannot edit a published employee. Disable it first.")

    return await employee_repo.update_employee(db, employee, updates)


async def delete_employee(db: AsyncSession, employee_id: int) -> None:
    employee = await employee_repo.get_employee(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")

    # Check for active tasks
    tasks = await employee_repo.list_tasks(db, employee_id=employee_id, status="running")
    if tasks:
        raise ValueError("Cannot delete employee with running tasks")

    await employee_repo.delete_employee(db, employee)


# ============================================================
# Agent Bindings
# ============================================================

async def set_bindings(
    db: AsyncSession,
    employee_id: int,
    bindings: List[Dict[str, Any]],
) -> None:
    """Full-replace agent bindings with full validation."""
    employee = await employee_repo.get_employee(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")

    if employee.status == "published":
        raise ValueError("Cannot modify bindings of a published employee. Disable first.")

    # Validate
    await _validate_bindings(db, bindings, employee)

    await employee_repo.set_bindings(db, employee_id, bindings)


async def _validate_bindings(
    db: AsyncSession,
    bindings: List[Dict[str, Any]],
    employee: AIEmployee,
) -> None:
    """Validate binding set before saving.

    Rules:
      1. All agent_id exist and are published + active
      2. depends_on references must be within the binding set
      3. No duplicate agent_id
      4. Dependency graph must be acyclic
      5. Supervisor agent must not be in the team (anti-self-loop)
    """
    if not bindings:
        return  # Empty bindings are allowed (draft state)

    agent_ids = [b["agent_id"] for b in bindings]

    # Rule 1: All agents exist and are published + active
    agents_map: Dict[int, Agent] = {}
    for aid in agent_ids:
        agent = await db.get(Agent, aid)
        if not agent:
            raise ValueError(f"Agent {aid} does not exist")
        if agent.status != "published":
            raise ValueError(f"Agent '{agent.name}' (id={aid}) is not published")
        if not agent.is_active:
            raise ValueError(f"Agent '{agent.name}' (id={aid}) is not active")
        agents_map[aid] = agent

    # Rule 2: depends_on references must be within the binding set
    for b in bindings:
        for dep_id in (b.get("depends_on") or []):
            if dep_id not in agent_ids:
                raise ValueError(
                    f"Agent {b['agent_id']} depends on agent {dep_id} "
                    f"which is not in the binding set"
                )

    # Rule 3: No duplicate agent_id
    if len(agent_ids) != len(set(agent_ids)):
        raise ValueError("Duplicate agent_id in bindings")

    # Rule 4: No cycle in dependency graph
    _check_no_cycle(bindings)

    # Rule 5: Supervisor agent must not be in the team
    if employee.supervisor_agent_id and employee.supervisor_agent_id in agent_ids:
        raise ValueError(
            f"Supervisor agent (id={employee.supervisor_agent_id}) "
            f"cannot also be a team member"
        )


def _check_no_cycle(bindings: List[Dict[str, Any]]) -> None:
    """Detect cycles in the agent dependency graph using DFS."""
    # Build adjacency: agent_id -> set of agent_ids it depends on
    graph: Dict[int, List[int]] = {}
    for b in bindings:
        aid = b["agent_id"]
        deps = b.get("depends_on") or []
        graph[aid] = [d for d in deps if d in graph or d in [x["agent_id"] for x in bindings]]

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[int, int] = {node: WHITE for node in graph}

    def dfs(node: int) -> bool:
        """Returns True if cycle found."""
        color[node] = GRAY
        for neighbor in graph.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                return True  # Back edge = cycle
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    for node in graph:
        if color.get(node) == WHITE:
            if dfs(node):
                raise ValueError("Dependency cycle detected in agent bindings")


# ============================================================
# Publish / Disable
# ============================================================

async def publish_employee(db: AsyncSession, employee_id: int) -> AIEmployee:
    """Publish an employee after full validation."""
    employee = await employee_repo.get_employee(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")

    if employee.status == "published":
        return employee  # Already published, idempotent

    # Get bindings
    bindings = await employee_repo.get_bindings(db, employee_id)
    enabled_bindings = [b for b in bindings if b.enabled]

    # Check 5: At least one enabled binding
    if not enabled_bindings:
        raise ValueError("Cannot publish: at least one enabled agent binding is required")

    # Re-validate all bindings
    binding_dicts = [
        {
            "agent_id": b.agent_id,
            "role": b.role,
            "priority": b.priority,
            "enabled": b.enabled,
            "depends_on": b.depends_on or [],
            "config": b.config or {},
        }
        for b in bindings
    ]
    await _validate_bindings(db, binding_dicts, employee)

    # Check 6: Supervisor mode requires supervisor_agent_id
    if employee.orchestration_mode == "supervisor":
        if not employee.supervisor_agent_id:
            raise ValueError(
                "Supervisor mode requires a supervisor_agent_id"
            )
        sup_agent = await db.get(Agent, employee.supervisor_agent_id)
        if not sup_agent or sup_agent.status != "published":
            raise ValueError(
                f"Supervisor agent (id={employee.supervisor_agent_id}) "
                f"does not exist or is not published"
            )

    employee.status = "published"
    await db.flush()
    await db.refresh(employee)
    logger.info(f"Employee '{employee.name}' (id={employee_id}) published")
    return employee


async def disable_employee(db: AsyncSession, employee_id: int) -> AIEmployee:
    """Disable a published employee."""
    employee = await employee_repo.get_employee(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")

    employee.status = "disabled"
    await db.flush()
    await db.refresh(employee)
    return employee


# ============================================================
# Snapshot Building
# ============================================================

async def build_snapshot(
    db: AsyncSession,
    employee: AIEmployee,
) -> Dict[str, Any]:
    """Build a complete configuration snapshot for task execution.

    This snapshot is stored in ai_employee_tasks.employee_snapshot and
    ensures that modifications to the employee config mid-task do not
    affect the running task.
    """
    bindings = await employee_repo.get_bindings(db, employee.id)
    enabled_bindings = [b for b in bindings if b.enabled]

    agents_info: List[Dict[str, Any]] = []
    for b in enabled_bindings:
        agent = await db.get(Agent, b.agent_id)
        agents_info.append({
            "agent_id": b.agent_id,
            "name": agent.name if agent else f"agent_{b.agent_id}",
            "code": agent.code if agent else None,
            "role": b.role,
            "description": agent.description if agent else None,
            "depends_on": b.depends_on or [],
            "config": b.config or {},
            "priority": b.priority,
        })

    # Sort by priority for consistent ordering
    agents_info.sort(key=lambda x: x["priority"])

    supervisor_name = None
    if employee.supervisor_agent_id:
        sup_agent = await db.get(Agent, employee.supervisor_agent_id)
        supervisor_name = sup_agent.name if sup_agent else None

    return {
        "mode": employee.orchestration_mode,
        "employee_name": employee.name,
        "role_prompt": employee.role_prompt or "",
        "goal": employee.goal or "",
        "supervisor_agent_id": employee.supervisor_agent_id,
        "supervisor_agent_name": supervisor_name,
        "config": employee.config or {},
        "agents": agents_info,
    }


async def get_published_employee(
    db: AsyncSession, employee_id: int,
) -> AIEmployee:
    """Get a published employee or raise."""
    employee = await employee_repo.get_employee(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")
    if employee.status != "published":
        raise ValueError(f"Employee is not published (current: {employee.status})")
    return employee


# ============================================================
# Selectable Agents
# ============================================================

async def list_selectable_agents(db: AsyncSession) -> List[Agent]:
    return await employee_repo.list_selectable_agents(db)
