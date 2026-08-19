"""
AI Employee repository: data access for employees, bindings, tasks and steps.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import select, delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_employee import (
    AIEmployee, AIEmployeeAgent, AIEmployeeTask, AIEmployeeTaskStep,
)
from app.models.agent import Agent


# ============================================================
# Employee CRUD
# ============================================================

async def list_employees(
    db: AsyncSession,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List employees with optional filters and agent count."""
    stmt = select(AIEmployee).order_by(AIEmployee.id.desc())

    if status:
        stmt = stmt.where(AIEmployee.status == status)
    if keyword:
        stmt = stmt.where(
            (AIEmployee.name.ilike(f"%{keyword}%"))
            | (AIEmployee.code.ilike(f"%{keyword}%"))
        )

    result = await db.execute(stmt)
    employees = list(result.scalars().all())

    # Bulk-load agent counts
    emp_ids = [e.id for e in employees]
    counts: Dict[int, int] = {}
    if emp_ids:
        count_stmt = (
            select(AIEmployeeAgent.employee_id, func.count().label("cnt"))
            .where(AIEmployeeAgent.employee_id.in_(emp_ids))
            .group_by(AIEmployeeAgent.employee_id)
        )
        count_result = await db.execute(count_stmt)
        for row in count_result.all():
            counts[row.employee_id] = row.cnt

    return [
        {
            "id": e.id,
            "name": e.name,
            "code": e.code,
            "description": e.description,
            "role": e.role,
            "goal": e.goal,
            "orchestration_mode": e.orchestration_mode,
            "supervisor_agent_id": e.supervisor_agent_id,
            "status": e.status,
            "config": e.config,
            "agent_count": counts.get(e.id, 0),
            "created_by": e.created_by,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }
        for e in employees
    ]


async def get_employee(db: AsyncSession, employee_id: int) -> Optional[AIEmployee]:
    """Get an employee by ID (with bindings eagerly loaded)."""
    return await db.get(AIEmployee, employee_id)


async def get_employee_by_code(db: AsyncSession, code: str) -> Optional[AIEmployee]:
    """Get an employee by unique code."""
    result = await db.execute(
        select(AIEmployee).where(AIEmployee.code == code)
    )
    return result.scalar_one_or_none()


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
    """Create a new AI Employee."""
    employee = AIEmployee(
        name=name,
        code=code,
        description=description,
        role=role,
        goal=goal,
        role_prompt=role_prompt,
        orchestration_mode=orchestration_mode,
        supervisor_agent_id=supervisor_agent_id,
        config=config or {},
        created_by=created_by,
    )
    db.add(employee)
    await db.flush()
    await db.refresh(employee)
    return employee


async def update_employee(
    db: AsyncSession,
    employee: AIEmployee,
    updates: Dict[str, Any],
) -> AIEmployee:
    """Update employee fields. Only non-None values are applied."""
    editable = (
        "name", "description", "role", "goal", "role_prompt",
        "orchestration_mode", "supervisor_agent_id", "config", "status",
    )
    for field in editable:
        if field in updates and updates[field] is not None:
            setattr(employee, field, updates[field])
    await db.flush()
    await db.refresh(employee)
    return employee


async def delete_employee(db: AsyncSession, employee: AIEmployee) -> None:
    """Delete an employee (cascade deletes bindings)."""
    await db.delete(employee)
    await db.flush()


async def get_employee_detail(
    db: AsyncSession, employee_id: int,
) -> Optional[Dict[str, Any]]:
    """Get employee with bindings and supervisor name."""
    employee = await db.get(AIEmployee, employee_id)
    if not employee:
        return None

    supervisor_name = None
    if employee.supervisor_agent_id:
        sup = await db.get(Agent, employee.supervisor_agent_id)
        if sup:
            supervisor_name = sup.name

    bindings_list = []
    for b in employee.bindings:
        agent = await db.get(Agent, b.agent_id)
        bindings_list.append({
            "id": b.id,
            "agent_id": b.agent_id,
            "role": b.role,
            "priority": b.priority,
            "enabled": b.enabled,
            "depends_on": b.depends_on or [],
            "config": b.config or {},
            "agent_name": agent.name if agent else None,
            "agent_code": agent.code if agent else None,
            "agent_status": agent.status if agent else None,
        })
    bindings_list.sort(key=lambda x: x["priority"])

    return {
        "id": employee.id,
        "name": employee.name,
        "code": employee.code,
        "description": employee.description,
        "role": employee.role,
        "goal": employee.goal,
        "role_prompt": employee.role_prompt,
        "orchestration_mode": employee.orchestration_mode,
        "supervisor_agent_id": employee.supervisor_agent_id,
        "supervisor_agent_name": supervisor_name,
        "status": employee.status,
        "config": employee.config,
        "agent_count": len(bindings_list),
        "bindings": bindings_list,
        "created_by": employee.created_by,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
    }


