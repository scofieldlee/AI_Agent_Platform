"""
Model registry: import all models so SQLAlchemy Base.metadata discovers them.
"""

from app.models.user import (
    User, UserProfile, Organization, Role, Permission,
    UserRole, RolePermission,
)
from app.models.agent import (
    Agent, AgentVersion, AgentWorkflowBinding,
    AgentKnowledgeBinding, AgentToolBinding,
)
from app.models.workflow import (
    Workflow, WorkflowNode, WorkflowRun,
)
from app.models.knowledge import (
    KnowledgeBase, Document, Chunk,
)
from app.models.conversation import (
    Conversation, Message,
)
from app.models.memory import Memory
from app.models.tool import Tool, ToolExecution
from app.models.model_config import (
    ModelProvider, ModelConfig, ModelUsageLog,
)

__all__ = [
    # User
    "User", "UserProfile", "Organization", "Role", "Permission",
    "UserRole", "RolePermission",
    # Agent
    "Agent", "AgentVersion", "AgentWorkflowBinding",
    "AgentKnowledgeBinding", "AgentToolBinding",
    # Workflow
    "Workflow", "WorkflowNode", "WorkflowRun",
    # Knowledge
    "KnowledgeBase", "Document", "Chunk",
    # Conversation
    "Conversation", "Message",
    # Memory
    "Memory",
    # Tool
    "Tool", "ToolExecution",
    # Model
    "ModelProvider", "ModelConfig", "ModelUsageLog",
]
