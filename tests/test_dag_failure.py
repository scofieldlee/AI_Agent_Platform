"""
Unit tests for DAG failure handling (design doc §9.2 scenario 4).

Scenario: Agent B fails -> retry 1 time -> still fails -> downstream steps
skipped -> Task result marked partial=True.

Tests cover:
- _mark_downstream_skipped cascading skip logic
- _execute_step retry + StepFailed on exhaustion
- DagScheduler.run full flow with a failing middle step
- fail_fast=True raises RuntimeError immediately
- Aggregator marks partial=True when skipped_steps non-empty

Run: .venv/bin/python -m pytest tests/test_dag_failure.py -v
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.employee.runtime.dag_scheduler import DagScheduler, StepFailed
from app.employee.runtime.context import EmployeeContext
from app.employee.runtime.aggregator import ResultAggregator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(agents, config=None):
    """Build a snapshot dict for DagScheduler."""
    return {
        "mode": "dag",
        "employee_name": "TestEmployee",
        "agents": agents,
        "config": config or {},
    }


def _make_task(task_id=1, input_data=None):
    """Build a mock task object."""
    task = MagicMock()
    task.id = task_id
    task.input = input_data or {"message": "test task"}
    task.user_id = 1
    task.tenant_id = None
    task.title = "Test Task"
    return task


def _make_async_db():
    """Build a mock AsyncSession with async commit/flush."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Tests: _mark_downstream_skipped (pure graph logic)
# ---------------------------------------------------------------------------

def test_skip_direct_downstream():
    """A -> B -> C: failing A should skip B and C."""
    scheduler = DagScheduler()
    steps = {
        "agent_1": {"depends_on": []},
        "agent_2": {"depends_on": ["agent_1"]},
        "agent_3": {"depends_on": ["agent_2"]},
    }
    pending = {"agent_2", "agent_3"}  # agent_1 already removed
    skipped = []

    to_skip = scheduler._mark_downstream_skipped(
        MagicMock(), steps, "agent_1", pending, skipped)

    assert set(to_skip) == {"agent_2", "agent_3"}
    assert set(skipped) == {"agent_2", "agent_3"}
    assert pending == set()


def test_skip_branch_only():
    """A -> B, A -> C, B -> D: failing B should skip only D, not C."""
    scheduler = DagScheduler()
    steps = {
        "agent_1": {"depends_on": []},
        "agent_2": {"depends_on": ["agent_1"]},
        "agent_3": {"depends_on": ["agent_1"]},
        "agent_4": {"depends_on": ["agent_2"]},
    }
    pending = {"agent_4"}  # agent_2 failed, agent_3 is independent
    skipped = []

    to_skip = scheduler._mark_downstream_skipped(
        MagicMock(), steps, "agent_2", pending, skipped)

    assert to_skip == ["agent_4"]
    assert "agent_3" not in to_skip


def test_skip_diamond_dependency():
    """Diamond: A -> B, A -> C, B -> D, C -> D: failing B skips D."""
    scheduler = DagScheduler()
    steps = {
        "agent_1": {"depends_on": []},
        "agent_2": {"depends_on": ["agent_1"]},
        "agent_3": {"depends_on": ["agent_1"]},
        "agent_4": {"depends_on": ["agent_2", "agent_3"]},
    }
    pending = {"agent_4"}
    skipped = []

    to_skip = scheduler._mark_downstream_skipped(
        MagicMock(), steps, "agent_2", pending, skipped)

    assert to_skip == ["agent_4"]


