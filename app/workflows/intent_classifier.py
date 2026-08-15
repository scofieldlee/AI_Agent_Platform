"""
LLM-powered intent classifier for the customer service agent.

Replaces keyword-based matching with LLM classification for:
- Better accuracy on natural language (colloquial, ambiguous expressions)
- Context-aware classification using conversation history
- Entity extraction hints for downstream tools

Fallback: if LLM call fails, falls back to keyword-based matching.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classify user intent using LLM with keyword fallback.

    Usage:
        classifier = IntentClassifier()
        result = await classifier.classify(
            user_input="这东西能飞多久",
            conversation_history=[...],
        )
        # result = {"intent": "product_info", "confidence": 0.9, "reasoning": "..."}
    """

    # Intent definitions — used in the LLM prompt
    INTENT_DEFINITIONS = {
        "product_info": "顾客询问商品参数、功能、特点、价格、库存、规格、使用方法等信息",
        "product_compare": "顾客要求对比两个或多个商品的区别、优劣",
        "purchase_advice": "顾客请求推荐或建议合适的商品，描述自己的需求让客服推荐",
        "order_query": "顾客查询订单状态、物流进度、发货情况、快递单号、预计到达时间",
        "after_sale": "顾客咨询售后问题：退换货、退款、维修、保修、配件更换",
        "complaint": "顾客投诉、表达不满、情绪激动、要求投诉处理",
        "greeting": "顾客打招呼、寒暄、闲聊、感谢",
        "unknown": "无法归入以上任何类别的问题",
    }

    # Keyword fallback rules (used when LLM fails)
    KEYWORD_RULES = [
        (["价格", "多少钱", "参数", "规格", "介绍", "有货", "库存", "什么时候到货",
          "能飞", "续航", "电池", "速度", "多远", "多高", "重量", "材质",
          "price", "spec", "stock", "available"], "product_info"),
        (["对比", "比较", "区别", "哪个好", "compare", "difference"], "product_compare"),
        (["推荐", "建议", "适合", "选哪个", "recommend"], "purchase_advice"),
        (["订单", "物流", "发货", "到哪了", "快递", "查订单", "单号", "什么时候到",
          "啥时候到", "到货了吗", "寄出了吗", "order", "shipping", "delivery", "tracking"], "order_query"),
        (["退货", "退款", "售后", "维修", "保修", "换货", "坏了", "return", "refund", "warranty"], "after_sale"),
        (["投诉", "差评", "不满", "生气", "骗人", "complaint", "angry", "bad"], "complaint"),
        (["你好", "在吗", "谢谢", "感谢", "hello", "hi", "thanks"], "greeting"),
    ]

    async def classify(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Classify user intent using LLM.

        Args:
            user_input: The user's message.
            conversation_history: Previous messages [{role, content}] for context.

        Returns:
            Dict with: intent (str), confidence (float), reasoning (str)
        """
        try:
            result = await self._classify_with_llm(user_input, conversation_history)
            logger.info(
                f"Intent classified by LLM: {result['intent']} "
                f"(confidence={result['confidence']}) | input={user_input[:50]}"
            )
            return result
        except Exception as e:
            logger.warning(f"LLM intent classification failed, falling back to keywords: {e}")
            return self._classify_with_keywords(user_input)

    async def _classify_with_llm(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Use DeepSeek to classify intent. Returns structured JSON."""
        from app.models_center.service import ModelService

        # Build intent descriptions for the prompt
        intent_list = "\n".join(
            f"- {name}: {desc}"
            for name, desc in self.INTENT_DEFINITIONS.items()
        )

        # Build conversation context (last 4 messages, truncated)
        history_text = ""
        if conversation_history:
            recent = conversation_history[-4:]
            history_text = "\n".join(
                f"{'顾客' if msg.get('role') == 'user' else '客服'}: {msg.get('content', '')[:100]}"
                for msg in recent
            )

        system_prompt = f"""你是一个意图分类器。根据顾客的消息，判断其意图属于以下哪个类别：

{intent_list}

分类规则：
1. 优先根据当前消息判断，但可以参考对话历史理解指代（如"它""那个"指什么商品）
2. 如果顾客同时问多个问题（如"Q150多少钱？还有货吗"），选择最主要的意图
3. 如果顾客语气激动或表达不满，优先分类为 complaint
4. confidence 表示你对分类的把握：0.9+ 非常确定，0.7-0.9 较确定，0.5-0.7 不太确定
5. 只有完全无法理解时才分类为 unknown

你必须输出严格的 JSON 格式（不要加 markdown 代码块标记），格式如下：
{{"intent": "意图名称", "confidence": 0.0到1.0的数字, "reasoning": "简短理由"}}"""

        user_prompt = ""
        if history_text:
            user_prompt += f"对话历史：\n{history_text}\n\n"
        user_prompt += f"顾客消息：{user_input}\n\n请分类："

        model_service = ModelService()
        response = await model_service.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=256,
        )

        raw_output = response.get("content", "").strip()

        # Parse JSON from LLM response
        # Handle cases where LLM wraps in markdown code blocks
        raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
        raw_output = re.sub(r"\s*```$", "", raw_output)

        parsed = json.loads(raw_output)

        # Validate intent
        intent = parsed.get("intent", "unknown")
        if intent not in self.INTENT_DEFINITIONS:
            logger.warning(f"LLM returned unknown intent '{intent}', defaulting to 'unknown'")
            intent = "unknown"

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

        return {
            "intent": intent,
            "confidence": confidence,
            "reasoning": parsed.get("reasoning", ""),
        }

    def _classify_with_keywords(self, user_input: str) -> Dict[str, Any]:
        """Fallback: keyword-based intent classification.

        Used when LLM is unavailable. Less accurate but always works.
        """
        intent = "unknown"
        confidence = 0.5

        for keywords, matched_intent in self.KEYWORD_RULES:
            if any(kw in user_input for kw in keywords):
                intent = matched_intent
                confidence = 0.75
                break

        return {
            "intent": intent,
            "confidence": confidence,
            "reasoning": "keyword_fallback",
        }
