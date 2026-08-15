"""
AgentRuntime: main entry point for agent execution.

Flow: user_input -> LangGraph Workflow -> response.

The workflow for MVP product customer service agent:
  Start -> Intent -> Router -> Knowledge Search -> Tool -> LLM -> Answer -> End
                                  |-> Human (if low confidence)
"""

import logging
import time
from typing import Optional, Dict, Any, List

from langgraph.graph import StateGraph, END

from app.runtime.state import AgentState
from app.runtime.context import AgentContext
from app.analytics.tracer import Tracer

logger = logging.getLogger(__name__)

# --- Runtime workflow config cache ---
# Workflow definitions are loaded from the database at most once per
# WORKFLOW_CACHE_TTL seconds per key (agent binding or global default),
# so edits become effective quickly while avoiding a DB round-trip on
# every message. Keys: f"agent:{id}" for agent-bound workflows, "default"
# for the global default.
WORKFLOW_CACHE_TTL = 5.0
_workflow_cache: Dict[str, Any] = {}
_workflow_cache_ts: float = 0.0


def invalidate_workflow_cache() -> None:
    """Drop the cached workflow definitions (called after save/publish/bind)."""
    global _workflow_cache_ts
    _workflow_cache.clear()
    _workflow_cache_ts = 0.0
    logger.debug("Workflow cache invalidated")


