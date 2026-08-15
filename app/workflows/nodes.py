"""
Workflow nodes for the product customer service agent.

Each node is an async function: (state) -> state_update (dict).
Nodes use Model Center for LLM calls and Knowledge module for RAG.

MVP Workflow:
  intent -> knowledge -> llm -> (end | human)
"""

import logging
from typing import Dict, Any, Optional

from app.runtime.state import AgentState

logger = logging.getLogger(__name__)


# --- Default System Prompt (used when agent config has no system_prompt) ---

DEFAULT_SYSTEM_PROMPT = """你是 Ruko（路客）品牌的专业商品客服助手，负责为顾客解答关于遥控无人机、遥控玩具等商品的问题。

你的职责：
- 回答商品相关问题（参数、功能、特点、价格区间）
- 根据顾客需求推荐合适的商品
- 查询订单状态和物流信息（已发货/待发货/已签收/快递单号）
- 查询库存状态（是否有货、预计到货时间）
- 处理售后咨询（退款进度、退换货政策、物流轨迹、保修范围）
- 当问题超出你的能力范围时，主动转接人工客服

回答规则：
- 严格按照提供的知识上下文回答，不要编造产品参数或价格
- 如果提供了商品查询工具结果（结构化数据），优先使用其中的价格和参数信息
- 如果提供了订单查询结果，直接告诉顾客订单状态、快递单号和承运商
- 如果提供了库存查询结果，告诉顾客是否有货、价格和预计到货时间
- 如果提供了退款查询结果，告诉顾客退款单号、处理状态、退款金额和退款类型
- 如果提供了物流轨迹查询结果，告诉顾客当前物流状态、当前位置、预计送达时间，并简要列出最近的物流轨迹
- 如果知识上下文中没有相关信息，诚实告知并建议转人工
- 语气友好、专业、简洁，用自然语言回答
- 如果顾客在投诉或情绪激动，直接建议转人工客服
- 可以结合对话历史理解顾客的上下文（比如顾客之前问了A产品，现在说"那它的续航呢"，你应该理解"它"指A产品）
- 如果提供了顾客记忆信息，请结合这些信息个性化回答（比如顾客偏好某价位，推荐时优先考虑）

回答格式：用中文自然语言回答，简短回答不需要使用标题或列表。"""


async def _load_agent_config(agent_id: Optional[int]) -> Dict[str, Any]:
    """Load agent config from database. Returns empty dict if not found."""
    if not agent_id:
        return {}
    try:
        from app.database.session import async_session_factory
        async with async_session_factory() as db:
            from app.models.agent import Agent
            agent = await db.get(Agent, agent_id)
            if agent and agent.config:
                return agent.config
    except Exception as e:
        logger.warning(f"Failed to load agent config (agent_id={agent_id}): {e}")
    return {}


async def _resolve_model_config_id(model_id: str) -> Optional[int]:
    """Resolve old string model_id to a ModelConfig ID."""
    try:
        from app.database.session import async_session_factory
        from app.repositories.model_repo import get_model_config
        from sqlalchemy import select
        from app.models.model_config import ModelConfig
        async with async_session_factory() as db:
            result = await db.execute(
                select(ModelConfig)
                .where(ModelConfig.model_id == model_id)
                .where(ModelConfig.is_active.is_(True))
                .order_by(ModelConfig.is_default.desc(), ModelConfig.id.asc())
            )
            config = result.scalars().first()
            return config.id if config else None
    except Exception as e:
        logger.warning(f"Failed to resolve model_config_id for '{model_id}': {e}")
    return None


# --- Intent Classification Node ---

async def intent_node(state: AgentState) -> Dict[str, Any]:
    """Classify user intent using LLM.

    Uses IntentClassifier (DeepSeek-powered) for accurate classification of
    natural language, including colloquial expressions and context-dependent
    references. Falls back to keyword matching if LLM is unavailable.

    Intents: product_info, product_compare, purchase_advice, order_query,
              after_sale, complaint, greeting, unknown.
    """
    user_input = state.get("user_input", "")
    conversation_history = state.get("conversation_history", [])

    from app.workflows.intent_classifier import IntentClassifier

    classifier = IntentClassifier()
    result = await classifier.classify(
        user_input=user_input,
        conversation_history=conversation_history,
    )

    intent = result.get("intent", "unknown")
    confidence = result.get("confidence", 0.5)
    reasoning = result.get("reasoning", "")

    logger.info(
        f"Intent: {intent} (confidence={confidence}) | "
        f"reasoning={reasoning[:60]} | input={user_input[:50]}"
    )

    return {
        "intent": intent,
        "confidence": confidence,
    }


