"""
EmployeeContext: task-level shared context for multi-Agent orchestration.

Persisted in ai_employee_tasks.context (JSONB). Survives across steps,
can be rebuilt from the database for resume after human intervention.
"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Truncate artifact summaries to prevent prompt context bloat
_MAX_ARTIFACT_CHARS = 2000


class EmployeeContext:
    """Task-level shared context, persisted in ai_employee_tasks.context."""

    def __init__(
        self,
        task_id: int,
        goal: str = "",
        input_data: Optional[dict] = None,
        artifacts: Optional[Dict[str, dict]] = None,
        decisions: Optional[List[dict]] = None,
    ):
        self.task_id = task_id
        self.goal = goal
        self.input = input_data or {}
        self.artifacts: Dict[str, dict] = artifacts or {}
        # artifacts: {step_key: AgentResult}
        self.decisions: List[dict] = decisions or []
        # decisions: Supervisor decision log (audit trail)

    def add_artifact(self, step_key: str, result: dict) -> None:
        """Store an Agent's execution result."""
        self.artifacts[step_key] = {
            "success": result.get("success", False),
            "summary": result.get("summary", ""),
            "data": result.get("data", {}),
            "metadata": result.get("metadata", {}),
        }

    def upstream_of(self, step_key: str) -> Dict[str, dict]:
        """Get upstream artifacts for a step (by step_key depends_on).

        Returns {step_key: AgentResult} for all dependencies.
        """
        # This is called by dispatcher with explicit depends_on list
        # The actual depends_on resolution is in dag_scheduler
        return self.artifacts

    def get_upstream_outputs(
        self, depends_on_step_keys: List[str],
    ) -> Dict[str, dict]:
        """Get outputs of specific upstream steps by their step_keys."""
        return {
            k: self.artifacts[k]
            for k in depends_on_step_keys
            if k in self.artifacts
        }

    def summarize(self) -> str:
        """Produce a text summary of all artifacts (for Supervisor prompt)."""
        if not self.artifacts:
            return "(no steps completed yet)"
        parts = []
        for key, art in self.artifacts.items():
            summary = (art.get("summary") or "")[:_MAX_ARTIFACT_CHARS]
            parts.append(f"[{key}] {summary}")
        return "\n".join(parts)

    def add_decision(self, decision: dict) -> None:
        """Log a Supervisor decision (audit trail)."""
        self.decisions.append(decision)

    def to_dict(self) -> dict:
        """Serialize for persistence in ai_employee_tasks.context."""
        return {
            "goal": self.goal,
            "input": self.input,
            "artifacts": self.artifacts,
            "decisions": self.decisions,
        }

    @classmethod
    def from_task(cls, task) -> "EmployeeContext":
        """Rebuild context from a task's context JSONB (for resume)."""
        ctx_data = task.context or {}
        return cls(
            task_id=task.id,
            goal=(task.employee_snapshot or {}).get("goal", ""),
            input_data=task.input or {},
            artifacts=ctx_data.get("artifacts", {}),
            decisions=ctx_data.get("decisions", []),
        )

    @classmethod
    def init(cls, task_id: int, input_data: dict, snapshot: dict) -> "EmployeeContext":
        """Initialize a fresh context for a new task."""
        return cls(
            task_id=task_id,
            goal=snapshot.get("goal", ""),
            input_data=input_data,
        )
