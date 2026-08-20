"""
Unit tests for Supervisor loop protection (design doc §9.2 scenario 7).

Scenario: Construct a "never finish" supervisor that always dispatches
agents. Verify that max_rounds and max_agent_calls both terminate the
loop, producing a RuntimeError (caught by EmployeeRuntime -> task failed).

Tests cover:
- max_rounds exceeded -> RuntimeError("supervisor_max_rounds exceeded")
- max_agent_calls exceeded -> RuntimeError("max_agent_calls exceeded")
- Budget continuation on resume (decisions from prior rounds count)
- HumanInterventionRequired properly raised
- SupervisorOutputError after 2 failed parse attempts

Run: .venv/bin/python -m pytest tests/test_supervisor_loop_protection.py -v
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.employee.runtime.supervisor import SupervisorLoop, parse_decision
from app.employee.runtime.context import EmployeeContext
from app.employee.runtime.exceptions import (
    HumanInterventionRequired,
    SupervisorOutputError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(config=None, agents=None, supervisor_agent_id=8):
    """Build a snapshot for SupervisorLoop."""
    return {
        "mode": "supervisor",
        "employee_name": "TestSupervisor",
        "role_prompt": "You are a test supervisor",
        "supervisor_agent_id": supervisor_agent_id,
        "agents": agents or [
            {"agent_id": 2, "name": "Agent A", "role": "分析",
             "description": "does analysis", "config": {}},
            {"agent_id": 7, "name": "Agent B", "role": "生成",
             "description": "generates content", "config": {}},
        ],
        "config": config or {},
    }


def _make_task(task_id=1, input_data=None):
    """Build a mock task object."""
    task = MagicMock()
    task.id = task_id
    task.input = input_data or {"message": "do something repeatedly"}
    task.user_id = 1
    task.tenant_id = None
    task.title = "Loop Test"
    return task


def _make_async_db():
    """Build a mock AsyncSession with async commit/flush."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _make_dispatch_mock(supervisor_agent_id=8, decision_json=None, team_response=None):
    """Create a mock dispatcher.execute that distinguishes supervisor vs team agents.

    - supervisor_agent_id: returns a JSON decision string
    - other agent_ids: returns a normal team agent result
    """
    default_decision = decision_json or (
        '{"action": "dispatch_agent", "agent_id": 2, "reason": "always dispatch", "input": {}}'
    )
    default_team = team_response or {
        "success": True,
        "summary": "team agent done",
        "data": {},
        "metadata": {"trace_id": "team-trace"},
    }

    async def mock_execute(agent_id, **kwargs):
        if agent_id == supervisor_agent_id:
            return {
                "success": True,
                "summary": f"```json\n{default_decision}\n```",
                "data": {},
                "metadata": {},
            }
        return dict(default_team)

    return mock_execute


# ---------------------------------------------------------------------------
# Tests: max_rounds termination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_rounds_exceeded():
    """Supervisor always dispatches -> hits max_rounds limit -> RuntimeError."""
    loop = SupervisorLoop()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)

    # Very low limits for fast testing
    snapshot = _make_snapshot(config={
        "supervisor_max_rounds": 3,
        "max_agent_calls": 100,  # high so rounds trigger first
        "step_timeout_seconds": 5,
        "max_retries": 0,
    })

    call_count = [0]

    async def mock_dispatch_execute(agent_id, **kwargs):
        call_count[0] += 1
        if agent_id == 8:  # supervisor
            return {
                "success": True,
                "summary": '```json\n{"action": "dispatch_agent", "agent_id": 2, "reason": "always dispatch", "input": {}}\n```',
                "data": {},
                "metadata": {},
            }
        return {
            "success": True,
            "summary": f"agent {agent_id} output",
            "data": {},
            "metadata": {"trace_id": f"t-{call_count[0]}"},
        }

    loop.dispatcher.execute = mock_dispatch_execute

    # Mock DB
    step_counter = [0]

    async def mock_create_step(db, **kwargs):
        step_counter[0] += 1
        mock = MagicMock()
        mock.id = step_counter[0]
        mock.step_key = kwargs.get("step_key")
        return mock

    with patch("app.employee.runtime.supervisor.employee_repo") as mock_repo:
        mock_repo.create_step = mock_create_step
        mock_repo.update_step = AsyncMock()
        mock_repo.update_task = AsyncMock()

        try:
            await loop.run(_make_async_db(), task, ctx, snapshot)
            assert False, "should have raised RuntimeError"
        except RuntimeError as e:
            assert "supervisor_max_rounds exceeded" in str(e)
            assert "3" in str(e)

    # Should have run exactly 3 rounds (1 dispatch per round)
    assert len(ctx.decisions) == 3