# --- Knowledge Retrieval Node (RAG) ---

async def knowledge_node(state: AgentState) -> Dict[str, Any]:
    """Retrieve relevant knowledge using RAG.

    Flow: Query -> Embedding -> Vector Search -> Rerank -> Context.
    """
    user_input = state.get("user_input", "")
    intent = state.get("intent", "unknown")

    try:
        from app.knowledge.retrievers.vector_retriever import retrieve_knowledge
        result = await retrieve_knowledge(user_input, top_k=5)
        knowledge_context = result.get("context", "")
        knowledge_sources = result.get("sources", [])
    except Exception as e:
        logger.warning(f"Knowledge retrieval failed: {e}")
        knowledge_context = ""
        knowledge_sources = []

    logger.info(
        f"Knowledge retrieved: {len(knowledge_sources)} sources | intent={intent}"
    )

    return {
        "knowledge_context": knowledge_context,
        "knowledge_sources": knowledge_sources,
    }


# --- Memory Retrieval Node ---

async def memory_node(state: AgentState) -> Dict[str, Any]:
    """Retrieve relevant long-term memories for the user's query.

    Uses pgvector semantic search to find memories that are relevant
    to the current user input. Memories are scoped by user_id and agent_id.

    Retrieved memories are stored in state['memory_context'] for
    injection into the LLM prompt.
    """
    user_input = state.get("user_input", "")
    user_id = state.get("user_id")
    agent_id = state.get("agent_id")

    try:
        from app.memory.service import MemoryService
        service = MemoryService()
        memories = await service.retrieve_memories(
            query=user_input,
            user_id=user_id,
            agent_id=agent_id,
            top_k=5,
        )

        memory_context = MemoryService.format_memory_context(memories)

        logger.info(f"Memories retrieved: {len(memories)} items for user={user_id}")

        return {
            "memory_context": memory_context,
            "memories_used": memories,
        }

    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")
        return {
            "memory_context": "",
            "memories_used": [],
        }


# --- Tool Execution Node ---

async def tool_node(state: AgentState) -> Dict[str, Any]:
    """Execute tools based on intent — multi-tool dispatcher.

    Intent → Tool mapping:
      - order_query           → order_query + logistics_query (tracking details)
      - product_info          → product_query + inventory_query
      - product_compare       → product_query + inventory_query
      - purchase_advice       → product_query + inventory_query
      - after_sale            → refund_query + logistics_query + order_query
      - other intents         → no-op

    Multiple tools can run in parallel for richer context.
    """
    user_input = state.get("user_input", "")
    intent = state.get("intent", "unknown")

    # Define which intents trigger which tools
    TOOL_MAP = {
        "order_query": ["order_query", "logistics_query"],
        "product_info": ["product_query", "inventory_query"],
        "product_compare": ["product_query", "inventory_query"],
        "purchase_advice": ["product_query", "inventory_query"],
        "after_sale": ["refund_query", "logistics_query", "order_query"],
    }

    tools_to_run = TOOL_MAP.get(intent, [])
    if not tools_to_run:
        logger.debug(f"Tool node skipped for intent={intent}")
        return {"tool_results": []}

    try:
        from app.tools.registry import get_registry
        from app.tools.executor import ToolExecutor
        import asyncio

        registry = get_registry()
        executor = ToolExecutor()

        # Build tool execution tasks
        async def run_tool(tool_name: str):
            """Run a single tool and return structured result."""
            if not registry.has(tool_name):
                logger.debug(f"Tool {tool_name} not registered, skipping")
                return None

            # Build parameters based on tool type
            if tool_name == "order_query":
                params = {"query": user_input}
            elif tool_name == "inventory_query":
                params = {"query": user_input}
            elif tool_name == "refund_query":
                params = {"query": user_input}
            elif tool_name == "logistics_query":
                params = {"query": user_input}
            else:
                params = {"query": user_input, "max_results": 5}

            result = await executor.execute(
                tool_name=tool_name,
                parameters=params,
                agent_id=state.get("agent_id"),
                conversation_id=state.get("conversation_id"),
                trace_id=state.get("trace_id"),
            )

            if not result.success:
                logger.warning(f"Tool {tool_name} failed: {result.error}")
                return None

            # Format result based on tool type
            data = result.data or {}
            formatted = {
                "tool": tool_name,
                "duration_ms": result.duration_ms,
            }

            if tool_name == "product_query":
                formatted["products"] = data.get("products", [])
                formatted["total"] = data.get("total", 0)
            elif tool_name == "order_query":
                formatted["orders"] = data.get("orders", [])
                formatted["total"] = data.get("total", 0)
                formatted["message"] = data.get("message", "")
            elif tool_name == "inventory_query":
                formatted["inventory"] = data.get("products", [])
                formatted["total"] = data.get("total", 0)
            elif tool_name == "refund_query":
                formatted["refunds"] = data.get("refunds", [])
                formatted["total"] = data.get("total", 0)
                formatted["message"] = data.get("message", "")
            elif tool_name == "logistics_query":
                formatted["trackings"] = data.get("trackings", [])
                formatted["total"] = data.get("total", 0)
                formatted["message"] = data.get("message", "")

            logger.info(
                f"Tool executed: {tool_name} | "
                f"results={formatted.get('total', 0)} | "
                f"duration={result.duration_ms}ms"
            )
            return formatted

        # Run all tools concurrently
        results = await asyncio.gather(
            *[run_tool(t) for t in tools_to_run],
            return_exceptions=True,
        )

        tool_results = [r for r in results if r is not None and not isinstance(r, Exception)]
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Tool execution error: {r}", exc_info=True)

        logger.info(f"Tool node done: {len(tool_results)} tools executed for intent={intent}")

        return {"tool_results": tool_results}

    except Exception as e:
        logger.error(f"Tool node failed: {e}", exc_info=True)
        return {"tool_results": []}


