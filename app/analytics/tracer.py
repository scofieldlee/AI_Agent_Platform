"""
Analytics Tracer: records trace and span data for agent execution.

Usage:
    tracer = Tracer()
    await tracer.start_trace(context, user_input)
    # ... execute workflow ...
    await tracer.end_trace(status="success", output=result, ...)

    # Or use span context manager:
    async with tracer.span("intent", input_data={...}) as span:
        result = await some_node_func(state)
        span.set_output(result)
"""

import uuid
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SpanContext:
    """Mutable context passed through a span's lifetime."""

    def __init__(self, span_id: str, trace_id: str, node_name: str):
        self.span_id = span_id
        self.trace_id = trace_id
        self.node_name = node_name
        self.output_data: Dict[str, Any] = {}
        self.status: str = "success"
        self.error: Optional[str] = None
        self.token_usage: Dict[str, int] = {}

    def set_output(self, data: Dict[str, Any]):
        self.output_data = data

    def set_error(self, error: str):
        self.status = "error"
        self.error = error

    def set_token_usage(self, prompt_tokens: int, completion_tokens: int):
        self.token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }


class Tracer:
    """Records agent execution traces and spans to the database.

    One Tracer per agent run. Creates one Trace + multiple Spans.
    """

    def __init__(self):
        self.trace_id: Optional[str] = None
        self.trace_db_id: Optional[int] = None
        self._spans: list = []

    async def start_trace(
        self,
        context,  # AgentContext
        user_input: str,
    ) -> str:
        """Create a trace record in DB. Returns trace_id."""
        import uuid as uuid_mod

        self.trace_id = context.trace_id

        try:
            from app.database.session import async_session_factory
            from app.models.analytics import AgentTrace

            now = datetime.now(timezone.utc)

            async with async_session_factory() as session:
                trace = AgentTrace(
                    trace_id=self.trace_id,
                    user_id=context.user_id,
                    agent_id=context.agent_id,
                    conversation_id=context.conversation_id,
                    status="running",
                    input_data={"user_input": user_input[:500]},
                    started_at=now,
                )
                session.add(trace)
                await session.commit()
                await session.refresh(trace)
                self.trace_db_id = trace.id

            logger.debug(f"Trace started: {self.trace_id}")
        except Exception as e:
            logger.warning(f"Failed to start trace: {e}")
            # Tracing is non-critical — don't block agent execution

        return self.trace_id

    async def end_trace(
        self,
        status: str,
        output: Dict[str, Any],
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        total_tokens: int = 0,
        total_cost: float = 0.0,
    ):
        """Update trace record with completion data."""
        if not self.trace_db_id:
            return

        try:
            from app.database.session import async_session_factory
            from app.models.analytics import AgentTrace
            from sqlalchemy import select

            now = datetime.now(timezone.utc)

            async with async_session_factory() as session:
                result = await session.execute(
                    select(AgentTrace).where(AgentTrace.id == self.trace_db_id)
                )
                trace = result.scalar_one_or_none()
                if trace:
                    trace.status = status
                    trace.output_data = output
                    trace.intent = intent
                    trace.confidence = confidence
                    trace.total_tokens = total_tokens
                    trace.total_cost = total_cost
                    trace.completed_at = now
                    if trace.started_at:
                        delta = now - trace.started_at
                        trace.duration_ms = int(delta.total_seconds() * 1000)
                    await session.commit()

            logger.debug(
                f"Trace ended: {self.trace_id} | status={status} | "
                f"duration={trace.duration_ms if trace else '?'}ms"
            )
        except Exception as e:
            logger.warning(f"Failed to end trace: {e}")

    @asynccontextmanager
    async def span(
        self,
        node_name: str,
        node_type: str = "workflow",
        input_data: Optional[Dict] = None,
    ):
        """Async context manager that creates a span.

        Usage:
            async with tracer.span("intent", input_data={...}) as span:
                result = await do_work()
                span.set_output(result)
        """
        span_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        ctx = SpanContext(span_id=span_id, trace_id=self.trace_id or "", node_name=node_name)

        # Persist span start to DB
        try:
            from app.database.session import async_session_factory
            from app.models.analytics import AgentSpan

            async with async_session_factory() as session:
                span_record = AgentSpan(
                    trace_id=self.trace_id,
                    span_id=span_id,
                    node_name=node_name,
                    node_type=node_type,
                    status="running",
                    input_data=input_data or {},
                    started_at=now,
                )
                session.add(span_record)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to create span {node_name}: {e}")

        try:
            yield ctx
        except Exception as e:
            ctx.set_error(str(e))
            raise
        finally:
            await self._end_span(ctx, node_name)

    async def _end_span(self, ctx: SpanContext, node_name: str):
        """Update span record with completion data."""
        try:
            from app.database.session import async_session_factory
            from app.models.analytics import AgentSpan
            from sqlalchemy import select

            now = datetime.now(timezone.utc)

            async with async_session_factory() as session:
                result = await session.execute(
                    select(AgentSpan).where(AgentSpan.span_id == ctx.span_id)
                )
                span = result.scalar_one_or_none()
                if span:
                    span.status = ctx.status
                    span.output_data = ctx.output_data
                    span.token_usage = ctx.token_usage or {}
                    span.error = ctx.error
                    span.completed_at = now
                    if span.started_at:
                        delta = now - span.started_at
                        span.duration_ms = int(delta.total_seconds() * 1000)
                    await session.commit()

            logger.debug(
                f"Span ended: {node_name} | status={ctx.status} | "
                f"duration={span.duration_ms if span else '?'}ms"
            )
        except Exception as e:
            logger.warning(f"Failed to end span {node_name}: {e}")

    def wrap_node(self, node_name: str, node_func, node_type: str = "workflow"):
        """Wrap a LangGraph node function with tracing.

        Returns a new async function that creates a span around the original.
        The original node function is not modified.
        """
        tracer = self

        async def traced_node(state):
            # Extract safe input data (avoid huge payloads)
            input_summary = {
                "user_input": str(state.get("user_input", ""))[:200],
                "intent": state.get("intent"),
                "conversation_id": state.get("conversation_id"),
            }

            async with tracer.span(node_name, node_type, input_data=input_summary) as span_ctx:
                try:
                    result = await node_func(state)
                    # Only store safe output summary
                    safe_output = {}
                    if isinstance(result, dict):
                        for k, v in result.items():
                            if k == "knowledge_sources":
                                safe_output[k] = f"{len(v)} sources"
                            elif k == "tool_results":
                                safe_output[k] = f"{len(v)} results"
                            elif k == "answer":
                                safe_output[k] = str(v)[:200]
                            elif k == "knowledge_context":
                                safe_output[k] = f"{len(str(v))} chars"
                            else:
                                safe_output[k] = v
                    span_ctx.set_output(safe_output)
                    return result
                except Exception as e:
                    span_ctx.set_error(str(e))
                    raise

        return traced_node