# ---------------------------------------------------------------------------
# Tests: _execute_step retry logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_retry_then_success():
    """Step fails on attempt 0, succeeds on attempt 1 (retry)."""
    scheduler = DagScheduler()
    ctx = EmployeeContext(task_id=1)
    task = _make_task()

    step_info = {
        "step_id": 10,
        "agent_id": 2,
        "role": "分析",
        "depends_on": [],
        "agent_config": {"max_retries": 1, "timeout_seconds": 30},
    }

    # Mock dispatcher: fail first, succeed second
    call_count = 0

    async def mock_execute(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("transient failure")
        return {
            "success": True,
            "summary": "done on retry",
            "data": {},
            "metadata": {"trace_id": "trace-retry-001"},
        }

    scheduler.dispatcher.execute = mock_execute

    # Mock DB calls
    with patch("app.employee.runtime.dag_scheduler.employee_repo") as mock_repo:
        mock_step = MagicMock()
        mock_step.id = 10
        mock_repo.get_step = AsyncMock(return_value=mock_step)
        mock_repo.update_step = AsyncMock()

        result = await scheduler._execute_step(
            _make_async_db(), task, ctx, "agent_2", step_info,
            timeout=30, max_retries=1,
        )

    assert result["success"] is True
    assert call_count == 2  # 1 initial + 1 retry
    assert ctx.artifacts["agent_2"]["success"] is True


@pytest.mark.asyncio
async def test_step_retry_exhausted_raises_step_failed():
    """Step fails on all retry attempts -> StepFailed raised."""
    scheduler = DagScheduler()
    ctx = EmployeeContext(task_id=1)
    task = _make_task()

    step_info = {
        "step_id": 10,
        "agent_id": 2,
        "role": "分析",
        "depends_on": [],
        "agent_config": {"max_retries": 1},
    }

    call_count = 0

    async def mock_execute(**kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("permanent failure")

    scheduler.dispatcher.execute = mock_execute

    with patch("app.employee.runtime.dag_scheduler.employee_repo") as mock_repo:
        mock_step = MagicMock()
        mock_repo.get_step = AsyncMock(return_value=mock_step)
        mock_repo.update_step = AsyncMock()

        try:
            await scheduler._execute_step(
                _make_async_db(), task, ctx, "agent_2", step_info,
                timeout=30, max_retries=1,
            )
            assert False, "should have raised StepFailed"
        except StepFailed as e:
            assert e.step_key == "agent_2"
            assert "permanent failure" in str(e)

    assert call_count == 2  # 1 initial + 1 retry


# ---------------------------------------------------------------------------
# Tests: DagScheduler.run full flow with failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dag_run_with_middle_failure_marks_partial():
    """3-step chain A -> B -> C: B fails -> C skipped -> result partial=True.

    This is §9.2 scenario 4.
    """
    scheduler = DagScheduler()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)

    snapshot = _make_snapshot([
        {"agent_id": 1, "role": "分析", "depends_on": [], "config": {}},
        {"agent_id": 2, "role": "生成", "depends_on": [1], "config": {}},
        {"agent_id": 3, "role": "审核", "depends_on": [2], "config": {}},
    ], config={"max_retries": 0, "step_timeout_seconds": 10})

    call_log = []

    async def mock_execute(agent_id, **kwargs):
        call_log.append(agent_id)
        if agent_id == 2:
            raise RuntimeError("Agent B is broken")
        return {
            "success": True,
            "summary": f"Agent {agent_id} completed",
            "data": {},
            "metadata": {"trace_id": f"trace-{agent_id}"},
        }

    scheduler.dispatcher.execute = mock_execute

    # Mock DB
    step_counter = [0]

    async def mock_create_step(db, **kwargs):
        step_counter[0] += 1
        mock = MagicMock()
        mock.id = step_counter[0]
        mock.step_key = kwargs.get("step_key")
        mock.agent_id = kwargs.get("agent_id")
        mock.status = "pending"
        return mock

    with patch("app.employee.runtime.dag_scheduler.employee_repo") as mock_repo:
        mock_repo.create_step = mock_create_step
        mock_repo.get_step = AsyncMock(return_value=MagicMock())
        mock_repo.update_step = AsyncMock()
        mock_repo.update_task = AsyncMock()

        result = await scheduler.run(_make_async_db(), task, ctx, snapshot)

    # Agent 1 succeeded, Agent 2 failed, Agent 3 never called
    assert 1 in call_log
    assert 2 in call_log
    assert 3 not in call_log

    # Result should be partial
    assert result["partial"] is True
    assert "agent_3" in result.get("skipped_steps", [])


@pytest.mark.asyncio
async def test_dag_run_fail_fast_raises():
    """With fail_fast=True, first failure immediately raises RuntimeError."""
    scheduler = DagScheduler()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)

    snapshot = _make_snapshot([
        {"agent_id": 1, "role": "分析", "depends_on": [], "config": {}},
        {"agent_id": 2, "role": "生成", "depends_on": [1], "config": {}},
    ], config={"max_retries": 0, "fail_fast": True})

    async def mock_execute(agent_id, **kwargs):
        if agent_id == 1:
            raise RuntimeError("Agent A broken")
        return {"success": True, "summary": "ok", "data": {}, "metadata": {}}

    scheduler.dispatcher.execute = mock_execute

    step_counter = [0]

    async def mock_create_step(db, **kwargs):
        step_counter[0] += 1
        mock = MagicMock()
        mock.id = step_counter[0]
        return mock

    with patch("app.employee.runtime.dag_scheduler.employee_repo") as mock_repo:
        mock_repo.create_step = mock_create_step
        mock_repo.get_step = AsyncMock(return_value=MagicMock())
        mock_repo.update_step = AsyncMock()
        mock_repo.update_task = AsyncMock()

        try:
            await scheduler.run(_make_async_db(), task, ctx, snapshot)
            assert False, "should have raised"
        except RuntimeError as e:
            assert "fail_fast" in str(e)


# ---------------------------------------------------------------------------
# Tests: Aggregator partial flag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregator_partial_flag():
    """Aggregator correctly sets partial=True when skipped_steps provided."""
    agg = ResultAggregator()
    ctx = EmployeeContext(task_id=1)
    ctx.add_artifact("agent_1", {
        "success": True,
        "summary": "Step 1 done",
        "data": {},
        "metadata": {"trace_id": "t1"},
    })

    snapshot = {"config": {}}  # no LLM summarize

    result = await agg.aggregate(ctx, snapshot, skipped_steps=["agent_2"])

    assert result["partial"] is True
    assert result["skipped_steps"] == ["agent_2"]
    assert "Step 1 done" in result["summary"]


@pytest.mark.asyncio
async def test_aggregator_no_partial_when_all_succeed():
    """Aggregator sets partial=False when no skipped steps."""
    agg = ResultAggregator()
    ctx = EmployeeContext(task_id=1)
    ctx.add_artifact("agent_1", {
        "success": True, "summary": "done", "data": {}, "metadata": {},
    })

    result = await agg.aggregate(ctx, {"config": {}}, skipped_steps=[])

    assert result["partial"] is False
    assert "skipped_steps" not in result


if __name__ == "__main__":
    # Simple runner for environments without pytest
    import inspect

    async def run_async(test_fn):
        return await test_fn()

    fails = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ):
        try:
            if inspect.iscoroutinefunction(fn):
                asyncio.run(run_async(fn))
            else:
                fn()
            print(f"PASS {name}")
        except Exception as e:
            fails += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
