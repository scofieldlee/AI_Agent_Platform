"""
Dynamic LangGraph builder: compiles a runnable StateGraph from a
database-persisted graph_config (as edited in the admin workflow editor).

Graph config shape (stored in workflows.graph_config):
    {
        "entry_point": "intent",
        "nodes": [
            {
                "id": "intent", "name": "意图分类", "node_type": "intent",
                "category": "intent", "type": "processing",
                "inputs": [...], "outputs": [...],
                "position": {"x": 50, "y": 200}, "config": {}
            }, ...
        ],
        "edges": [
            {
                "id": "e-intent-knowledge", "source": "intent", "target": "knowledge",
                "label": "confidence >= 0.5", "condition": "confidence >= 0.5",
                "edge_type": "conditional"
            }, ...
        ]
    }

Node implementation lookup is driven by ``node_type``; unknown node types are
skipped with a warning so a misconfigured draft never crashes the runtime.
"""

import logging
from typing import Dict, Any, List, Optional, Callable

from langgraph.graph import StateGraph, END

from app.runtime.state import AgentState

logger = logging.getLogger(__name__)


# --- Node implementation registry ---

def _node_impls() -> Dict[str, Callable]:
    from app.workflows.nodes import (
        intent_node, knowledge_node, memory_node, tool_node, llm_node, human_node,
    )
    return {
        "intent": intent_node,
        "knowledge": knowledge_node,
        "memory": memory_node,
        "tool": tool_node,
        "llm": llm_node,
        "human": human_node,
    }


# Node type -> trace category (for span recording)
NODE_TRACE_CATEGORY = {
    "intent": "workflow",
    "knowledge": "retrieval",
    "memory": "retrieval",
    "tool": "tool",
    "llm": "model",
    "human": "workflow",
}


# --- Condition evaluation ---

def _normalize_condition(expr: str) -> str:
    """Normalize a condition expression to Python-compatible syntax.

    Supports the friendly operators used in the editor:
        && -> and, || -> or, ! -> not
    """
    normalized = expr.replace("&&", " and ").replace("||", " or ")
    # Replace '!' only when used as a unary operator (not ==, !=, <=, >=, !in, !is)
    result = []
    i = 0
    while i < len(normalized):
        ch = normalized[i]
        if ch == "!":
            nxt = normalized[i + 1] if i + 1 < len(normalized) else ""
            if nxt in ("=", ">", "<"):  # !=, !>, !< keep as-is (python handles !=)
                result.append(ch)
            else:
                result.append(" not ")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def evaluate_condition(expr: str, state: AgentState) -> bool:
    """Safely evaluate a condition expression against the agent state.

    Only exposes a restricted namespace (no builtins) with the state fields.
    Returns False on any error so routing degrades gracefully.
    """
    expr = expr.strip()
    if not expr:
        return True

    # Restricted namespace: state fields only (no builtins).
    # A small whitelist of safe helpers for len-based conditions.
    helpers: Dict[str, Any] = {"len": len}
    namespace: Dict[str, Any] = {
        k: v for k, v in state.items() if k.isidentifier()
    }
    namespace.update(helpers)

    try:
        normalized = _normalize_condition(expr)
        return bool(eval(normalized, {"__builtins__": {}}, namespace))  # noqa: S307
    except Exception as e:
        logger.warning(f"Condition evaluation failed for '{expr}': {e}")
        return False


# --- Router factories ---


def _make_router(source: str, edges: List[Dict[str, Any]]) -> Callable[[AgentState], str]:
    """Create a LangGraph conditional router for a node's outgoing edges.

    Checks conditional edges in order; the first whose condition evaluates to
    True wins. Falls back to the single default edge, then to the last edge.
    """

    def router(state: AgentState) -> str:
        for edge in edges:
            if edge.get("edge_type") == "conditional" and edge.get("condition"):
                if evaluate_condition(edge["condition"], state):
                    return edge["id"]
        # Fallback: default edge
        for edge in edges:
            if edge.get("edge_type") != "conditional":
                return edge["id"]
        # Last resort: last edge in definition order
        return edges[-1]["id"]

    return router


def _resolve_target(target: str) -> str:
    return END if target == "END" else target


# --- Graph construction ---

def build_graph_from_config(
    graph_config: Dict[str, Any],
    tracer: Optional[Any] = None,
) -> "CompiledStateGraph":
    """Compile a runnable LangGraph from a persisted graph_config.

    Args:
        graph_config: nodes/edges/entry_point as documented above.
        tracer: optional Tracer instance used to wrap nodes for span recording.

    Returns:
        A compiled LangGraph executable.

    Raises:
        ValueError: when the config has no entry point or no usable nodes.
    """
    impls = _node_impls()
    nodes = graph_config.get("nodes", [])
    edges = graph_config.get("edges", [])
    entry_point = graph_config.get("entry_point")

    if not entry_point:
        raise ValueError("graph_config missing entry_point")
    if not nodes:
        raise ValueError("graph_config has no nodes")

    # Build node lookup
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        node_type = node.get("node_type")
        if node_type not in impls:
            logger.warning(
                f"Skipping node '{node_id}': unknown node_type '{node_type}' "
                f"(supported: {list(impls.keys())})"
            )
            continue
        node_by_id[node_id] = node

    if not node_by_id:
        raise ValueError("graph_config has no usable nodes (unknown node types)")

    graph = StateGraph(AgentState)

    # Add nodes
    for node_id, node in node_by_id.items():
        impl = impls[node["node_type"]]
        if tracer is not None:
            category = NODE_TRACE_CATEGORY.get(node["node_type"], "workflow")
            impl = tracer.wrap_node(node_id, impl, category)
        graph.add_node(node_id, impl)

    # Group outgoing edges by source
    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        # Ignore edges from nodes that don't exist (dangling edges)
        if source not in node_by_id:
            continue
        outgoing.setdefault(source, []).append(edge)

    # Add edges
    for source, edge_list in outgoing.items():
        if len(edge_list) == 1:
            edge = edge_list[0]
            graph.add_edge(source, _resolve_target(edge["target"]))
        else:
            # Conditional routing: at least one conditional edge expected
            if not any(e.get("edge_type") == "conditional" for e in edge_list):
                # Multiple plain edges: keep only the first, warn about the rest
                logger.warning(
                    f"Node '{source}' has {len(edge_list)} plain edges without "
                    f"conditions; only the first is used"
                )
                graph.add_edge(source, _resolve_target(edge_list[0]["target"]))
                continue
            path_map = {e["id"]: _resolve_target(e["target"]) for e in edge_list}
            graph.add_conditional_edges(source, _make_router(source, edge_list), path_map)

    graph.set_entry_point(entry_point)
    return graph.compile()
