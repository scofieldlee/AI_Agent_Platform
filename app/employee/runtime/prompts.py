"""
Prompt templates for the AI Employee runtime.

Currently contains the Supervisor decision prompt (design doc §8.1)
and helpers to render roster / task / context sections.
"""

import json
from typing import Dict, Any, List

SUPERVISOR_DECISION_PROMPT = """你是 AI 员工「{role_name}」的调度大脑。

# 你的职责
{role_prompt}

# 团队 Agent 清单（只能从以下 Agent 中选择）
{roster_text}

# 任务
{task_text}

# 已完成步骤的产出摘要
{context_summary}

# 决策轮次
第 {round_no} / {max_rounds} 轮（剩余 Agent 调用额度：{calls_left}）

# 输出要求（必须且只能输出一个 JSON 代码块，不要输出其他内容）
下一步动作，从以下四种中选择：

1. 派发单个 Agent：
```json
{{"action": "dispatch_agent", "agent_id": <int>, "reason": "<为什么>", "input": {{}}}}
```
2. 并行派发多个 Agent：
```json
{{"action": "dispatch_parallel", "agents": [{{"agent_id": <int>, "input": {{}}}}], "reason": "<为什么>"}}
```
3. 任务完成：
```json
{{"action": "finish", "result": {{"summary": "<最终结果总结>"}}}}
```
4. 需要人工介入：
```json
{{"action": "human_intervention", "reason": "<无法自主决策的原因>"}}
```
"""

# Appended when the previous decision output failed to parse.
SUPERVISOR_RETRY_SUFFIX = """

# 上一次输出解析失败
你上一次的输出无法解析为有效的 JSON 决策（错误：{parse_error}）。
请严格遵循上述输出要求，重新输出一个且仅一个 JSON 代码块，不要输出任何其他文字。
"""


def build_roster_text(agents: List[dict]) -> str:
    """Render the team agent roster for the supervisor prompt."""
    lines = []
    for a in agents:
        name = a.get("name") or f"agent_{a.get('agent_id')}"
        role = a.get("role") or "（未设置角色）"
        desc = a.get("description") or ""
        line = f"- agent_id={a.get('agent_id')} | {name} | 角色：{role}"
        if desc:
            line += f" | {desc[:200]}"
        lines.append(line)
    return "\n".join(lines) if lines else "(团队为空)"


def build_task_text(task_input: dict) -> str:
    """Render the task input section (message/title or full JSON)."""
    if not task_input:
        return "(无任务输入)"
    message = (
        task_input.get("message")
        or task_input.get("title")
        or json.dumps(task_input, ensure_ascii=False)
    )
    return str(message)


def build_supervisor_prompt(
    role_name: str,
    role_prompt: str,
    task_input: dict,
    roster: List[dict],
    context_summary: str,
    round_no: int,
    max_rounds: int,
    calls_left: int,
) -> str:
    """Render the full supervisor decision prompt (design doc §8.1)."""
    role_prompt_text = (role_prompt or "").strip() or (
        "根据任务目标，合理调度团队 Agent 完成任务，并在完成后给出最终总结。"
    )
    return SUPERVISOR_DECISION_PROMPT.format(
        role_name=role_name or "AI员工",
        role_prompt=role_prompt_text,
        roster_text=build_roster_text(roster),
        task_text=build_task_text(task_input),
        context_summary=(context_summary or "").strip() or "(尚无已完成的步骤)",
        round_no=round_no,
        max_rounds=max_rounds,
        calls_left=calls_left,
    )