# ---------------------------------------------------------------------------
# Tests: max_agent_calls termination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_agent_calls_exceeded():
    """Supervisor dispatches 2 agents per round -> hits max_calls before rounds."""
    loop = SupervisorLoop()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)

    snapshot = _make_snapshot(config={
        "supervisor_max_rounds": 100,  # high so calls trigger first
        "max_agent_calls": 3,  # very low
        "step_timeout_seconds": 5,
        "max_retries": 0,
    })

    async def mock_dispatch_execute(agent_id, **kwargs):
        if agent_id == 8:  # supervisor: always dispatch_parallel with 2 agents
            return {
                "success": True,
                "summary": '```json\n{"action": "dispatch_parallel", "agents": [{"agent_id": 2, "input": {}}, {"agent_id": 7, "input": {}}], "reason": "parallel"}\n```',
                "data": {},
                "metadata": {},
            }
        return {
            "success": True,
            "summary": f"agent {agent_id} done",
            "data": {},
            "metadata": {"trace_id": f"t-{agent_id}"},
        }

    loop.dispatcher.execute = mock_dispatch_execute

    step_counter = [0]

    async def mock_create_step(db, **kwargs):
        step_counter[0] += 1
        mock = MagicMock()
        mock.id = step_counter[0]
        mock.step_key = kwargs.get("step_key")
        return mock

    with patch("app.employee.runtime.supervisor.employee_repo") as mock_repo:
        mock_repo.create_step = mock_create_step
        mock_repo.update_step = AsyncMock()
        mock_repo.update_task = AsyncMock()

        try:
            await loop.run(_make_async_db(), task, ctx, snapshot)
            assert False, "should have raised RuntimeError"
        except RuntimeError as e:
            assert "max_agent_calls exceeded" in str(e)
            assert "3" in str(e)


# ---------------------------------------------------------------------------
# Tests: Budget continuation on resume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_budget_continuation():
    """On resume, prior decisions count toward max_rounds and max_calls."""
    loop = SupervisorLoop()
    task = _make_task()
    # Pre-populate context with 2 prior rounds (2 dispatches each = 4 calls)
    ctx = EmployeeContext(
        task_id=1,
        decisions=[
            {"round": 1, "action": "dispatch_parallel", "dispatched": 2},
            {"round": 2, "action": "dispatch_parallel", "dispatched": 2},
        ],
    )

    snapshot = _make_snapshot(config={
        "supervisor_max_rounds": 4,  # only 2 more rounds allowed (prior=2)
        "max_agent_calls": 20,  # high enough so rounds trigger first
        "step_timeout_seconds": 5,
        "max_retries": 0,
    })

    async def mock_execute(agent_id, **kwargs):
        if agent_id == 8:  # supervisor: dispatch_parallel 2 agents
            return {
                "success": True,
                "summary": '```json\n{"action": "dispatch_parallel", "agents": [{"agent_id": 2, "input": {}}, {"agent_id": 7, "input": {}}], "reason": "parallel"}\n```',
                "data": {},
                "metadata": {},
            }
        return {
            "success": True,
            "summary": f"agent {agent_id} done",
            "data": {},
            "metadata": {},
        }

    loop.dispatcher.execute = mock_execute

    step_counter = [0]

    async def mock_create_step(db, **kwargs):
        step_counter[0] += 1
        mock = MagicMock()
        mock.id = step_counter[0]
        mock.step_key = kwargs.get("step_key")
        return mock

    with patch("app.employee.runtime.supervisor.employee_repo") as mock_repo:
        mock_repo.create_step = mock_create_step
        mock_repo.update_step = AsyncMock()
        mock_repo.update_task = AsyncMock()

        try:
            await loop.run(_make_async_db(), task, ctx, snapshot)
            assert False, "should hit max_rounds"
        except RuntimeError as e:
            # Should hit max_rounds=4 after 2 more rounds (rounds 3 and 4)
            assert "max_rounds" in str(e)

    # Total decisions = 2 prior + 2 new = 4
    assert len(ctx.decisions) == 4


