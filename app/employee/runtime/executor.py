"""
EmployeeRuntime: the top-level orchestrator for AI Employee tasks.

Entry point: run_task(task_id) — called via asyncio.create_task from the API layer.

Routes to DagScheduler (DAG mode) or SupervisorLoop (Supervisor mode).
Does NOT use LangGraph — Agent-internal graph execution is handled by
AgentRuntime. EmployeeRuntime only manages Agent-to-Agent orchestration.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import async_session_factory
from app.repositories import employee_repo
from app.employee.runtime.context import EmployeeContext
from app.employee.runtime.dag_scheduler import DagScheduler
from app.employee.runtime.aggregator import ResultAggregator
from app.employee.runtime.exceptions import (
    HumanInterventionRequired,
    SupervisorOutputError,
    TaskCancelled,
)

# Backward-compatible re-exports (these were previously defined here)
__all__ = [
    "EmployeeRuntime",
    "HumanInterventionRequired",
    "TaskCancelled",
    "SupervisorOutputError",
]

logger = logging.getLogger(__name__)


class EmployeeRuntime:
    """Top-level orchestrator for AI Employee task execution."""

    def __init__(self):
        self.dag = DagScheduler()
        self.aggregator = ResultAggregator()
        # Supervisor loop loaded lazily (Phase 4)
        self._supervisor = None

    @property
    def supervisor(self):
        if self._supervisor is None:
            from app.employee.runtime.supervisor import SupervisorLoop
            self._supervisor = SupervisorLoop()
        return self._supervisor

    async def run_task(self, task_id: int) -> None:
        """Background execution of a task (called via asyncio.create_task).

        Flow:
        1. Load task + snapshot
        2. Mark as running
        3. Route to DAG or Supervisor based on snapshot mode
        4. Mark completed/failed/cancelled/waiting_human
        """
        async with async_session_factory() as db:
            task = await employee_repo.get_task(db, task_id)
            if not task:
                logger.error(f"Task {task_id} not found")
                return

            snapshot = task.employee_snapshot or {}
            mode = snapshot.get("mode", "dag")
            ctx = EmployeeContext.from_task(task)

            try:
                # Mark as running
                await employee_repo.update_task(
                    db, task,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                await db.commit()

                logger.info(
                    f"EmployeeTask {task_id} started "
                    f"(mode={mode}, employee={snapshot.get('employee_name')})"
                )

                # Route to scheduler
                if mode == "supervisor":
                    final = await self.supervisor.run(db, task, ctx, snapshot)
                else:
                    final = await self.dag.run(db, task, ctx, snapshot)

                # Mark completed
                await employee_repo.update_task(
                    db, task,
                    status="completed",
                    result=final,
                    completed_at=datetime.now(timezone.utc),
                )
                await db.commit()

                logger.info(
                    f"EmployeeTask {task_id} completed "
                    f"(steps={len(ctx.artifacts)})"
                )

            except asyncio.CancelledError:
                # Task was cancelled by user
                await employee_repo.update_task(
                    db, task,
                    status="cancelled",
                    completed_at=datetime.now(timezone.utc),
                    context=ctx.to_dict(),
                )
                await db.commit()
                logger.info(f"EmployeeTask {task_id} cancelled")

            except HumanInterventionRequired as e:
                await employee_repo.update_task(
                    db, task,
                    status="waiting_human",
                    error={"reason": str(e)},
                    context=ctx.to_dict(),
                )
                await db.commit()
                logger.info(f"EmployeeTask {task_id} waiting for human: {e}")

            except SupervisorOutputError as e:
                # Supervisor JSON contract violated after retry — fail
                # explicitly, never silently continue (design doc §4.3.4)
                await employee_repo.update_task(
                    db, task,
                    status="failed",
                    error={
                        "code": "supervisor_invalid_output",
                        "message": str(e)[:1000],
                    },
                    completed_at=datetime.now(timezone.utc),
                    context=ctx.to_dict(),
                )
                await db.commit()
                logger.error(
                    f"EmployeeTask {task_id} failed: "
                    f"supervisor_invalid_output: {e}"
                )

            except Exception as e:
                logger.exception(f"EmployeeTask {task_id} failed: {e}")
                await employee_repo.update_task(
                    db, task,
                    status="failed",
                    error={
                        "code": "runtime_error",
                        "message": str(e)[:1000],
                    },
                    completed_at=datetime.now(timezone.utc),
                    context=ctx.to_dict(),
                )
                await db.commit()
