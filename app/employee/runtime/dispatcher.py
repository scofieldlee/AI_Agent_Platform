"""
AgentDispatcher: the adaptation layer between EmployeeRuntime and AgentRuntime.

Responsibilities:
1. Render structured task input into an Agent-understandable instruction.
2. Call AgentRuntime.execute_task() (programmatic entry, no conversation).
3. Return AgentResult to the scheduler.
"""

import json
import logging
from typing import Dict, Any, Optional

from app.runtime.executor import AgentRuntime

logger = logging.getLogger(__name__)

_MAX_UPSTREAM_CHARS = 2000


def render_instruction(
    task_input: dict,
    step_role: Optional[str],
    upstream_outputs: Dict[str, dict],
) -> str:
    """Render structured input into an Agent instruction text.

    Args:
        task_input: The original task input (e.g. {"message": "..."})
        step_role: The Agent's role in this employee (e.g. "商品分析")
        upstream_outputs: {step_key: AgentResult} from dependency steps

    Returns:
        A formatted instruction string for the Agent.
    """
    parts = []

    # Main task message
    message = (
        task_input.get("message")
        or task_input.get("title")
        or json.dumps(task_input, ensure_ascii=False)
    )
    parts.append(f"## 任务\n{message}")

    # Agent role
    if step_role:
        parts.append(f"## 你的角色\n{step_role}")

    # Upstream outputs (dependency results)
    if upstream_outputs:
        parts.append("## 上游步骤输出（依据这些信息完成任务）")
        for key, out in upstream_outputs.items():
            summary = (out or {}).get("summary", "")
            if len(summary) > _MAX_UPSTREAM_CHARS:
                summary = summary[:_MAX_UPSTREAM_CHARS] + "...(截断)"
            parts.append(f"### {key}\n{summary}")

    return "\n\n".join(parts)


class AgentDispatcher:
    """Calls AgentRuntime.execute_task() with rendered instructions."""

    def __init__(self):
        self.runtime = AgentRuntime()

    async def execute(
        self,
        agent_id: int,
        instruction: str,
        user_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute a single Agent and return AgentResult.

        This is the single point where EmployeeRuntime calls AgentRuntime.
        conversation_id is None (no Conversation/Message records).
        """
        try:
            result = await self.runtime.execute_task(
                agent_id=agent_id,
                task_instruction=instruction,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            return result
        except Exception as e:
            logger.error(
                f"AgentRuntime.execute_task failed (agent_id={agent_id}): {e}",
                exc_info=True,
            )
            return {
                "success": False,
                "summary": f"Agent execution error: {str(e)[:500]}",
                "data": {},
                "artifacts": {},
                "metadata": {"error": str(e)[:500]},
            }
