"""
Workflow schemas: workflow definitions for the visual editor.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# --- Graph config (stored in workflows.graph_config JSONB) ---

class WorkflowNodeDef(BaseModel):
    """A node in the workflow graph.

    node_type is the executor implementation key:
      intent / knowledge / memory / tool / llm / human
    category is the visual grouping (intent / retrieval / tool / model / human).
    """
    id: str
    name: str
    node_type: str = "intent"
    type: str = "processing"  # entry, processing, decision, output, terminal
    category: str = "intent"  # intent, retrieval, tool, model, human, system
    description: str = ""
    inputs: List[str] = []
    outputs: List[str] = []
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    config: Dict[str, Any] = Field(default_factory=dict)  # node-specific params


class WorkflowEdgeDef(BaseModel):
    """A directed edge between two nodes.

    Conditional edges carry a condition expression evaluated against the
    LangGraph state, e.g. "confidence >= 0.5" or "need_human".
    target may be "END" for terminal edges.
    """
    id: str
    source: str
    target: str
    label: Optional[str] = None
    condition: Optional[str] = None
    edge_type: str = "default"  # default, conditional


class WorkflowGraphConfig(BaseModel):
    """Complete graph definition: entry point + nodes + edges."""
    entry_point: str = "intent"
    nodes: List[WorkflowNodeDef] = Field(default_factory=list)
    edges: List[WorkflowEdgeDef] = Field(default_factory=list)


# --- CRUD request/response ---

class WorkflowCreate(BaseModel):
    """Create a new workflow."""
    name: str
    code: str
    description: Optional[str] = None
    workflow_type: str = "hybrid"  # static, dynamic, hybrid
    graph_config: Optional[WorkflowGraphConfig] = None


class WorkflowUpdate(BaseModel):
    """Update an existing workflow. All fields optional."""
    name: Optional[str] = None
    description: Optional[str] = None
    workflow_type: Optional[str] = None
    graph_config: Optional[WorkflowGraphConfig] = None
    is_active: Optional[bool] = None


class WorkflowSummary(BaseModel):
    """Workflow list item (no full graph config)."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    workflow_type: str
    status: str
    version: str
    is_active: bool
    node_count: int = 0
    edge_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkflowDetail(BaseModel):
    """Workflow detail with full graph config."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    workflow_type: str
    status: str
    version: str
    is_active: bool
    graph_config: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Read-only definition view (compatible with the old /definition endpoint) ---

class WorkflowDefNode(BaseModel):
    id: str
    name: str
    node_type: str
    type: str
    category: str
    description: str
    inputs: List[str]
    outputs: List[str]
    position: Dict[str, float]
    config: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDefEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None
    condition: Optional[str] = None
    edge_type: str = "default"


class WorkflowDefinition(BaseModel):
    """The resolved workflow definition used by the canvas."""
    id: Optional[int] = None
    code: Optional[str] = None
    name: str
    description: str
    entry_point: str
    nodes: List[WorkflowDefNode]
    edges: List[WorkflowDefEdge]
