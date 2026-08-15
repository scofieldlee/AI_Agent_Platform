"""
AgentState: TypedDict for LangGraph state management.
Passed through all nodes in the workflow.
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated
from operator import add


class AgentState(TypedDict, total=False):
    """
    State object for agent workflow.

    Each node reads from and writes to this state.
    LangGraph manages state transitions and checkpointing.
    """

    # --- Input ---
    user_input: str                    # User's message
    conversation_id: Optional[int]     # Conversation ID for context
    conversation_history: List[Dict]   # Previous messages [{role, content}]
    attachments: List[Dict]            # Parsed attachments [{type, content, meta}]

    # --- Intent ---
    intent: Optional[str]              # Classified intent (product_info, order_query, etc.)
    confidence: float                  # Intent classification confidence (0.0-1.0)

    # --- Knowledge ---
    knowledge_context: str             # Retrieved knowledge for LLM context
    knowledge_sources: List[Dict]      # Source documents [{title, section, score}]

    # --- Memory ---
    memory_context: str                # Retrieved memories for context
    memories_used: List[Dict]          # Retrieved memory items [{id, content, type, score}]

    # --- Tools ---
    need_tool: bool                    # Whether tool execution is needed
    tool_results: Annotated[List[Dict], add]  # Tool execution results

    # --- Output ---
    messages: Annotated[List[Dict], add]      # Conversation messages
    answer: str                        # Final answer to user
    need_human: bool                   # Whether to transfer to human
    transfer_reason: Optional[str]     # Reason for human transfer
    ticket_number: Optional[str]       # Human task ticket number (if transferred)

    # --- Metadata ---
    trace_id: str                      # Trace ID for analytics
    agent_id: Optional[int]            # Agent ID
    user_id: Optional[int]             # User ID
