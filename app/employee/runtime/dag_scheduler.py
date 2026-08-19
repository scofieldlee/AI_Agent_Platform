"""
DagScheduler: topological execution of Agent steps.

- Statically creates all TaskSteps from the snapshot.
- Runs ready steps in parallel (asyncio.gather).
- Handles retries, skips, and fail-fast/skip-on-failure policies.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import employee_repo
from app.employee.runtime.context import EmployeeContext
from app.employee.runtime.dispatcher import AgentDispatcher, render_instruction
from app.employee.runtime.aggregator import ResultAggregator

logger = logging.getLogger(__name__)


class StepFailed(Exception):
    """Raised when a step fails after all retries."""
    def __init__(self, step_key: str, message: str):
        self.step_key = step_key
        super().__init__(f"Step '{step_key}' failed: {message}")


class DagScheduler:
    """DAG-based topological scheduler for Agent execution."""

    def __init__(self):
        self.dispatcher = AgentDispatcher()
        self.aggregator = ResultAggregator()

    async def run(
        self,
        db: AsyncSession,
        task,
        ctx: EmployeeContext,
        snapshot: dict,
    ) -> dict:
        """Execute all steps in topological order.

        Returns the aggregated result dict.
        """
        agents_config = snapshot.get("agents", [])
        config = snapshot.get("config", {})
        max_calls = config.get("max_agent_calls", 20)
        max_retries = config.get("max_retries", 1)
        step_timeout = config.get("step_timeout_seconds", 300)
        fail_fast = config.get("fail_fast", False)

        # 1. Build step_key mapping: agent_id -> step_key
        step_keys: Dict[int, str] = {}
        for agent_info in agents_config:
            aid = agent_info["agent_id"]
            step_keys[aid] = f"agent_{aid}"

        # 2. Create TaskSteps (static, all at once)
        steps: Dict[str, dict] = {}  # step_key -> step_info
        for agent_info in agents_config:
            aid = agent_info["agent_id"]
            sk = step_keys[aid]
            dep_keys = [step_keys[d] for d in (agent_info.get("depends_on") or []) if d in step_keys]

            # Create step in DB if not exists
            db_step = await employee_repo.create_step(
                db,
                task_id=task.id,
                agent_id=aid,
                step_key=sk,
                role=agent_info.get("role"),
                input_data={"instruction": None, "upstream_keys": dep_keys},
                depends_on=dep_keys,
            )

            steps[sk] = {
                "step_id": db_step.id,
                "agent_id": aid,
                "role": agent_info.get("role"),
                "depends_on": dep_keys,
                "agent_config": agent_info.get("config", {}),
            }

        await db.commit()

        # 3. Topological execution loop
        pending: Set[str] = set(steps.keys())
        completed: Set[str] = set()
        skipped: List[str] = []
        agent_calls = 0

        while pending:
            # Find ready steps (all deps completed)
            ready = [
                sk for sk in pending
                if all(d in completed for d in steps[sk]["depends_on"])
            ]

            if not ready:
                # Deadlock: pending steps have failed/skipped dependencies
                for sk in pending:
                    await employee_repo.update_step(
                        db,
                        await employee_repo.get_step(db, steps[sk]["step_id"]),
                        status="skipped",
                        error={"reason": "dependency_failed"},
                    )
                    skipped.append(sk)
                pending.clear()
                break

            # Execute ready steps in parallel
            coros = []
            for sk in ready:
                agent_calls += 1
                if agent_calls > max_calls:
                    raise RuntimeError(f"max_agent_calls exceeded ({max_calls})")

                step_info = steps[sk]
                step_timeout_val = step_info["agent_config"].get(
                    "timeout_seconds", step_timeout)
                max_retries_val = step_info["agent_config"].get(
                    "max_retries", max_retries)

                coros.append(self._execute_step(
                    db, task, ctx, sk, step_info,
                    step_timeout_val, max_retries_val,
                ))

            results = await asyncio.gather(*coros, return_exceptions=True)

            for sk, result in zip(ready, results):
                pending.discard(sk)
                if isinstance(result, StepFailed):
                    skipped.extend(self._mark_downstream_skipped(
                        db, steps, sk, pending, skipped))
                    if fail_fast:
                        raise RuntimeError(
                            f"fail_fast: step '{sk}' failed: {result}")
                    # else: continue, mark as failed
                else:
                    completed.add(sk)

        # Persist final context
        await employee_repo.update_task(db, task, context=ctx.to_dict())
        await db.commit()

        return await self.aggregator.aggregate(ctx, snapshot, skipped_steps=skipped)

    async def _execute_step(
        self,
        db: AsyncSession,
        task,
        ctx: EmployeeContext,
        step_key: str,
        step_info: dict,
        timeout: int,
        max_retries: int,
    ) -> dict:
        """Execute a single step with retry logic."""
        step_id = step_info["step_id"]
        agent_id = step_info["agent_id"]
        role = step_info.get("role")

        # Get upstream outputs
        upstream_keys = step_info["depends_on"]
        upstream_outputs = ctx.get_upstream_outputs(upstream_keys)

        # Render instruction
        instruction = render_instruction(
            task_input=task.input or {},
            step_role=role,
            upstream_outputs=upstream_outputs,
        )

        # Update step: running
        step = await employee_repo.get_step(db, step_id)
        await employee_repo.update_step(
            db, step,
            status="running",
            started_at=datetime.now(timezone.utc),
            input={"instruction": instruction[:500], "upstream_keys": upstream_keys},
        )
        await db.commit()

        # Retry loop
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

                # Success
                await employee_repo.update_step(
                    db, step,
                    status="completed",
                    output=result,
                    trace_id=result.get("metadata", {}).get("trace_id"),
                    retry_count=attempt,
                    completed_at=datetime.now(timezone.utc),
                )
                await db.commit()

                # Update context
                ctx.add_artifact(step_key, result)

                logger.info(
                    f"Step '{step_key}' completed "
                    f"(attempt={attempt}, trace={result.get('metadata', {}).get('trace_id')})"
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"Step '{step_key}' timed out (attempt={attempt}, timeout={timeout}s)"
                )
                if attempt < max_retries:
                    continue
                await employee_repo.update_step(
                    db, step,
                    status="failed",
                    error={"code": "timeout", "message": f"Timed out after {timeout}s"},
                    retry_count=attempt,
                    completed_at=datetime.now(timezone.utc),
                )
                await db.commit()
                raise StepFailed(step_key, f"Timeout after {timeout}s")

            except Exception as e:
                logger.warning(
                    f"Step '{step_key}' error (attempt={attempt}): {e}"
                )
                if attempt < max_retries:
                    continue
                await employee_repo.update_step(
                    db, step,
                    status="failed",
                    error={"code": "step_error", "message": str(e)[:500]},
                    retry_count=attempt,
                    completed_at=datetime.now(timezone.utc),
                )
                await db.commit()
                raise StepFailed(step_key, str(e))

    def _mark_downstream_skipped(
        self,
        db: AsyncSession,
        steps: Dict[str, dict],
        failed_key: str,
        pending: Set[str],
        skipped: List[str],
    ) -> List[str]:
        """Mark all downstream steps of a failed step as skipped."""
        # Find all steps that transitively depend on failed_key
        to_skip = set()
        changed = True
        while changed:
            changed = False
            for sk in pending:
                if sk in to_skip or sk == failed_key:
                    continue
                deps = steps[sk]["depends_on"]
                if any(d in to_skip or d == failed_key for d in deps):
                    to_skip.add(sk)
                    changed = True

        for sk in to_skip:
            if sk not in skipped:
                skipped.append(sk)
            pending.discard(sk)

        return list(to_skip)
