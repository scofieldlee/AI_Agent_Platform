"""
SupervisorLoop: dynamic decision-making loop for Supervisor mode.

The Supervisor Agent decides at each round which team Agent(s) to call,
based on the task input and previous step outputs. It outputs a JSON
decision: dispatch_agent / dispatch_parallel / finish / human_intervention.

Output-contract guarantee (design doc §4.3.4):
1. Prompt enforces a strict JSON output contract.
2. Parsing: extract ```json block first, fallback to brace extraction.
3. Parse failure or invalid action -> retry once with error feedback.
4. Still failing -> SupervisorOutputError -> Task failed
   (error: supervisor_invalid_output), never silently continue.

Loop protection (double insurance):
- supervisor_max_rounds (decision rounds, default 15)
- max_agent_calls (actual agent executions, default 20)
Either limit exceeded terminates the task immediately.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import employee_repo
from app.employee.runtime.context import EmployeeContext
from app.employee.runtime.dispatcher import AgentDispatcher, render_instruction
from app.employee.runtime.aggregator import ResultAggregator
from app.employee.runtime.exceptions import (
    HumanInterventionRequired,
    SupervisorOutputError,
)
from app.employee.runtime.prompts import (
    build_supervisor_prompt,
    SUPERVISOR_RETRY_SUFFIX,
)

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {
    "dispatch_agent", "dispatch_parallel", "finish", "human_intervention",
}

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

# How many recent artifacts to include in a dispatched Agent's instruction
_MAX_UPSTREAM_IN_INSTRUCTION = 8


def parse_decision(text: str) -> dict:
    """Parse supervisor LLM output into a decision dict.

    Three defense layers:
    1. Extract a ```json ... ``` code block.
    2. Fallback: extract substring from first '{' to last '}'.
    3. Validate action enum + required fields.

    Raises:
        SupervisorOutputError: if no valid decision can be extracted.
    """
    if not text or not text.strip():
        raise SupervisorOutputError("supervisor 输出为空")

    candidates: List[str] = []
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidates.append(match.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    candidates.append(text.strip())

    last_error: Optional[str] = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as e:
            # Parse errors never overwrite a more specific validation error
            # already found in an earlier candidate.
            if last_error is None:
                last_error = f"JSONDecodeError: {e.msg}"
            continue

        if not isinstance(data, dict):
            last_error = "decision is not a JSON object"
            continue

        action = data.get("action")
        if action not in _VALID_ACTIONS:
            last_error = f"invalid action: {action!r}"
            continue

        if action == "dispatch_agent":
            if not isinstance(data.get("agent_id"), int):
                last_error = "dispatch_agent requires integer agent_id"
                continue
        elif action == "dispatch_parallel":
            agents = data.get("agents")
            if not isinstance(agents, list) or not agents:
                last_error = "dispatch_parallel requires non-empty agents list"
                continue
            if not all(
                isinstance(t, dict) and isinstance(t.get("agent_id"), int)
                for t in agents
            ):
                last_error = (
                    "dispatch_parallel entries must be objects "
                    "with integer agent_id"
                )
                continue

        return data

    raise SupervisorOutputError(last_error or "no JSON object found")


class SupervisorLoop:
    """Dynamic supervisor decision loop (Supervisor orchestration mode)."""

    def __init__(self):
        self.dispatcher = AgentDispatcher()
        self.aggregator = ResultAggregator()

    async def run(
        self,
        db: AsyncSession,
        task,
        ctx: EmployeeContext,
        snapshot: dict,
    ) -> Dict[str, Any]:
        """Execute the supervisor decision loop.

        Returns the final aggregated result dict.
        Raises HumanInterventionRequired / SupervisorOutputError /
        RuntimeError (limits exceeded) — handled by EmployeeRuntime.
        """
        config = snapshot.get("config", {})
        max_rounds = config.get("supervisor_max_rounds", 15)
        max_calls = config.get("max_agent_calls", 20)
        step_timeout = config.get("step_timeout_seconds", 300)
        max_retries = config.get("max_retries", 1)

        supervisor_agent_id = snapshot.get("supervisor_agent_id")
        if not supervisor_agent_id:
            raise RuntimeError(
                "supervisor mode requires supervisor_agent_id in snapshot"
            )

        roster: Dict[int, dict] = {
            a["agent_id"]: a for a in snapshot.get("agents", [])
        }
        if not roster:
            raise RuntimeError(
                "supervisor mode requires at least one team agent"
            )

        # On resume (waiting_human -> resume), keep budget accounting
        # from previous decisions so limits are not reset.
        calls = sum(int(d.get("dispatched", 0)) for d in ctx.decisions)
        round_no = len(ctx.decisions)

        logger.info(
            f"SupervisorLoop start | task={task.id} | "
            f"round={round_no}/{max_rounds} | calls={calls}/{max_calls} | "
            f"artifacts={len(ctx.artifacts)}"
        )

        while round_no < max_rounds:
            round_no += 1

            # 1. Build decision prompt
            prompt = build_supervisor_prompt(
                role_name=snapshot.get("employee_name"),
                role_prompt=snapshot.get("role_prompt", ""),
                task_input=task.input or {},
                roster=list(roster.values()),
                context_summary=ctx.summarize(),
                round_no=round_no,
                max_rounds=max_rounds,
                calls_left=max(0, max_calls - calls),
            )

            # 2. Ask the supervisor agent (parse + 1 retry)
            decision = await self._decide(db, task, supervisor_agent_id, prompt)

            action = decision["action"]
            ctx.add_decision({
                "round": round_no,
                "action": action,
                "reason": (decision.get("reason") or "")[:500],
                "dispatched": 0,
            })

            logger.info(
                f"Supervisor decision | task={task.id} | round={round_no} | "
                f"action={action}"
            )

            # 3. Execute the decision
            if action == "finish":
                return await self._finish(db, task, ctx, snapshot, decision)

            if action == "human_intervention":
                reason = decision.get("reason") or (
                    "Supervisor requested human intervention"
                )
                await self._create_human_task(task, snapshot, reason)
                await employee_repo.update_task(
                    db, task, context=ctx.to_dict())
                await db.commit()
                raise HumanInterventionRequired(reason)

            if action in ("dispatch_agent", "dispatch_parallel"):
                targets = (
                    [{"agent_id": decision["agent_id"],
                      "input": decision.get("input") or {}}]
                    if action == "dispatch_agent"
                    else decision["agents"]
                )
                # Dispatched agents must be team members
                invalid = [t["agent_id"] for t in targets
                           if t["agent_id"] not in roster]
                if invalid:
                    raise SupervisorOutputError(
                        f"dispatched agent(s) not in roster: {invalid}"
                    )

                calls += len(targets)
                if calls > max_calls:
                    raise RuntimeError(
                        f"max_agent_calls exceeded ({max_calls})"
                    )
                ctx.decisions[-1]["dispatched"] = len(targets)
                ctx.decisions[-1]["agents"] = [t["agent_id"] for t in targets]

                await self._dispatch(
                    db, task, ctx, roster, targets,
                    round_no, step_timeout, max_retries,
                )
                # Persist context after each round (visible to frontend polling)
                await employee_repo.update_task(
                    db, task, context=ctx.to_dict())
                await db.commit()
                continue

            raise SupervisorOutputError(f"unknown action: {action!r}")

        raise RuntimeError(
            f"supervisor_max_rounds exceeded ({max_rounds})"
        )

    # ------------------------------------------------------------------
    # Decision (supervisor agent call + JSON parsing + 1 retry)
    # ------------------------------------------------------------------

    async def _decide(
        self,
        db: AsyncSession,
        task,
        supervisor_agent_id: int,
        prompt: str,
    ) -> dict:
        """Call the supervisor agent and parse its JSON decision.

        On parse failure, retry once with the error appended to the prompt.
        """
        last_error = "unknown"
        for attempt in range(2):  # 1 try + 1 retry
            instruction = prompt
            if attempt > 0:
                instruction = prompt + SUPERVISOR_RETRY_SUFFIX.format(
                    parse_error=last_error,
                )

            result = await self.dispatcher.execute(
                agent_id=supervisor_agent_id,
                instruction=instruction,
                user_id=task.user_id,
                tenant_id=task.tenant_id,
            )

            if not result.get("success"):
                # The supervisor agent itself failed (not a parse issue)
                raise RuntimeError(
                    "supervisor agent execution failed: "
                    f"{(result.get('summary') or '')[:300]}"
                )

            try:
                return parse_decision(result.get("summary") or "")
            except SupervisorOutputError as e:
                last_error = str(e)
                logger.warning(
                    f"Supervisor output parse failed "
                    f"(task={task.id}, attempt={attempt}): {e}"
                )

        raise SupervisorOutputError(
            f"supervisor_invalid_output: {last_error}"
        )

    # ------------------------------------------------------------------
    # Decision handlers
    # ------------------------------------------------------------------

    async def _finish(
        self,
        db: AsyncSession,
        task,
        ctx: EmployeeContext,
        snapshot: dict,
        decision: dict,
    ) -> dict:
        """Finish: aggregate artifacts; supervisor summary wins if provided."""
        final = await self.aggregator.aggregate(ctx, snapshot, skipped_steps=[])
        sup_result = decision.get("result")
        if isinstance(sup_result, dict) and sup_result.get("summary"):
            final["summary"] = str(sup_result["summary"])
        final["supervisor_finished"] = True

        await employee_repo.update_task(db, task, context=ctx.to_dict())
        await db.commit()
        return final

    async def _create_human_task(self, task, snapshot: dict, reason: str) -> None:
        """Create a Human Center ticket for human intervention."""
        try:
            from app.human_center.service import HumanCenterService

            task_input = task.input or {}
            input_msg = (
                task_input.get("message")
                or task_input.get("title")
                or task.title
            )
            await HumanCenterService().create_task(
                conversation_id=None,
                agent_id=snapshot.get("supervisor_agent_id"),
                user_id=task.user_id,
                user_message=(
                    f"[AI员工任务 #{task.id} · "
                    f"{snapshot.get('employee_name', '')}] {input_msg}"
                ),
                transfer_reason="user_request",
                trace_id=None,
                agent_answer=reason[:500],
                extra_context={
                    "ai_employee_task_id": task.id,
                    "employee_name": snapshot.get("employee_name"),
                    "supervisor_reason": reason[:500],
                },
            )
            logger.info(
                f"Human task created for employee task {task.id}: {reason[:200]}"
            )
        except Exception as e:
            # Human ticket creation failure must not lose the original reason
            logger.error(
                f"Failed to create human task for employee task {task.id}: {e}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Dispatch (dynamic TaskStep creation + sequential execution)
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        db: AsyncSession,
        task,
        ctx: EmployeeContext,
        roster: Dict[int, dict],
        targets: List[dict],
        round_no: int,
        step_timeout: int,
        max_retries: int,
    ) -> None:
        """Create TaskSteps for the dispatched agents and execute them.

        Steps execute sequentially within a round (MVP; AsyncSession is not
        safe for concurrent use). "parallel" here means multiple agents are
        dispatched in one round based on one supervisor decision.

        A failed step does NOT fail the task: its failure is recorded as an
        artifact so the supervisor can decide to retry or finish (dynamic
        recovery — the key advantage over DAG mode).
        """
        # Build unique step keys (same agent may be dispatched twice/round)
        key_counter: Dict[int, int] = {}
        for target in targets:
            aid = target["agent_id"]
            key_counter[aid] = key_counter.get(aid, 0) + 1
            suffix = "" if key_counter[aid] == 1 else f"_{key_counter[aid]}"
            step_key = f"round{round_no}_agent{aid}{suffix}"

            agent_info = roster[aid]
            dispatch_input = target.get("input") or {}

            step = await employee_repo.create_step(
                db,
                task_id=task.id,
                agent_id=aid,
                step_key=step_key,
                role=agent_info.get("role"),
                input_data={
                    "instruction": None,
                    "dispatch_input": dispatch_input,
                },
                tenant_id=task.tenant_id,
            )
            await db.commit()

            agent_cfg = agent_info.get("config") or {}
            timeout = agent_cfg.get("timeout_seconds", step_timeout)
            retries = agent_cfg.get("max_retries", max_retries)

            await self._execute_step(
                db, task, ctx, step, agent_info,
                dispatch_input, timeout, retries,
            )

    async def _execute_step(
        self,
        db: AsyncSession,
        task,
        ctx: EmployeeContext,
        step,
        agent_info: dict,
        dispatch_input: dict,
        timeout: int,
        max_retries: int,
    ) -> dict:
        """Execute one dispatched agent step with retry + timeout.

        On success: step completed, artifact added.
        On failure after retries: step failed, failure recorded as artifact
        (supervisor decides what to do next).
        """
        step_key = step.step_key
        agent_id = agent_info["agent_id"]

        # Merge task input with the supervisor's dispatch input
        merged_input = dict(task.input or {})
        merged_input.update(dispatch_input or {})

        # Upstream context: most recent artifacts (each truncated by
        # render_instruction)
        upstream = self._recent_artifacts(ctx, _MAX_UPSTREAM_IN_INSTRUCTION)

        instruction = render_instruction(
            task_input=merged_input,
            step_role=agent_info.get("role"),
            upstream_outputs=upstream,
        )

        await employee_repo.update_step(
            db, step,
            status="running",
            started_at=datetime.now(timezone.utc),
            input={"instruction": instruction[:500],
                   "dispatch_input": dispatch_input},
        )
        await db.commit()

        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self.dispatcher.execute(
                        agent_id=agent_id,
                        instruction=instruction,
                        user_id=task.user_id,
                        tenant_id=task.tenant_id,
                    ),
                    timeout=timeout,
                )

                if result.get("success"):
                    await employee_repo.update_step(
                        db, step,
                        status="completed",
                        output=result,
                        trace_id=result.get("metadata", {}).get("trace_id"),
                        retry_count=attempt,
                        completed_at=datetime.now(timezone.utc),
                    )
                    await db.commit()
                    ctx.add_artifact(step_key, result)
                    logger.info(
                        f"Supervisor step '{step_key}' completed "
                        f"(attempt={attempt}, trace="
                        f"{result.get('metadata', {}).get('trace_id')})"
                    )
                    return result

                # Agent returned a soft failure (e.g. need_human)
                last_error = (result.get("summary") or "agent soft failure")[:500]
                logger.warning(
                    f"Supervisor step '{step_key}' soft failure "
                    f"(attempt={attempt}): {last_error[:200]}"
                )

            except asyncio.TimeoutError:
                last_error = f"Timed out after {timeout}s"
                logger.warning(
                    f"Supervisor step '{step_key}' timed out "
                    f"(attempt={attempt}, timeout={timeout}s)"
                )
            except Exception as e:
                last_error = str(e)[:500]
                logger.warning(
                    f"Supervisor step '{step_key}' error "
                    f"(attempt={attempt}): {last_error[:200]}"
                )

            if attempt < max_retries:
                continue

        # All retries exhausted -> record failure as artifact and continue
        # (supervisor decides: retry, alternative agent, finish, or escalate)
        failed_result = {
            "success": False,
            "summary": f"Step failed: {last_error}",
            "data": {},
            "metadata": {"error": last_error},
        }
        await employee_repo.update_step(
            db, step,
            status="failed",
            error={"code": "step_error", "message": last_error},
            retry_count=max_retries,
            completed_at=datetime.now(timezone.utc),
        )
        await db.commit()
        ctx.add_artifact(step_key, failed_result)
        logger.warning(f"Supervisor step '{step_key}' failed: {last_error}")
        return failed_result

    @staticmethod
    def _recent_artifacts(
        ctx: EmployeeContext, limit: int,
    ) -> Dict[str, dict]:
        """Return the N most recent artifacts (insertion order preserved)."""
        items = list(ctx.artifacts.items())
        if len(items) <= limit:
            return dict(items)
        return dict(items[-limit:])