# --- LLM Response Node ---

async def llm_node(state: AgentState) -> Dict[str, Any]:
    """Generate response using LLM with knowledge context.

    Uses System Prompt + Knowledge Context + User Input -> LLM -> Answer.
    System prompt, temperature, and max_tokens are loaded from agent config
    if available; otherwise falls back to DEFAULT_SYSTEM_PROMPT.

    If attachments are present:
    - Text-type (pdf/word/excel/text): already injected into user_input by the endpoint
    - Image-type: passed as base64 to multimodal model via ModelService
    - Video-type: metadata injected as text, agent responds with "received, transfer to human"
    """
    user_input = state.get("user_input", "")
    knowledge_context = state.get("knowledge_context", "")
    memory_context = state.get("memory_context", "")
    intent = state.get("intent", "unknown")
    conversation_history = state.get("conversation_history", [])
    tool_results = state.get("tool_results", [])
    agent_id = state.get("agent_id")
    attachments = state.get("attachments", [])

    # Load agent config (system_prompt, temperature, max_tokens, model)
    agent_config = await _load_agent_config(agent_id)
    system_prompt = agent_config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    temperature = agent_config.get("temperature")
    max_tokens = agent_config.get("max_tokens", 4096)
    model_config_id = agent_config.get("model_config_id")

    # Backward compatibility: old configs stored "model" as model_id string
    if not model_config_id and agent_config.get("model"):
        model_config_id = await _resolve_model_config_id(agent_config.get("model"))

    logger.info(
        f"LLM node config | agent_id={agent_id} "
        f"has_custom_prompt={'system_prompt' in agent_config} "
        f"temperature={temperature} max_tokens={max_tokens} "
        f"model_config_id={model_config_id}"
    )

    # Build tool context string from structured tool results
    tool_context = ""
    if tool_results:
        tool_parts = []
        for tr in tool_results:
            tool_name = tr.get("tool", "")

            # Format product query results
            if tool_name == "product_query" and tr.get("products"):
                for p in tr["products"]:
                    price_str = f"，价格 {p.get('price')}" if p.get("price") else ""
                    tool_parts.append(
                        f"商品：{p.get('title')}（{p.get('section')}）"
                        f"{price_str}，相关度 {p.get('score')}\n"
                        f"内容：{p.get('content', '')[:300]}"
                    )

            # Format order query results
            elif tool_name == "order_query" and tr.get("orders"):
                for o in tr["orders"]:
                    tracking = ""
                    if o.get("tracking_number") and o["tracking_number"] != "暂无":
                        tracking = f"，快递单号 {o['tracking_number']}（{o.get('carrier', '')}）"
                    tool_parts.append(
                        f"订单：{o['order_number']}\n"
                        f"商品：{o['product_name']} x{o['quantity']}，"
                        f"金额 ${o['total_amount']:.2f}\n"
                        f"状态：{o.get('status_label', o.get('status', '未知'))}{tracking}\n"
                        f"客户：{o.get('customer_name', '')} {o.get('customer_phone', '')}"
                    )
                if tr.get("message"):
                    tool_parts.append(f"订单查询提示：{tr['message']}")

            # Format inventory query results
            elif tool_name == "inventory_query" and tr.get("inventory"):
                for inv in tr["inventory"]:
                    stock_str = (
                        f"库存 {inv['stock_quantity']} 件" if inv["stock_quantity"] > 0
                        else f"缺货，预计到货 {inv.get('restock_date', '未知')}"
                    )
                    tool_parts.append(
                        f"库存：{inv['product_name']}（SKU: {inv['sku']}）\n"
                        f"价格 ${inv['price']:.2f}，{stock_str}，"
                        f"状态：{inv.get('status_label', inv.get('status', '未知'))}"
                    )

            # Format refund query results
            elif tool_name == "refund_query" and tr.get("refunds"):
                for r in tr["refunds"]:
                    tool_parts.append(
                        f"退款：{r['refund_number']}\n"
                        f"订单：{r['order_number']}\n"
                        f"商品：{r['product_name']} x{r['quantity']}\n"
                        f"退款金额：{r['refund_amount']:.2f} {r.get('currency', 'CNY')}\n"
                        f"退款类型：{r.get('refund_type_label', r.get('refund_type', '未知'))}\n"
                        f"处理状态：{r.get('status_label', r.get('status', '未知'))}\n"
                        f"退款原因：{r.get('reason', '未提供')}\n"
                        f"客户：{r.get('customer_name', '')} {r.get('customer_phone', '')}"
                    )
                if tr.get("message"):
                    tool_parts.append(f"退款查询提示：{tr['message']}")

            # Format logistics tracking results
            elif tool_name == "logistics_query" and tr.get("trackings"):
                for t in tr["trackings"]:
                    events_str = ""
                    events = t.get("events", [])
                    if events:
                        # Show last 3 events
                        recent_events = events[-3:]
                        event_lines = [
                            f"  {e.get('timestamp', '')} {e.get('location', '')} — {e.get('description', '')}"
                            for e in recent_events
                        ]
                        events_str = "\n物流轨迹（最近{}条）：\n{}".format(
                            len(recent_events), "\n".join(event_lines)
                        )
                    tool_parts.append(
                        f"物流：{t['tracking_number']}\n"
                        f"订单：{t['order_number']} | 承运商：{t.get('carrier', '暂无')}\n"
                        f"状态：{t.get('status_label', t.get('status', '未知'))}\n"
                        f"当前位置：{t.get('current_location', '暂无')}\n"
                        f"预计送达：{t.get('estimated_delivery', '未知')}"
                        f"{events_str}"
                    )
                if tr.get("message"):
                    tool_parts.append(f"物流查询提示：{tr['message']}")

        if tool_parts:
            tool_context = "\n\n".join(tool_parts)

    # Build user prompt with knowledge context + tool context + memory
    context_parts = []
    if memory_context:
        context_parts.append(f"顾客记忆（来自历史对话）：\n{memory_context}")
    if knowledge_context:
        context_parts.append(f"知识上下文（产品文档）：\n{knowledge_context}")
    if tool_context:
        context_parts.append(f"业务数据（订单/库存/退款/物流查询结果）：\n{tool_context}")
    if not context_parts:
        context_parts.append("未检索到相关知识。")

    user_prompt = f"""{chr(10).join(context_parts)}

顾客问题：{user_input}

请根据上述信息回答顾客的问题。优先使用商品查询结果中的价格和参数。如果知识不足，请说明可能需要转接人工客服。"""

    # Collect image attachments for multimodal LLM
    image_attachments = []
    has_video = False
    for att in attachments:
        if att.get("type") == "image":
            image_attachments.append({
                "base64": att.get("content", ""),
                "mime_type": att.get("meta", {}).get("mime_type", "image/jpeg"),
            })
        elif att.get("type") == "video":
            has_video = True

    # If video is present, respond with transfer-to-human message
    if has_video:
        video_msg = "已收到您上传的视频文件。由于当前暂不支持视频内容自动分析，已为您转接人工客服，客服人员将尽快为您处理。"
        return {
            "answer": video_msg,
            "confidence": 0.9,
            "need_human": True,
            "transfer_reason": "video_attachment",
        }

    # TODO: Replace with actual LLM call via Model Center
    answer = ""
    confidence = state.get("confidence", 0.5)

    try:
        from app.models_center.service import ModelService
        model_service = ModelService()

        # If image attachments present, use multimodal chat
        if image_attachments:
            response = await model_service.chat_with_images(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                images=image_attachments,
                conversation_history=conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
                model_config_id=model_config_id,
            )
        else:
            response = await model_service.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                conversation_history=conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
                model_config_id=model_config_id,
            )
        answer = response.get("content", "")
        confidence = max(confidence, response.get("confidence", 0.7))
    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        answer = "抱歉，我暂时遇到了一些问题，正在为您转接人工客服，请稍等。"
        confidence = 0.3
        return {
            "answer": answer,
            "confidence": confidence,
            "need_human": True,
            "transfer_reason": "llm_error",
        }

    # Check if answer indicates knowledge insufficiency
    need_human = False
    transfer_reason = None

    if knowledge_context == "" and intent in ["product_info", "product_compare", "purchase_advice"]:
        need_human = True
        transfer_reason = "knowledge_missing"

    # Complaints should always be transferred to human
    if intent == "complaint":
        need_human = True
        transfer_reason = "complaint"

    logger.info(f"LLM response generated | confidence={confidence} need_human={need_human}")

    return {
        "answer": answer,
        "confidence": confidence,
        "need_human": need_human,
        "transfer_reason": transfer_reason,
    }


