"""AI Employee management & execution endpoints."""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission, get_current_user
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeeDetailResponse,
    AgentBindingsUpdate, AgentBindingResponse,
    SelectableAgentResponse,
    ExecuteRequest, ExecuteResponse, TaskResumeRequest,
    TaskResponse, TaskListResponse, StepResponse,
)
from app.employee import service as employee_service
from app.repositories import employee_repo

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Running task registry (process-level) ---
_running_tasks: dict = {}
MAX_CONCURRENT_TASKS = 10


# ============================================================
# Employee CRUD (non-{id} routes first to avoid path conflicts)
# ============================================================

@router.get("", response_model=List[EmployeeResponse],
            dependencies=[Depends(require_permission("agent:view"))])
async def list_employees_endpoint(
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all AI employees."""
    return await employee_service.list_employees(db, status=status, keyword=keyword)


@router.post("", response_model=EmployeeResponse, status_code=201,
             dependencies=[Depends(require_permission("agent:manage"))])
async def create_employee_endpoint(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new AI employee."""
    try:
        employee = await employee_service.create_employee(
            db, name=data.name, code=data.code, description=data.description,
            role=data.role, goal=data.goal, role_prompt=data.role_prompt,
            orchestration_mode=data.orchestration_mode,
            supervisor_agent_id=data.supervisor_agent_id,
            config=data.config, created_by=current_user.id,
        )
        await db.commit()
        await db.refresh(employee)
        return {
            "id": employee.id,
            "name": employee.name,
            "code": employee.code,
            "description": employee.description,
            "role": employee.role,
            "goal": employee.goal,
            "orchestration_mode": employee.orchestration_mode,
            "supervisor_agent_id": employee.supervisor_agent_id,
            "status": employee.status,
            "config": employee.config,
            "agent_count": 0,
            "created_by": employee.created_by,
            "created_at": employee.created_at,
            "updated_at": employee.updated_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ============================================================
# Selectable agents & task list (before /{id} routes)
# ============================================================

@router.get("/agents/selectable", response_model=List[SelectableAgentResponse],
            dependencies=[Depends(require_permission("agent:view"))])
async def list_selectable_agents_endpoint(
    db: AsyncSession = Depends(get_db),
):
    """List published & active agents available for binding."""
    agents = await employee_service.list_selectable_agents(db)
    return [
        {"id": a.id, "name": a.name, "code": a.code,
         "description": a.description, "status": a.status}
        for a in agents
    ]


@router.get("/tasks", response_model=List[TaskListResponse],
            dependencies=[Depends(require_permission("agent:view"))])
async def list_tasks_endpoint(
    status: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    mine: bool = Query(False),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List tasks with optional filters."""
    user_id = current_user.id if mine else None
    return await employee_repo.list_tasks(
        db, status=status, employee_id=employee_id,
        user_id=user_id, mine=mine, limit=limit, offset=offset,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse,
             dependencies=[Depends(require_permission("agent:view"))])
async def get_task_endpoint(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get task detail with all steps (polling endpoint)."""
    detail = await employee_repo.get_task_detail(db, task_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail


@router.post("/tasks/{task_id}/cancel",
             dependencies=[Depends(require_permission("agent:view"))])
async def cancel_task_endpoint(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a running or waiting task."""
    task = await employee_repo.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Permission: owner or manage
    if task.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only the task owner can cancel")

    if task.status not in ("pending", "running", "waiting_human"):
        raise HTTPException(status_code=422, detail=f"Cannot cancel task in '{task.status}' state")

    # Cancel the asyncio task if running
    running = _running_tasks.get(task_id)
    if running and not running.done():
        running.cancel()

    await employee_repo.update_task(db, task, status="cancelled")
    await db.commit()

    # Cancel pending steps
    for step in task.steps:
        if step.status in ("pending", "running"):
            await employee_repo.update_step(db, step, status="cancelled")
    await db.commit()

    return {"task_id": task_id, "status": "cancelled"}


@router.post("/tasks/{task_id}/resume",
             dependencies=[Depends(require_permission("agent:view"))])
async def resume_task_endpoint(
    task_id: int,
    payload: Optional[TaskResumeRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume a waiting_human task.

    Optionally carries human_feedback (e.g. the resolved ticket's
    resolution note). The feedback is injected into the task context as a
    `human_resolution` artifact so the Supervisor sees the human decision
    and can act on it instead of escalating again.
    """
    task = await employee_repo.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only the task owner can resume")

    if task.status != "waiting_human":
        raise HTTPException(status_code=422, detail=f"Cannot resume task in '{task.status}' state")

    feedback = (payload.human_feedback or "").strip() if payload else ""
    if feedback:
        ctx_data = dict(task.context or {})
        artifacts = dict(ctx_data.get("artifacts", {}))
        decisions = list(ctx_data.get("decisions", []))

        # Inject the human decision as a visible artifact
        artifacts["human_resolution"] = {
            "success": True,
            "summary": f"[人工处理结果] {feedback[:2000]}",
            "data": {},
            "metadata": {"source": "human_feedback"},
        }
        # Audit trail entry (round numbering continues from existing decisions)
        decisions.append({
            "round": len(decisions) + 1,
            "action": "human_resolved",
            "reason": feedback[:500],
            "dispatched": 0,
        })
        ctx_data["artifacts"] = artifacts
        ctx_data["decisions"] = decisions

        await employee_repo.update_task(db, task, context=ctx_data)

    await employee_repo.update_task(db, task, status="running", error=None)
    await db.commit()

    _launch_runtime(task_id)

    return {"task_id": task_id, "status": "running"}


# ============================================================
# Employee {id} routes
# ============================================================

@router.get("/{employee_id}", response_model=EmployeeDetailResponse,
            dependencies=[Depends(require_permission("agent:view"))])
async def get_employee_endpoint(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get employee detail with bindings."""
    detail = await employee_service.get_employee_detail(db, employee_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Employee not found")
    return detail


@router.put("/{employee_id}", response_model=EmployeeDetailResponse,
            dependencies=[Depends(require_permission("agent:manage"))])
async def update_employee_endpoint(
    employee_id: int,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update employee basic info."""
    try:
        await employee_service.update_employee(db, employee_id, data.model_dump(exclude_unset=True))
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    detail = await employee_service.get_employee_detail(db, employee_id)
    return detail


@router.delete("/{employee_id}",
               dependencies=[Depends(require_permission("agent:manage"))])
async def delete_employee_endpoint(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an employee (refused if running tasks exist)."""
    try:
        await employee_service.delete_employee(db, employee_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"detail": "Employee deleted"}


@router.get("/{employee_id}/agents", response_model=List[AgentBindingResponse],
            dependencies=[Depends(require_permission("agent:view"))])
async def get_bindings_endpoint(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get agent bindings for an employee."""
    detail = await employee_service.get_employee_detail(db, employee_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Employee not found")
    return detail["bindings"]


@router.put("/{employee_id}/agents",
            dependencies=[Depends(require_permission("agent:manage"))])
async def set_bindings_endpoint(
    employee_id: int,
    data: AgentBindingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Full-replace agent bindings with validation."""
    binding_list = [
        {
            "agent_id": b.agent_id,
            "role": b.role,
            "priority": b.priority,
            "enabled": b.enabled,
            "depends_on": b.depends_on,
            "config": b.config,
        }
        for b in data.agents
    ]
    try:
        await employee_service.set_bindings(db, employee_id, binding_list)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    detail = await employee_service.get_employee_detail(db, employee_id)
    return detail["bindings"]


@router.post("/{employee_id}/publish", response_model=EmployeeDetailResponse,
             dependencies=[Depends(require_permission("agent:manage"))])
async def publish_employee_endpoint(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Publish an employee after validation."""
    try:
        await employee_service.publish_employee(db, employee_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    detail = await employee_service.get_employee_detail(db, employee_id)
    return detail


@router.post("/{employee_id}/disable", response_model=EmployeeDetailResponse,
             dependencies=[Depends(require_permission("agent:manage"))])
async def disable_employee_endpoint(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Disable a published employee."""
    try:
        await employee_service.disable_employee(db, employee_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    detail = await employee_service.get_employee_detail(db, employee_id)
    return detail


# ============================================================
# Execute (create + launch task)
# ============================================================

@router.post("/{employee_id}/execute", response_model=ExecuteResponse)
async def execute_employee_endpoint(
    employee_id: int,
    data: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a task and launch async execution."""
    # Concurrency guard
    if len(_running_tasks) >= MAX_CONCURRENT_TASKS:
        raise HTTPException(status_code=429, detail="Too many concurrent tasks")

    try:
        employee = await employee_service.get_published_employee(db, employee_id)
        snapshot = await employee_service.build_snapshot(db, employee)

        # Validate snapshot agents are still available
        from app.models.agent import Agent
        for agent_info in snapshot["agents"]:
            agent = await db.get(Agent, agent_info["agent_id"])
            if not agent or not agent.is_active:
                raise ValueError(
                    f"Agent '{agent_info['name']}' is no longer available"
                )

        title = data.title or (
            data.input.get("message", "")[:100]
            if data.input.get("message") else f"Task for {employee.name}"
        )

        task = await employee_repo.create_task(
            db,
            employee_id=employee.id,
            user_id=current_user.id,
            title=title,
            input_data=data.input,
            employee_snapshot=snapshot,
            context={"artifacts": {}, "decisions": []},
            tenant_id=None,
        )
        await db.commit()
        await db.refresh(task)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Launch async execution
    _launch_runtime(task.id)

    return {"task_id": task.id, "status": "pending"}


# ============================================================
# Runtime launcher (Phase 3 will replace this with EmployeeRuntime)
# ============================================================

def _launch_runtime(task_id: int) -> None:
    """Launch the EmployeeRuntime for a task.

    Phase 2: placeholder that will be replaced by EmployeeRuntime.run_task().
    """
    try:
        from app.employee.runtime.executor import EmployeeRuntime
        runtime = EmployeeRuntime()
        coro = runtime.run_task(task_id)
        task = asyncio.create_task(coro)
        _running_tasks[task_id] = task

        # Auto-cleanup on completion
        def _cleanup(t):
            _running_tasks.pop(task_id, None)
        task.add_done_callback(_cleanup)

    except ImportError:
        logger.warning(
            f"EmployeeRuntime not yet implemented (Phase 3). "
            f"Task {task_id} created but not executed."
        )
    except Exception as e:
        logger.error(f"Failed to launch runtime for task {task_id}: {e}")
