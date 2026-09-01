"""审计日志 Schema：查询参数与响应模型。"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogListItem(BaseModel):
    """审计日志列表项（不返回大字段，保证列表轻量）。"""

    id: int
    request_id: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    summary: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    success: bool = True
    ip_address: Optional[str] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogDetail(AuditLogListItem):
    """审计日志详情（含请求体与变更 diff）。"""

    user_agent: Optional[str] = None
    request_body: Optional[Dict[str, Any]] = None
    changes: Optional[Dict[str, Any]] = None


class AuditLogPage(BaseModel):
    """分页响应。"""

    items: List[AuditLogListItem]
    total: int
    page: int
    page_size: int


class AuditLogQuery(BaseModel):
    """查询参数（不用于校验，仅作文档参考）。"""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    keyword: Optional[str] = None          # summary / resource_name / username 模糊
    action: Optional[str] = None
    resource_type: Optional[str] = None
    username: Optional[str] = None
    user_id: Optional[int] = None
    success: Optional[bool] = None
    request_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class AuditStats(BaseModel):
    """概览统计（可选扩展）。"""

    total: int
    success_count: int
    failed_count: int
    today_count: int
    action_distribution: Dict[str, int]
