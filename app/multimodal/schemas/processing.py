"""Multimodal Knowledge Base schemas — 处理任务."""

from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class ProcessingTaskResponse(BaseModel):
    """处理任务记录."""
    id: int
    asset_id: Optional[int] = None
    knowledge_base_id: Optional[int] = None
    task_type: str
    status: str
    model: Optional[str] = None
    input: Optional[dict] = None
    output: Optional[dict] = None
    error: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProcessingTaskListResponse(BaseModel):
    """处理任务列表."""
    total: int
    items: List[ProcessingTaskResponse] = Field(default_factory=list)


class TaskTriggerResponse(BaseModel):
    """触发异步任务响应."""
    task_id: int
    asset_id: int
    task_type: str
    status: str
    message: str = "任务已提交"


class BatchAnalyzeRequest(BaseModel):
    """批量分析请求."""
    asset_ids: List[int] = Field(..., min_length=1)