# ============================================================
# Agent Bindings
# ============================================================

async def set_bindings(
    db: AsyncSession,
    employee_id: int,
    bindings: List[Dict[str, Any]],
) -> None:
    """Full-replace all agent bindings for an employee."""
    await db.execute(
        delete(AIEmployeeAgent).where(AIEmployeeAgent.employee_id == employee_id)
    )
    for b in bindings:
        db.add(AIEmployeeAgent(
            employee_id=employee_id,
            agent_id=b["agent_id"],
            role=b.get("role"),
            priority=b.get("priority", 0),
            enabled=b.get("enabled", True),
            depends_on=b.get("depends_on", []),
            config=b.get("config", {}),
        ))
    await db.flush()


async def get_bindings(
    db: AsyncSession, employee_id: int,
) -> List[AIEmployeeAgent]:
    """Get all bindings for an employee, ordered by priority."""
    result = await db.execute(
        select(AIEmployeeAgent)
        .where(AIEmployeeAgent.employee_id == employee_id)
        .order_by(AIEmployeeAgent.priority)
    )
    return list(result.scalars().all())


# ============================================================
# Selectable Agents
# ============================================================

async def list_selectable_agents(db: AsyncSession) -> List[Agent]:
    """List published & active agents available for binding."""
    result = await db.execute(
        select(Agent)
        .where(Agent.status == "published")
        .where(Agent.is_active.is_(True))
        .order_by(Agent.name)
    )
    return list(result.scalars().all())


# ============================================================
# Task CRUD
# ============================================================

async def create_task(
    db: AsyncSession,
    employee_id: int,
    user_id: Optional[int],
    title: str,
    input_data: dict,
    employee_snapshot: dict,
    context: dict,
    tenant_id: Optional[int] = None,
) -> AIEmployeeTask:
    """Create a new task instance."""
    task = AIEmployeeTask(
        tenant_id=tenant_id,
        employee_id=employee_id,
        user_id=user_id,
        title=title,
        input=input_data,
        context=context,
        employee_snapshot=employee_snapshot,
        status="pending",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: int) -> Optional[AIEmployeeTask]:
    """Get a task by ID (with steps eagerly loaded)."""
    return await db.get(AIEmployeeTask, task_id)


async def get_task_detail(
    db: AsyncSession, task_id: int,
) -> Optional[Dict[str, Any]]:
    """Get task with steps and employee name."""
    task = await db.get(AIEmployeeTask, task_id)
    if not task:
        return None

    employee = await db.get(AIEmployee, task.employee_id)
    employee_name = employee.name if employee else None

    # Build steps with agent names
    steps_list = []
    for s in sorted(task.steps, key=lambda x: x.id):
        agent = await db.get(Agent, s.agent_id)
        steps_list.append({
            "id": s.id,
            "agent_id": s.agent_id,
            "step_key": s.step_key,
            "role": s.role,
            "status": s.status,
            "input": s.input,
            "output": s.output,
            "depends_on": s.depends_on or [],
            "retry_count": s.retry_count,
            "trace_id": s.trace_id,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
            "error": s.error,
            "agent_name": agent.name if agent else None,
        })

    return {
        "id": task.id,
        "employee_id": task.employee_id,
        "user_id": task.user_id,
        "title": task.title,
        "input": task.input or {},
        "context": task.context or {},
        "status": task.status,
        "current_step_id": task.current_step_id,
        "result": task.result,
        "error": task.error,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "steps": steps_list,
        "employee_name": employee_name,
    }


