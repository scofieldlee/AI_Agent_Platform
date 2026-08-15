"""
Agent schemas.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# --- Default input config ---
DEFAULT_ALLOWED_INPUT_TYPES = ["text"]
DEFAULT_MAX_FILE_SIZE_MB = 10
DEFAULT_MAX_FILES_PER_MESSAGE = 5

ALL_INPUT_TYPES = ["text", "pdf", "word", "excel", "image", "video"]


class AgentCreate(BaseModel):
    """Create a new agent."""
    name: str
    code: str
    description: Optional[str] = None
    agent_type: str = "customer_service"
    config: dict = {}


class AgentUpdate(BaseModel):
    """Update an existing agent. All fields optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    agent_type: Optional[str] = None
    status: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None


class ToolBindingResponse(BaseModel):
    """Tool binding info in agent detail."""
    tool_id: int
    tool_name: str
    tool_type: str
    description: Optional[str] = None
    permission: str = "allow"

    model_config = {"from_attributes": True}


class KnowledgeBindingResponse(BaseModel):
    """Knowledge base binding info in agent detail."""
    knowledge_base_id: int
    name: str
    kb_type: Optional[str] = None

    model_config = {"from_attributes": True}


class VersionResponse(BaseModel):
    """Agent version history item."""
    id: int
    version: str
    changelog: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkflowBindingResponse(BaseModel):
    """Workflow binding info in agent detail."""
    workflow_id: int
    name: str
    code: str
    status: str = "draft"
    version: str = "0.1.0"
    is_primary: bool = False
    node_count: int = 0

    model_config = {"from_attributes": True}


class AgentResponse(BaseModel):
    """Agent list item."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    agent_type: str
    status: str
    version: str
    config: dict
    is_active: bool
    chat_token: Optional[str] = None
    workflow: Optional[dict] = None  # primary workflow summary, if bound

    model_config = {"from_attributes": True}


class AgentDetailResponse(AgentResponse):
    """Agent detail with bindings and version history."""
    tool_bindings: List[ToolBindingResponse] = []
    knowledge_bindings: List[KnowledgeBindingResponse] = []
    workflow_bindings: List[WorkflowBindingResponse] = []
    versions: List[VersionResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ToolBindingRequest(BaseModel):
    """Set tool bindings for an agent."""
    tool_names: List[str]


class KnowledgeBindingRequest(BaseModel):
    """Set knowledge base bindings for an agent."""
    knowledge_base_ids: List[int]


class WorkflowBindingRequest(BaseModel):
    """Set workflow bindings for an agent.

    The first element of workflow_ids becomes the primary workflow
    (is_primary=True) used by the runtime; the rest are secondary.
    Pass an empty list to unbind all workflows.
    """
    workflow_ids: List[int] = []


def get_input_config(agent_config: dict) -> dict:
    """Extract attachment input configuration from agent config.

    Returns a dict with:
      - allowed_input_types: List[str]
      - max_file_size_mb: int
      - max_files_per_message: int
    Falls back to defaults if not configured.
    """
    if not agent_config:
        return {
            "allowed_input_types": DEFAULT_ALLOWED_INPUT_TYPES,
            "max_file_size_mb": DEFAULT_MAX_FILE_SIZE_MB,
            "max_files_per_message": DEFAULT_MAX_FILES_PER_MESSAGE,
        }
    return {
        "allowed_input_types": agent_config.get("allowed_input_types", DEFAULT_ALLOWED_INPUT_TYPES),
        "max_file_size_mb": agent_config.get("max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB),
        "max_files_per_message": agent_config.get("max_files_per_message", DEFAULT_MAX_FILES_PER_MESSAGE),
    }
