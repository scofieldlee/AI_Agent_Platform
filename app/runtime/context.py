"""
AgentContext: execution context for a single agent run.
Carries user/tenant/conversation/agent/trace information.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import uuid


@dataclass
class AgentContext:
    """Context for a single agent execution.

    Passed through the entire workflow, accessible by all nodes.
    """

    user_id: Optional[int] = None
    tenant_id: Optional[int] = None
    conversation_id: Optional[int] = None
    agent_id: Optional[int] = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "trace_id": self.trace_id,
            "metadata": self.metadata,
        }