# ---------------------------------------------------------------------------
# Tests: SupervisorOutputError after retry exhaustion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supervisor_output_error_after_retry():
    """Supervisor agent returns garbage twice -> SupervisorOutputError."""
    loop = SupervisorLoop()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)

    snapshot = _make_snapshot(config={
        "supervisor_max_rounds": 5,
        "max_agent_calls": 10,
    })

    call_count = [0]

    async def mock_execute(agent_id, **kwargs):
        call_count[0] += 1
        # Supervisor agent "succeeds" but returns unparseable text
        return {
            "success": True,
            "summary": "I cannot decide. Please help me.",  # no JSON
            "data": {},
            "metadata": {},
        }

    loop.dispatcher.execute = mock_execute

    with patch("app.employee.runtime.supervisor.employee_repo") as mock_repo:
        mock_repo.update_task = AsyncMock()

        try:
            await loop.run(MagicMock(), task, ctx, snapshot)
            assert False, "should raise SupervisorOutputError"
        except SupervisorOutputError as e:
            assert "supervisor_invalid_output" in str(e)

    # 1 initial attempt + 1 retry = 2 calls
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# Tests: HumanInterventionRequired
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_intervention_raised():
    """Supervisor decides human_intervention -> HumanInterventionRequired."""
    loop = SupervisorLoop()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)

    snapshot = _make_snapshot()

    async def mock_execute(agent_id, **kwargs):
        return {
            "success": True,
            "summary": '```json\n{"action": "human_intervention", "reason": "need user authorization"}\n```',
            "data": {},
            "metadata": {},
        }

    loop.dispatcher.execute = mock_execute

    with patch("app.employee.runtime.supervisor.employee_repo") as mock_repo:
        mock_repo.update_task = AsyncMock()
        # Mock HumanCenterService
        with patch(
            "app.human_center.service.HumanCenterService.create_task",
            new_callable=AsyncMock,
        ):
            try:
                await loop.run(_make_async_db(), task, ctx, snapshot)
                assert False, "should raise HumanInterventionRequired"
            except HumanInterventionRequired as e:
                assert "need user authorization" in str(e)

    assert len(ctx.decisions) == 1
    assert ctx.decisions[0]["action"] == "human_intervention"


# ---------------------------------------------------------------------------
# Tests: Finish action produces correct result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finish_action_returns_result():
    """Supervisor decides finish -> aggregated result with supervisor summary."""
    loop = SupervisorLoop()
    task = _make_task()
    ctx = EmployeeContext(task_id=1)
    # Pre-populate one artifact from a prior dispatch
    ctx.add_artifact("round1_agent2", {
        "success": True,
        "summary": "Analysis complete",
        "data": {},
        "metadata": {"trace_id": "t1"},
    })

    snapshot = _make_snapshot()

    async def mock_execute(agent_id, **kwargs):
        return {
            "success": True,
            "summary": '```json\n{"action": "finish", "result": {"summary": "All done: analysis completed successfully"}}\n```',
            "data": {},
            "metadata": {},
        }

    loop.dispatcher.execute = mock_execute

    with patch("app.employee.runtime.supervisor.employee_repo") as mock_repo:
        mock_repo.update_task = AsyncMock()

        result = await loop.run(_make_async_db(), task, ctx, snapshot)

    assert result["supervisor_finished"] is True
    assert "All done" in result["summary"]
    assert result["partial"] is False


if __name__ == "__main__":
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
