"""
Default workflow seed data.

The default product customer service workflow (previously hardcoded in
app/api/v1/endpoints/workflow.py) is persisted to the workflows table on
startup so it can be edited from the admin UI.

Each node carries a ``node_type`` field that maps to the executor
implementation (intent / knowledge / memory / tool / llm / human).
"""

from typing import Dict, Any, Optional
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow

logger = logging.getLogger(__name__)

DEFAULT_WORKFLOW_CODE = "product_customer_service"


def default_graph_config() -> Dict[str, Any]:
    """Build the default product customer service workflow graph config."""
    return {
        "entry_point": "intent",
        "nodes": [
            {
                "id": "intent",
                "name": "意图分类",
                "node_type": "intent",
                "type": "processing",
                "category": "intent",
                "description": "使用 DeepSeek LLM 对用户输入进行意图分类，支持 8 种意图：product_info, product_compare, purchase_advice, order_query, after_sale, complaint, greeting, unknown。LLM 失败时自动降级为关键词匹配。",
                "inputs": ["user_input", "conversation_history"],
                "outputs": ["intent", "confidence"],
                "position": {"x": 50, "y": 200},
                "config": {},
            },
            {
                "id": "knowledge",
                "name": "知识检索",
                "node_type": "knowledge",
                "type": "processing",
                "category": "retrieval",
                "description": "RAG 知识检索：将用户问题向量化，在 pgvector 中搜索最相关的产品文档片段（top 5），作为 LLM 回答的知识上下文。",
                "inputs": ["user_input", "intent"],
                "outputs": ["knowledge_context", "knowledge_sources"],
                "position": {"x": 350, "y": 100},
                "config": {},
            },
            {
                "id": "memory",
                "name": "记忆检索",
                "node_type": "memory",
                "type": "processing",
                "category": "retrieval",
                "description": "长期记忆检索：使用 pgvector 语义搜索该用户的历史记忆（偏好、事实、行为），注入 LLM prompt 实现个性化回答。",
                "inputs": ["user_input", "user_id", "agent_id"],
                "outputs": ["memory_context", "memories_used"],
                "position": {"x": 650, "y": 100},
                "config": {},
            },
            {
                "id": "tool",
                "name": "工具执行",
                "node_type": "tool",
                "type": "processing",
                "category": "tool",
                "description": "多工具并行调度器：根据意图映射表并行执行工具。product_info → [product_query, inventory_query]，order_query → [order_query, logistics_query]，after_sale → [refund_query, logistics_query, order_query]。",
                "inputs": ["user_input", "intent", "agent_id", "conversation_id", "trace_id"],
                "outputs": ["tool_results"],
                "position": {"x": 950, "y": 100},
                "config": {},
            },
            {
                "id": "llm",
                "name": "LLM 生成",
                "node_type": "llm",
                "type": "processing",
                "category": "model",
                "description": "使用 DeepSeek 生成最终回答。System Prompt 定义客服角色职责，注入知识上下文 + 工具结果 + 记忆信息 + 对话历史，生成自然语言回答。",
                "inputs": ["user_input", "knowledge_context", "memory_context", "tool_results", "conversation_history", "intent"],
                "outputs": ["answer", "confidence", "need_human", "transfer_reason"],
                "position": {"x": 1250, "y": 100},
                "config": {},
            },
            {
                "id": "human",
                "name": "转人工",
                "node_type": "human",
                "type": "terminal",
                "category": "human",
                "description": "创建人工客服工单：记录用户消息、意图、置信度、转接原因、AI 预答和 trace_id，分配优先级（complaint=urgent），返回工单号给用户。",
                "inputs": ["user_input", "intent", "confidence", "transfer_reason", "answer", "conversation_id", "agent_id", "trace_id"],
                "outputs": ["answer", "need_human", "ticket_number"],
                "position": {"x": 1250, "y": 350},
                "config": {},
            },
        ],
        "edges": [
            {
                "id": "e-intent-knowledge",
                "source": "intent",
                "target": "knowledge",
                "label": "confidence >= 0.5",
                "condition": "confidence >= 0.5",
                "edge_type": "conditional",
            },
            {
                "id": "e-intent-human",
                "source": "intent",
                "target": "human",
                "label": "confidence < 0.5",
                "condition": "confidence < 0.5",
                "edge_type": "conditional",
            },
            {
                "id": "e-knowledge-memory",
                "source": "knowledge",
                "target": "memory",
                "edge_type": "default",
            },
            {
                "id": "e-memory-tool",
                "source": "memory",
                "target": "tool",
                "edge_type": "default",
            },
            {
                "id": "e-tool-llm",
                "source": "tool",
                "target": "llm",
                "edge_type": "default",
            },
            {
                "id": "e-llm-end",
                "source": "llm",
                "target": "END",
                "label": "confidence >= 0.5",
                "condition": "confidence >= 0.5 && !need_human",
                "edge_type": "conditional",
            },
            {
                "id": "e-llm-human",
                "source": "llm",
                "target": "human",
                "label": "need_human",
                "condition": "confidence < 0.5 || need_human",
                "edge_type": "conditional",
            },
        ],
    }


async def seed_default_workflow(db: AsyncSession) -> None:
    """Ensure the default workflow exists in the database.

    - Creates it if no workflow with the default code exists.
    - Back-fills graph_config if the row exists but is empty (migration path).
    """
    result = await db.execute(
        select(Workflow).where(Workflow.code == DEFAULT_WORKFLOW_CODE)
    )
    wf = result.scalar_one_or_none()

    if wf is None:
        wf = Workflow(
            name="商品客服 Agent 工作流",
            code=DEFAULT_WORKFLOW_CODE,
            description=(
                "基于 LangGraph 的多节点客服工作流："
                "意图分类 → 知识检索 → 记忆检索 → 工具执行 → LLM 生成 → 转人工"
            ),
            workflow_type="hybrid",
            status="published",
            version="0.1.0",
            graph_config=default_graph_config(),
            is_active=True,
        )
        db.add(wf)
        await db.commit()
        logger.info(f"Seeded default workflow: {DEFAULT_WORKFLOW_CODE}")
    elif not wf.graph_config:
        wf.graph_config = default_graph_config()
        await db.commit()
        logger.info(f"Back-filled graph_config for default workflow: {DEFAULT_WORKFLOW_CODE}")
    else:
        logger.debug(f"Default workflow already seeded: {DEFAULT_WORKFLOW_CODE} (id={wf.id})")