async def list_tasks(
    db: AsyncSession,
    status: Optional[str] = None,
    employee_id: Optional[int] = None,
    user_id: Optional[int] = None,
    mine: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List tasks with optional filters."""
    stmt = select(AIEmployeeTask).order_by(AIEmployeeTask.id.desc())

    if status:
        stmt = stmt.where(AIEmployeeTask.status == status)
    if employee_id:
        stmt = stmt.where(AIEmployeeTask.employee_id == employee_id)
    if mine and user_id:
        stmt = stmt.where(AIEmployeeTask.user_id == user_id)

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    # Bulk load employee names
    emp_ids = list({t.employee_id for t in tasks})
    emp_map: Dict[int, str] = {}
    if emp_ids:
        emp_result = await db.execute(
            select(AIEmployee.id, AIEmployee.name).where(AIEmployee.id.in_(emp_ids))
        )
        for row in emp_result.all():
            emp_map[row.id] = row.name

    # Bulk load step counts
    task_ids = [t.id for t in tasks]
    step_counts: Dict[int, Dict[str, int]] = {}
    if task_ids:
        sc_result = await db.execute(
            select(
                AIEmployeeTaskStep.task_id,
                func.count().label("total"),
                func.count().filter(AIEmployeeTaskStep.status == "completed").label("done"),
            )
            .where(AIEmployeeTaskStep.task_id.in_(task_ids))
            .group_by(AIEmployeeTaskStep.task_id)
        )
        for row in sc_result.all():
            step_counts[row.task_id] = {"total": row.total, "done": row.done}

    items = []
    for t in tasks:
        sc = step_counts.get(t.id, {"total": 0, "done": 0})
        items.append({
            "id": t.id,
            "employee_id": t.employee_id,
            "user_id": t.user_id,
            "title": t.title,
            "status": t.status,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "created_at": t.created_at,
            "employee_name": emp_map.get(t.employee_id),
            "step_count": sc["total"],
            "completed_steps": sc["done"],
        })
    return items


async def update_task(
    db: AsyncSession,
    task: AIEmployeeTask,
    **kwargs: Any,
) -> AIEmployeeTask:
    """Update task fields (status, result, error, context, started_at, etc.)."""
    for key, value in kwargs.items():
        if value is not None or key in ("result", "error", "current_step_id"):
            setattr(task, key, value)
    await db.flush()
    await db.refresh(task)
    return task


# ============================================================
# Task Step CRUD
# ============================================================

async def create_step(
    db: AsyncSession,
    task_id: int,
    agent_id: int,
    step_key: str,
    role: Optional[str] = None,
    input_data: Optional[dict] = None,
    depends_on: Optional[list] = None,
    tenant_id: Optional[int] = None,
) -> AIEmployeeTaskStep:
    """Create a new task step."""
    step = AIEmployeeTaskStep(
        tenant_id=tenant_id,
        task_id=task_id,
        agent_id=agent_id,
        step_key=step_key,
        role=role,
        status="pending",
        input=input_data,
        depends_on=depends_on or [],
    )
    db.add(step)
    await db.flush()
    await db.refresh(step)
    return step


async def get_step(db: AsyncSession, step_id: int) -> Optional[AIEmployeeTaskStep]:
    """Get a step by ID."""
    return await db.get(AIEmployeeTaskStep, step_id)


async def update_step(
    db: AsyncSession,
    step: AIEmployeeTaskStep,
    **kwargs: Any,
) -> AIEmployeeTaskStep:
    """Update step fields."""
    for key, value in kwargs.items():
        if value is not None or key in ("output", "error", "trace_id", "current_step_id"):
            setattr(step, key, value)
    await db.flush()
    await db.refresh(step)
    return step


# ============================================================
# Lifecycle
# ============================================================

async def fail_orphan_tasks(db: AsyncSession) -> int:
    """Mark running tasks as failed (called on startup).

    Returns the count of affected tasks.
    """
    result = await db.execute(
        select(AIEmployeeTask).where(AIEmployeeTask.status == "running")
    )
    orphans = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for task in orphans:
        task.status = "failed"
        task.error = {"code": "service_restarted", "message": "Service restarted while task was running"}
        task.completed_at = now
    if orphans:
        await db.flush()
    await db.commit()
    return len(orphans)