# --- Human Transfer Node ---

async def human_node(state: AgentState) -> Dict[str, Any]:
    """Handle transfer to human customer service.

    Creates a HumanTask (ticket) in the database with full context,
    including the user's message, intent, confidence, and the AI's
    preliminary answer (if any). Returns a message with the ticket number.
    """
    user_input = state.get("user_input", "")
    intent = state.get("intent", "unknown")
    confidence = state.get("confidence", 0.0)
    transfer_reason = state.get("transfer_reason", "low_confidence")
    conversation_id = state.get("conversation_id")
    agent_id = state.get("agent_id")
    user_id = state.get("user_id")
    trace_id = state.get("trace_id")
    agent_answer = state.get("answer", "")

    logger.info(
        f"Transferring to human | reason={transfer_reason} intent={intent} "
        f"confidence={confidence} conversation={conversation_id}"
    )

    try:
        from app.human_center.service import HumanCenterService
        hc_service = HumanCenterService()

        task = await hc_service.create_task(
            conversation_id=conversation_id,
            agent_id=agent_id,
            user_id=user_id,
            user_message=user_input,
            intent=intent,
            confidence=confidence,
            transfer_reason=transfer_reason,
            trace_id=trace_id,
            agent_answer=agent_answer,
        )

        ticket_number = task.ticket_number
        logger.info(f"Human task created: {ticket_number}")

        # Build the final answer: include AI's preliminary answer + transfer notice
        if agent_answer:
            answer = (
                f"{agent_answer}\n\n---\n"
                f"已为您创建人工客服工单（工单号：{ticket_number}），"
                f"客服人员将尽快为您处理。感谢您的耐心等待！"
            )
        else:
            answer = (
                f"已为您创建人工客服工单（工单号：{ticket_number}），"
                f"客服人员将尽快为您处理。感谢您的耐心等待！"
            )

        return {
            "answer": answer,
            "need_human": True,
            "transfer_reason": transfer_reason,
            "ticket_number": ticket_number,
        }

    except Exception as e:
        logger.error(f"Failed to create human task: {e}", exc_info=True)
        # Fallback: still transfer, just without a ticket
        answer = (
            f"{agent_answer}\n\n已为您转接人工客服，请稍等。"
            if agent_answer
            else "已为您转接人工客服，请稍等。"
        )
        return {
            "answer": answer,
            "need_human": True,
            "transfer_reason": transfer_reason,
        }
