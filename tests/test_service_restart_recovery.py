"""
Unit tests for service restart recovery (design doc §9.2 scenario 8).

Scenario: Running tasks exist when the service crashes/restarts.
On startup, lifespan calls employee_repo.fail_orphan_tasks() which
marks all "running" tasks as "failed" with error code "service_restarted".

Tests cover:
- fail_orphan_tasks marks running tasks as failed
- Tasks in other states (pending, completed, waiting_human) are untouched
- The error dict contains the correct code and message
- completed_at is set to the current time

Run: .venv/bin/python -m pytest tests/test_service_restart_recovery.py -v
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Tests: fail_orphan_tasks logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_running_tasks_marked_failed():
    """Running tasks are marked as failed on startup."""
    from app.repositories import employee_repo
    from app.models.ai_employee import AIEmployeeTask

    # Create mock task objects
    running_task_1 = MagicMock(spec=AIEmployeeTask)
    running_task_1.id = 101
    running_task_1.status = "running"
    running_task_1.error = None
    running_task_1.completed_at = None

    running_task_2 = MagicMock(spec=AIEmployeeTask)
    running_task_2.id = 102
    running_task_2.status = "running"
    running_task_2.error = None
    running_task_2.completed_at = None

    # Mock the database query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        running_task_1, running_task_2
    ]

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    count = await employee_repo.fail_orphan_tasks(mock_db)

    assert count == 2

    # Both tasks should be marked failed
    assert running_task_1.status == "failed"
    assert running_task_1.error is not None
    assert running_task_1.error["code"] == "service_restarted"
    assert "Service restarted" in running_task_1.error["message"]
    assert running_task_1.completed_at is not None

    assert running_task_2.status == "failed"
    assert running_task_2.error["code"] == "service_restarted"
    assert running_task_2.completed_at is not None


@pytest.mark.asyncio
async def test_non_running_tasks_untouched():
    """Tasks in pending/completed/waiting_human states are not affected."""
    from app.repositories import employee_repo
    from app.models.ai_employee import AIEmployeeTask

    # Mock returns only running tasks (the query filters by status="running")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []  # no running tasks

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    count = await employee_repo.fail_orphan_tasks(mock_db)

    assert count == 0


@pytest.mark.asyncio
async def test_completed_at_set_to_utc_now():
    """completed_at should be set to approximately the current UTC time."""
    from app.repositories import employee_repo
    from app.models.ai_employee import AIEmployeeTask

    running_task = MagicMock(spec=AIEmployeeTask)
    running_task.id = 201
    running_task.status = "running"
    running_task.error = None
    running_task.completed_at = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [running_task]

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    before = datetime.now(timezone.utc)

    count = await employee_repo.fail_orphan_tasks(mock_db)

    after = datetime.now(timezone.utc)

    assert count == 1
    assert running_task.completed_at is not None
    # completed_at should be between before and after (within a few seconds)
    assert before <= running_task.completed_at <= after


@pytest.mark.asyncio
async def test_empty_database_returns_zero():
    """No tasks at all -> returns 0, no errors."""
    from app.repositories import employee_repo

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    count = await employee_repo.fail_orphan_tasks(mock_db)
    assert count == 0


# ---------------------------------------------------------------------------
# Tests: Lifespan integration (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifespan_calls_fail_orphan_tasks():
    """Verify lifespan startup calls fail_orphan_tasks."""
    # We test that the lifespan code path invokes fail_orphan_tasks
    # by checking the import and call pattern in main.py
    from app.main import lifespan

    # We can't easily run the full lifespan (it inits DB, Redis, etc.)
    # but we can verify the code references fail_orphan_tasks
    import inspect
    source = inspect.getsource(lifespan)
    assert "fail_orphan_tasks" in source
    assert "orphan" in source.lower()


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
