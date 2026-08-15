"""Memory Center API endpoints: manage agent long-term memories."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.memory.service import MemoryService
from app.auth.dependencies import require_permission
from app.schemas.memory import MemoryCreate, MemoryUpdate, MemoryResponse, MemoryListResponse

router = APIRouter(dependencies=[Depends(require_permission("memory:view"))])


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    user_id: Optional[int] = Query(None, description="Filter by user"),
    agent_id: Optional[int] = Query(None, description="Filter by agent"),
    memory_type: Optional[str] = Query(None, description="Filter by type"),
    status: str = Query("active", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """List memories with optional filters and pagination."""
    service = MemoryService()
    return await service.list_memories(
        user_id=user_id,
        agent_id=agent_id,
        memory_type=memory_type,
        status=status,
        page=page,
        size=size,
    )


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: int):
    """Get a single memory by ID."""
    service = MemoryService()
    memory = await service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("", response_model=dict)
async def create_memory(req: MemoryCreate):
    """Manually create a memory with embedding."""
    service = MemoryService()
    return await service.create_memory(
        content=req.content,
        memory_type=req.memory_type,
        importance=req.importance,
        user_id=req.user_id,
        agent_id=req.agent_id,
    )


@router.patch("/{memory_id}", response_model=dict)
async def update_memory(memory_id: int, req: MemoryUpdate):
    """Update memory importance or status."""
    service = MemoryService()
    result = await service.update_memory(
        memory_id=memory_id,
        importance=req.importance,
        status=req.status,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


@router.delete("/{memory_id}")
async def delete_memory(memory_id: int):
    """Soft-delete a memory (set status to 'archived')."""
    service = MemoryService()
    success = await service.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Memory archived", "id": memory_id}


@router.get("/search/results")
async def search_memories(
    query: str = Query(..., description="Search query"),
    user_id: Optional[int] = Query(None),
    agent_id: Optional[int] = Query(None),
    top_k: int = Query(5, ge=1, le=20),
):
    """Semantic search memories by query."""
    service = MemoryService()
    memories = await service.retrieve_memories(
        query=query,
        user_id=user_id,
        agent_id=agent_id,
        top_k=top_k,
    )
    return {"query": query, "results": memories, "count": len(memories)}
