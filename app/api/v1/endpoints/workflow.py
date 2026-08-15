"""Workflow endpoints: CRUD, publish, definition, traces and execution paths."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.repositories.analytics_repo import get_trace, get_spans, list_traces
from app.repositories import workflow_repo
from app.schemas import workflow as wf_schemas

router = APIRouter()

# --- Trace / execution path models ---


class ExecutionStep(BaseModel):
    node_name: str
    node_category: str
    status: str  # success, error, skipped
    duration_ms: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class ExecutionPath(BaseModel):
    trace_id: str
    status: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: Optional[int] = None
    steps: List[ExecutionStep]


class TraceOption(BaseModel):
    trace_id: str
    status: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: Optional[int] = None
    started_at: Optional[str] = None


# --- Converters ---


def _to_definition(wf) -> wf_schemas.WorkflowDefinition:
    """Convert a Workflow ORM row to the canvas definition view."""
    gc = wf.graph_config or {}
    nodes = gc.get("nodes", [])
    edges = gc.get("edges", [])
    return wf_schemas.WorkflowDefinition(
        id=wf.id,
        code=wf.code,
        name=wf.name,
        description=wf.description or "",
        entry_point=gc.get("entry_point", "intent"),
        nodes=[wf_schemas.WorkflowDefNode(**n) for n in nodes],
        edges=[wf_schemas.WorkflowDefEdge(**e) for e in edges],
    )


def _to_summary(wf) -> wf_schemas.WorkflowSummary:
    """Convert a Workflow ORM row to a list summary."""
    gc = wf.graph_config or {}
    return wf_schemas.WorkflowSummary(
        id=wf.id,
        name=wf.name,
        code=wf.code,
        description=wf.description,
        workflow_type=wf.workflow_type,
        status=wf.status,
        version=wf.version,
        is_active=wf.is_active,
        node_count=len(gc.get("nodes", [])),
        edge_count=len(gc.get("edges", [])),
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


# --- CRUD ---


@router.get("", response_model=List[wf_schemas.WorkflowSummary],
            dependencies=[Depends(require_permission("agent:view"))])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    """List all workflows."""
    workflows = await workflow_repo.list_workflows(db)
    return [_to_summary(wf) for wf in workflows]


@router.post("", response_model=wf_schemas.WorkflowDetail, status_code=201,
             dependencies=[Depends(require_permission("agent:manage"))])
async def create_workflow(
    payload: wf_schemas.WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    if await workflow_repo.code_exists(db, payload.code):
        raise HTTPException(status_code=400, detail=f"工作流编码 {payload.code} 已存在")
    wf = await workflow_repo.create_workflow(
        db,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        workflow_type=payload.workflow_type,
        graph_config=payload.graph_config.model_dump() if payload.graph_config else {},
    )
    _invalidate_runtime_cache()
    return wf


# --- Static paths MUST be declared before /{workflow_id} ---


@router.get("/definition", response_model=wf_schemas.WorkflowDefinition,
            dependencies=[Depends(require_permission("agent:view"))])
async def get_workflow_definition(db: AsyncSession = Depends(get_db)):
    """Get the current (default) workflow definition for the canvas."""
    wf = await workflow_repo.get_default_workflow(db)
    if wf is None:
        raise HTTPException(status_code=404, detail="尚未创建工作流，请先在后台创建工作流")
    return _to_definition(wf)


@router.get("/traces", response_model=List[TraceOption],
            dependencies=[Depends(require_permission("agent:view"))])
async def list_workflow_traces(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List recent traces for execution path selection."""
    traces = await list_traces(db, limit=limit, offset=offset)
    return [
        TraceOption(
            trace_id=t.trace_id,
            status=t.status,
            intent=t.intent,
            confidence=t.confidence,
            duration_ms=t.duration_ms,
            started_at=t.started_at.isoformat() if t.started_at else None,
        )
        for t in traces
    ]


@router.get("/execution-path/{trace_id}", response_model=ExecutionPath,
            dependencies=[Depends(require_permission("agent:view"))])
async def get_execution_path(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Get the execution path for a specific trace."""
    trace = await get_trace(db, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    spans = await get_spans(db, trace_id)

    NODE_CATEGORY_MAP = {
        "intent": "intent",
        "knowledge": "retrieval",
        "memory": "retrieval",
        "tool": "tool",
        "llm": "model",
        "human": "human",
    }

    steps = []
    for span in spans:
        node_name = span.node_name
        category = NODE_CATEGORY_MAP.get(node_name, "unknown")

        attrs = {}
        if span.input_data:
            attrs["input"] = span.input_data
        if span.output_data:
            attrs["output"] = span.output_data
        if span.error:
            attrs["error"] = span.error

        steps.append(ExecutionStep(
            node_name=node_name,
            node_category=category,
            status=span.status or "success",
            duration_ms=span.duration_ms,
            started_at=span.started_at.isoformat() if span.started_at else None,
            completed_at=span.completed_at.isoformat() if span.completed_at else None,
            attributes=attrs if attrs else None,
        ))

    return ExecutionPath(
        trace_id=trace.trace_id,
        status=trace.status,
        intent=trace.intent,
        confidence=trace.confidence,
        duration_ms=trace.duration_ms,
        steps=steps,
    )


@router.get("/{workflow_id}", response_model=wf_schemas.WorkflowDetail,
            dependencies=[Depends(require_permission("agent:view"))])
async def get_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """Get a workflow with its full graph config."""
    wf = await workflow_repo.get_workflow(db, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf


@router.put("/{workflow_id}", response_model=wf_schemas.WorkflowDetail,
            dependencies=[Depends(require_permission("agent:manage"))])
async def update_workflow(
    workflow_id: int,
    payload: wf_schemas.WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow (used by the editor's save action)."""
    wf = await workflow_repo.get_workflow(db, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")

    updates: Dict[str, Any] = payload.model_dump(exclude_unset=True)
    # NOTE: Pydantic v2 model_dump() already recursively serializes nested
    # models (WorkflowGraphConfig) into plain dicts — no extra conversion.

    wf = await workflow_repo.update_workflow(db, wf, updates)
    _invalidate_runtime_cache()
    return wf


@router.delete("/{workflow_id}", status_code=204,
               dependencies=[Depends(require_permission("agent:manage"))])
async def delete_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a workflow. Refuses when agents are bound to it."""
    wf = await workflow_repo.get_workflow(db, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")

    binding_count = await workflow_repo.count_agent_bindings(db, workflow_id)
    if binding_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该工作流已被 {binding_count} 个 Agent 绑定，无法删除。请先解除绑定。",
        )

    await workflow_repo.delete_workflow(db, wf)
    _invalidate_runtime_cache()


@router.post("/{workflow_id}/publish", response_model=wf_schemas.WorkflowDetail,
             dependencies=[Depends(require_permission("agent:manage"))])
async def publish_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """Publish a workflow so it becomes the runtime default."""
    wf = await workflow_repo.get_workflow(db, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")

    gc = wf.graph_config or {}
    if not gc.get("nodes"):
        raise HTTPException(status_code=400, detail="工作流没有任何节点，无法发布")

    wf = await workflow_repo.publish_workflow(db, wf)
    _invalidate_runtime_cache()
    return wf


# --- Runtime cache invalidation ---


def _invalidate_runtime_cache() -> None:
    """Invalidate the executor's cached workflow graph (safe no-op if absent)."""
    try:
        from app.runtime.executor import invalidate_workflow_cache
        invalidate_workflow_cache()
    except Exception:
        pass
