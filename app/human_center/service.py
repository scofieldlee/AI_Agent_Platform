"""
HumanCenter Service: manages human-in-the-loop customer service tasks.

When the AI agent cannot handle a request, it creates a HumanTask (ticket).
This service handles task creation, assignment, resolution, and querying.
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import select, func, and_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import async_session_factory
from app.models.human_task import HumanTask

logger = logging.getLogger(__name__)


class HumanCenterService:
    """Service for managing human customer service tasks."""

    # Priority mapping based on transfer reason
    PRIORITY_MAP = {
        "complaint": "urgent",
        "system_error": "high",
        "llm_error": "high",
        "knowledge_missing": "normal",
        "low_confidence": "normal",
        "user_request": "normal",
    }

    # Transfer reason labels (for display)
    REASON_LABELS = {
        "low_confidence": "AI 置信度不足",
        "knowledge_missing": "知识库缺失",
        "complaint": "顾客投诉",
        "llm_error": "AI 服务异常",
        "system_error": "系统错误",
        "user_request": "顾客主动请求",
    }

    # Status labels
    STATUS_LABELS = {
        "pending": "待处理",
        "assigned": "处理中",
        "resolved": "已解决",
        "closed": "已关闭",
    }

    # Priority labels
    PRIORITY_LABELS = {
        "low": "低",
        "normal": "普通",
        "high": "高",
        "urgent": "紧急",
    }

    async def create_task(
        self,
        conversation_id: Optional[int],
        agent_id: Optional[int],
        user_id: Optional[int],
        user_message: str,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        transfer_reason: str = "low_confidence",
        trace_id: Optional[str] = None,
        agent_answer: str = "",
        extra_context: Optional[Dict] = None,
    ) -> HumanTask:
        """Create a new human task when the AI agent transfers to human.

        Args:
            conversation_id: Related conversation ID.
            agent_id: The AI agent that triggered the transfer.
            user_id: The user who sent the message.
            user_message: The user's original message.
            intent: Classified intent (complaint, order_query, etc.).
            confidence: AI confidence score (0.0-1.0).
            transfer_reason: Why the transfer happened.
            trace_id: Analytics trace ID for correlation.
            agent_answer: What the AI said before transferring.
            extra_context: Additional context (knowledge_sources, tool_results, etc.)

        Returns:
            The created HumanTask instance.
        """
        ticket_number = await self._generate_ticket_number()
        priority = self.PRIORITY_MAP.get(transfer_reason, "normal")

        meta = {
            "agent_answer": agent_answer[:500] if agent_answer else "",
        }
        if extra_context:
            meta.update(extra_context)

        task = HumanTask(
            ticket_number=ticket_number,
            conversation_id=conversation_id,
            agent_id=agent_id,
            user_id=user_id,
            trace_id=trace_id,
            user_message=user_message,
            intent=intent,
            confidence=confidence,
            transfer_reason=transfer_reason,
            status="pending",
            priority=priority,
            meta=meta,
        )

        async with async_session_factory() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)

        logger.info(
            f"Human task created | ticket={ticket_number} | "
            f"reason={transfer_reason} | priority={priority} | "
            f"conversation={conversation_id} | intent={intent}"
        )

        return task

    async def assign_task(
        self,
        task_id: int,
        assigned_to: int,
    ) -> Optional[HumanTask]:
        """Assign a task to a human agent.

        Args:
            task_id: The task ID to assign.
            assigned_to: The human agent/staff ID.

        Returns:
            Updated HumanTask or None if not found.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(HumanTask).where(HumanTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            task.assigned_to = assigned_to
            task.status = "assigned"
            task.assigned_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(task)

        logger.info(
            f"Human task assigned | ticket={task.ticket_number} | "
            f"assigned_to={assigned_to}"
        )
        return task

    async def resolve_task(
        self,
        task_id: int,
        resolution_note: str,
        resolution_type: str = "resolved",
        assigned_to: Optional[int] = None,
    ) -> Optional[HumanTask]:
        """Resolve a human task.

        Args:
            task_id: The task ID to resolve.
            resolution_note: What the human agent did to resolve the issue.
            resolution_type: resolved, cannot_resolve, redirected, duplicate.
            assigned_to: Staff ID (auto-assign if task was pending).

        Returns:
            Updated HumanTask or None if not found.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(HumanTask).where(HumanTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            # Auto-assign if was pending
            if task.status == "pending" and assigned_to:
                task.assigned_to = assigned_to
                task.assigned_at = datetime.now(timezone.utc)

            task.resolution_note = resolution_note
            task.resolution_type = resolution_type
            task.status = "resolved"
            task.resolved_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(task)

        logger.info(
            f"Human task resolved | ticket={task.ticket_number} | "
            f"type={resolution_type}"
        )
        return task

    async def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get a single task with all details.

        Returns a dict with display labels included.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(HumanTask).where(HumanTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            return self._task_to_dict(task)

    async def get_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List human tasks with optional filters.

        Args:
            status: Filter by status (pending, assigned, resolved, closed).
            priority: Filter by priority (low, normal, high, urgent).
            assigned_to: Filter by assigned staff ID.
            limit: Max results (default 50).
            offset: Pagination offset.

        Returns:
            List of task dicts (newest first).
        """
        conditions = []
        if status:
            conditions.append(HumanTask.status == status)
        if priority:
            conditions.append(HumanTask.priority == priority)
        if assigned_to is not None:
            conditions.append(HumanTask.assigned_to == assigned_to)

        query = select(HumanTask)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(desc(HumanTask.created_at)).limit(limit).offset(offset)

        async with async_session_factory() as session:
            result = await session.execute(query)
            tasks = result.scalars().all()

        return [self._task_to_dict(t) for t in tasks]

    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics for human tasks.

        Returns:
            Dict with counts by status, priority, and avg resolution time.
        """
        async with async_session_factory() as session:
            # Total count
            total_result = await session.execute(
                select(func.count(HumanTask.id))
            )
            total = total_result.scalar() or 0

            # By status
            status_result = await session.execute(
                select(HumanTask.status, func.count(HumanTask.id))
                .group_by(HumanTask.status)
            )
            status_counts = {row[0]: row[1] for row in status_result}

            # By priority
            priority_result = await session.execute(
                select(HumanTask.priority, func.count(HumanTask.id))
                .group_by(HumanTask.priority)
            )
            priority_counts = {row[0]: row[1] for row in priority_result}

            # By transfer reason
            reason_result = await session.execute(
                select(HumanTask.transfer_reason, func.count(HumanTask.id))
                .group_by(HumanTask.transfer_reason)
            )
            reason_counts = {row[0]: row[1] for row in reason_result}

            # Average resolution time (for resolved tasks)
            avg_result = await session.execute(
                select(
                    func.avg(
                        func.extract("epoch", HumanTask.resolved_at - HumanTask.created_at)
                    )
                ).where(
                    HumanTask.status == "resolved",
                    HumanTask.resolved_at.isnot(None),
                )
            )
            avg_resolution_seconds = avg_result.scalar() or 0

        return {
            "total": total,
            "by_status": {
                "pending": status_counts.get("pending", 0),
                "assigned": status_counts.get("assigned", 0),
                "resolved": status_counts.get("resolved", 0),
                "closed": status_counts.get("closed", 0),
            },
            "by_priority": {
                "low": priority_counts.get("low", 0),
                "normal": priority_counts.get("normal", 0),
                "high": priority_counts.get("high", 0),
                "urgent": priority_counts.get("urgent", 0),
            },
            "by_reason": reason_counts,
            "avg_resolution_minutes": round(avg_resolution_seconds / 60, 1) if avg_resolution_seconds else 0,
        }

    async def _generate_ticket_number(self) -> str:
        """Generate a unique ticket number: HT + YYYYMMDD + 3-digit sequence.

        Format: HT20260803001
        """
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")

        # Query the count of today's tasks to generate sequence
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(HumanTask.id)).where(
                    HumanTask.ticket_number.like(f"HT{date_str}%")
                )
            )
            count = result.scalar() or 0

        seq = count + 1
        return f"HT{date_str}{seq:03d}"

    def _task_to_dict(self, task: HumanTask) -> Dict[str, Any]:
        """Convert a HumanTask to a dict with display labels."""
        return {
            "id": task.id,
            "ticket_number": task.ticket_number,
            "conversation_id": task.conversation_id,
            "agent_id": task.agent_id,
            "user_id": task.user_id,
            "trace_id": task.trace_id,
            "user_message": task.user_message,
            "intent": task.intent,
            "confidence": task.confidence,
            "transfer_reason": task.transfer_reason,
            "transfer_reason_label": self.REASON_LABELS.get(task.transfer_reason, task.transfer_reason),
            "status": task.status,
            "status_label": self.STATUS_LABELS.get(task.status, task.status),
            "priority": task.priority,
            "priority_label": self.PRIORITY_LABELS.get(task.priority, task.priority),
            "assigned_to": task.assigned_to,
            "resolution_note": task.resolution_note,
            "resolution_type": task.resolution_type,
            "meta": task.meta or {},
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "assigned_at": task.assigned_at.isoformat() if task.assigned_at else None,
            "resolved_at": task.resolved_at.isoformat() if task.resolved_at else None,
            "is_open": task.is_open,
        }