class AgentRuntime:
    """Executes agent workflows using LangGraph.

    Usage:
        runtime = AgentRuntime()
        result = await runtime.run("What products do you have?", context)
    """

    def __init__(self):
        self.tracer: Optional[Tracer] = None

    async def _load_workflow_config(self, agent_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Load the workflow graph_config for an agent with a short TTL cache.

        Resolution priority:
          1. Workflow bound to this agent via AgentWorkflowBinding
             (primary binding first, any binding as fallback).
          2. Global default workflow.
        Returns None when no workflow definition is available.
        """
        global _workflow_cache, _workflow_cache_ts
        now = time.monotonic()
        cache_key = f"agent:{agent_id}" if agent_id else "default"

        if cache_key in _workflow_cache and (now - _workflow_cache_ts) < WORKFLOW_CACHE_TTL:
            return _workflow_cache.get(cache_key)

        try:
            from app.database.session import async_session_factory
            from app.repositories.workflow_repo import (
                get_agent_bound_workflow, get_default_workflow,
            )
            async with async_session_factory() as db:
                wf = None
                source = "global default"
                if agent_id:
                    wf = await get_agent_bound_workflow(db, agent_id)
                    if wf:
                        source = f"agent binding (id={agent_id})"
                if wf is None:
                    wf = await get_default_workflow(db)

                if wf and wf.graph_config and wf.graph_config.get("nodes"):
                    _workflow_cache[cache_key] = wf.graph_config
                    _workflow_cache_ts = now
                    logger.info(
                        f"Loaded workflow from DB: '{wf.name}' (id={wf.id}, "
                        f"source={source}, {len(wf.graph_config.get('nodes', []))} nodes)"
                    )
                    return wf.graph_config
        except Exception as e:
            logger.warning(f"Failed to load workflow from DB (agent_id={agent_id}): {e}")

        _workflow_cache[cache_key] = None
        _workflow_cache_ts = now
        return None

    async def run(
        self,
        user_input: str,
        context: AgentContext,
        conversation_history: Optional[List[Dict]] = None,
        attachments: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Execute the agent workflow.

        Args:
            user_input: User's message text.
            context: Agent execution context.
            conversation_history: Previous messages [{role, content}] for multi-turn.
            attachments: Parsed file attachments [{type, content, meta}].

        Returns:
            Dict with: answer, intent, confidence, knowledge_sources, need_human, trace_id
        """
        # Initialize tracer for this run
        self.tracer = Tracer()
        await self.tracer.start_trace(context, user_input)

        # Initialize state
        initial_state: AgentState = {
            "user_input": user_input,
            "conversation_id": context.conversation_id,
            "conversation_history": conversation_history or [],
            "attachments": attachments or [],
            "intent": None,
            "confidence": 0.0,
            "knowledge_context": "",
            "knowledge_sources": [],
            "memory_context": "",
            "memories_used": [],
            "need_tool": False,
            "tool_results": [],
            "messages": [],
            "answer": "",
            "need_human": False,
            "transfer_reason": None,
            "ticket_number": None,
            "trace_id": context.trace_id,
            "agent_id": context.agent_id,
            "user_id": context.user_id,
        }

        # Build and compile the workflow graph (with tracing wrappers)
        graph = await self._build_graph(agent_id=context.agent_id)

        # Execute
        try:
            final_state = await graph.ainvoke(initial_state)

            intent = final_state.get("intent")
            confidence = final_state.get("confidence")
            need_human = final_state.get("need_human", False)

            # Determine trace status
            trace_status = "human_transfer" if need_human else "success"

            # End trace
            await self.tracer.end_trace(
                status=trace_status,
                output={
                    "answer": str(final_state.get("answer", ""))[:500],
                    "intent": intent,
                    "confidence": confidence,
                    "need_human": need_human,
                },
                intent=intent,
                confidence=confidence,
            )

            logger.info(
                f"Agent run completed | trace={context.trace_id} "
                f"intent={intent} "
                f"confidence={confidence}"
            )

            # Post-processing: extract and store long-term memories
            # Non-critical: if this fails, the response is still valid
            try:
                from app.memory.service import MemoryService
                mem_service = MemoryService()
                await mem_service.extract_and_store(
                    user_input=user_input,
                    agent_answer=final_state.get("answer", ""),
                    conversation_history=conversation_history or [],
                    user_id=context.user_id,
                    agent_id=context.agent_id,
                    conversation_id=context.conversation_id,
                )
            except Exception as mem_err:
                logger.warning(f"Memory extraction failed (non-blocking): {mem_err}")

            return {
                "answer": final_state.get("answer", ""),
                "intent": final_state.get("intent"),
                "confidence": final_state.get("confidence"),
                "knowledge_sources": final_state.get("knowledge_sources", []),
                "memories_used": final_state.get("memories_used", []),
                "need_human": final_state.get("need_human", False),
                "transfer_reason": final_state.get("transfer_reason"),
                "ticket_number": final_state.get("ticket_number"),
                "trace_id": context.trace_id,
            }
        except Exception as e:
            logger.error(f"Agent run failed | trace={context.trace_id} error={e}", exc_info=True)

            # End trace with error
            await self.tracer.end_trace(
                status="failed",
                output={"error": str(e)[:500]},
                intent=None,
                confidence=0.0,
            )

            return {
                "answer": "抱歉，处理您的请求时遇到了错误。请重试或联系人工客服。",
                "intent": None,
                "confidence": 0.0,
                "knowledge_sources": [],
                "need_human": True,
                "transfer_reason": "system_error",
                "trace_id": context.trace_id,
            }

    async def _build_graph(self, agent_id: Optional[int] = None):
        """Build the LangGraph workflow for an agent.

        Priority:
          1. Workflow bound to this agent (editable in admin UI).
          2. Database-defined default workflow.
          3. Hardcoded legacy MVP graph (fallback if DB is unavailable/empty).
        """
        try:
            config = await self._load_workflow_config(agent_id=agent_id)
            if config:
                from app.runtime.graph_builder import build_graph_from_config
                return build_graph_from_config(config, tracer=self.tracer)
        except Exception as e:
            logger.warning(f"Failed to build graph from DB definition: {e}", exc_info=True)

        logger.info("Falling back to legacy hardcoded workflow graph")
        return self._build_legacy_graph()

    def _build_legacy_graph(self) -> StateGraph:
        """Hardcoded MVP workflow (fallback path).

        MVP workflow:
            START -> intent -> knowledge -> memory -> tool -> llm -> END
                                                        -> human -> END (if low confidence)

        Each node is wrapped with Tracer for span recording.
        """
        from app.workflows.nodes import (
            intent_node, knowledge_node, memory_node, tool_node, llm_node, human_node,
        )

        graph = StateGraph(AgentState)

        # Wrap nodes with tracing (non-critical: if tracer is None, just use raw nodes)
        if self.tracer:
            wrap = self.tracer.wrap_node
            graph.add_node("intent", wrap("intent", intent_node, "workflow"))
            graph.add_node("knowledge", wrap("knowledge", knowledge_node, "retrieval"))
            graph.add_node("memory", wrap("memory", memory_node, "retrieval"))
            graph.add_node("tool", wrap("tool", tool_node, "tool"))
            graph.add_node("llm", wrap("llm", llm_node, "model"))
            graph.add_node("human", wrap("human", human_node, "workflow"))
        else:
            graph.add_node("intent", intent_node)
            graph.add_node("knowledge", knowledge_node)
            graph.add_node("memory", memory_node)
            graph.add_node("tool", tool_node)
            graph.add_node("llm", llm_node)
            graph.add_node("human", human_node)

        # Set entry point
        graph.set_entry_point("intent")

        # Conditional routing after intent classification
        graph.add_conditional_edges(
            "intent",
            self._router,
            {
                "knowledge": "knowledge",
                "human": "human",
            },
        )

        # Knowledge -> Memory -> Tool
        graph.add_edge("knowledge", "memory")
        graph.add_edge("memory", "tool")

        # Tool -> LLM
        graph.add_edge("tool", "llm")

        # LLM -> END (with confidence check could route to human)
        graph.add_conditional_edges(
            "llm",
            self._llm_router,
            {
                "end": END,
                "human": "human",
            },
        )

        # Human -> END
        graph.add_edge("human", END)

        return graph.compile()

    def _router(self, state: AgentState) -> str:
        """Route after intent classification.

        Hybrid Router: rule-based first, LLM fallback.
        """
        confidence = state.get("confidence", 0.0)
        if confidence < 0.5:
            return "human"
        return "knowledge"

    def _llm_router(self, state: AgentState) -> str:
        """Route after LLM response.

        If confidence is still low after generating answer, transfer to human.
        """
        confidence = state.get("confidence", 0.0)
        if confidence < 0.5 or state.get("need_human", False):
            return "human"
        return "end"
