"""
AI Employee schemas (Pydantic v2).
"""

from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Binding schemas
# ---------------------------------------------------------------------------

class AgentBindingIn(BaseModel):
    """A single Agent binding with DAG dependency info."""
    agent_id: int
    role: Optional[str] = None
    priority: int = 0
    enabled: bool = True
    depends_on: List[int] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class AgentBindingsUpdate(BaseModel):
    """Full-replace binding set for an employee."""
    agents: List[AgentBindingIn]


class AgentBindingResponse(BaseModel):
    """Binding info in employee detail."""
    id: int
    agent_id: int
    role: Optional[str] = None
    priority: int = 0
    enabled: bool = True
    depends_on: List[int] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    agent_name: Optional[str] = None
    agent_code: Optional[str] = None
    agent_status: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Employee schemas
# ---------------------------------------------------------------------------

class EmployeeCreate(BaseModel):
    """Create a new AI Employee."""
    name: str
    code: str
    description: Optional[str] = None
    role: Optional[str] = None
    goal: Optional[str] = None
    role_prompt: Optional[str] = None
    orchestration_mode: str = "dag"  # dag / supervisor
    supervisor_agent_id: Optional[int] = None
    config: dict = Field(default_factory=dict)


class EmployeeUpdate(BaseModel):
    """Update an existing AI Employee. All fields optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    goal: Optional[str] = None
    role_prompt: Optional[str] = None
    orchestration_mode: Optional[str] = None
    supervisor_agent_id: Optional[int] = None
    config: Optional[dict] = None


class EmployeeResponse(BaseModel):
    """Employee list item (without bindings)."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    role: Optional[str] = None
    goal: Optional[str] = None
    orchestration_mode: str = "dag"
    supervisor_agent_id: Optional[int] = None
    status: str = "draft"
    config: dict = Field(default_factory=dict)
    agent_count: int = 0
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmployeeDetailResponse(EmployeeResponse):
    """Employee detail with bindings."""
    bindings: List[AgentBindingResponse] = Field(default_factory=list)
    supervisor_agent_name: Optional[str] = None


class SelectableAgentResponse(BaseModel):
    """Published Agent for binding dropdown."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    status: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Task / Step schemas
# ---------------------------------------------------------------------------

class ExecuteRequest(BaseModel):
    """Submit a task to an AI Employee."""
    input: dict
    title: Optional[str] = None


class ExecuteResponse(BaseModel):
    """Immediate response after task creation."""
    task_id: int
    status: str = "pending"


class TaskResumeRequest(BaseModel):
    """Resume a waiting_human task, optionally carrying human feedback.

    The feedback (e.g. a resolved ticket's resolution note) is injected
    into the task context so the Supervisor sees the human decision.
    """
    human_feedback: Optional[str] = None


class StepResponse(BaseModel):
    """A single task step."""
    id: int
    agent_id: int
    step_key: str
    role: Optional[str] = None
    status: str
    input: Optional[dict] = None
    output: Optional[dict] = None
    depends_on: List[str] = Field(default_factory=list)
    retry_count: int = 0
    trace_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[dict] = None
    agent_name: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskResponse(BaseModel):
    """Task detail (with steps for polling)."""
    id: int
    employee_id: int
    user_id: Optional[int] = None
    title: str
    input: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    status: str
    current_step_id: Optional[int] = None
    result: Optional[dict] = None
    error: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    steps: List[StepResponse] = Field(default_factory=list)
    employee_name: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """Task list item (without steps)."""
    id: int
    employee_id: int
    user_id: Optional[int] = None
    title: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    employee_name: Optional[str] = None
    step_count: int = 0
    completed_steps: int = 0

    model_config = {"from_attributes": True}
