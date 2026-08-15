"""Human task (ticket) endpoints for human-in-the-loop customer service."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends

from app.human_center.service import HumanCenterService
from app.auth.dependencies import require_permission
from app.schemas.human_task import AssignRequest, ResolveRequest

router = APIRouter()
service = HumanCenterService()


@router.get("", dependencies=[Depends(require_permission("ticket:view"))])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status: pending, assigned, resolved, closed"),
    priority: Optional[str] = Query(None, description="Filter by priority: low, normal, high, urgent"),
    assigned_to: Optional[int] = Query(None, description="Filter by assigned staff ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List human tasks with optional filters."""
    return await service.get_tasks(
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", dependencies=[Depends(require_permission("ticket:view"))])
async def task_stats():
    """Get aggregate statistics for human tasks."""
    return await service.get_stats()


@router.get("/{task_id}", dependencies=[Depends(require_permission("ticket:view"))])
async def get_task(task_id: int):
    """Get a single human task with full details."""
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/assign", dependencies=[Depends(require_permission("ticket:manage"))])
async def assign_task(task_id: int, request: AssignRequest):
    """Assign a task to a human agent."""
    task = await service.assign_task(task_id, request.assigned_to)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return service._task_to_dict(task)


@router.post("/{task_id}/resolve", dependencies=[Depends(require_permission("ticket:manage"))])
async def resolve_task(task_id: int, request: ResolveRequest):
    """Resolve a human task."""
    task = await service.resolve_task(
        task_id=task_id,
        resolution_note=request.resolution_note,
        resolution_type=request.resolution_type,
        assigned_to=request.assigned_to,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return service._task_to_dict(task)
