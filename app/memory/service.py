"""
MemoryService: long-term memory management for agents.

Responsibilities:
1. Extract memories from conversations (LLM-powered analysis)
2. Store memories with embeddings for semantic search
3. Retrieve relevant memories using pgvector similarity
4. CRUD operations on memories

Architecture:
  Conversation -> Extract -> Store(with embedding) -> Retrieve(by query) -> Inject to LLM

Memory types: preference, fact, behavior, history
Lifecycle: active -> expired -> archived
"""

import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, text, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import async_session_factory
from app.models.memory import Memory
from app.core.config import settings

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing agent long-term memories.

    Usage:
        service = MemoryService()
        # Retrieve relevant memories before LLM
        memories = await service.retrieve_memories("用户问题", user_id=1, agent_id=1)
        # Extract and store after conversation
        await service.extract_and_store(user_input, answer, history, user_id=1, agent_id=1)
    """

    # Minimum importance score to include in retrieval results
    MIN_IMPORTANCE_THRESHOLD = 0.3
    # Maximum memories to retrieve per query
    DEFAULT_TOP_K = 5
    # Similarity score threshold for retrieval (BGE-small-zh gives lower scores for short texts)
    SIMILARITY_THRESHOLD = 0.15

    async def retrieve_memories(
        self,
        query: str,
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant memories using vector similarity search.

        Args:
            query: User's question (used for semantic search).
            user_id: Filter by user (scope memories to specific user).
            agent_id: Filter by agent.
            top_k: Max results.

        Returns:
            List of memory dicts: {id, content, memory_type, importance, score}
        """
        if top_k is None:
            top_k = self.DEFAULT_TOP_K

        logger.info(f"Retrieving memories | query={query[:50]}... user={user_id} agent={agent_id}")

        try:
            # 1. Embed the query
            from app.models_center.service import ModelService
            model_service = ModelService()
            query_embedding = await model_service.embed([query])
            query_vector = query_embedding[0]

            # 2. Vector search in memories table
            # Dynamic WHERE: only add user/agent filter if value is provided
            # (asyncpg can't infer type of NULL parameters)
            where_clauses = [
                "embedding IS NOT NULL",
                "status = 'active'",
                "importance >= :min_importance",
            ]
            params = {
                "query_vector": str(query_vector),
                "min_importance": self.MIN_IMPORTANCE_THRESHOLD,
                "top_k": top_k,
            }
            if user_id is not None:
                where_clauses.append("user_id = :user_id")
                params["user_id"] = user_id
            if agent_id is not None:
                where_clauses.append("agent_id = :agent_id")
                params["agent_id"] = agent_id

            sql = text(f"""
                SELECT id, content, memory_type, importance,
                       1 - (embedding <=> CAST(:query_vector AS vector)) as score
                FROM memories
                WHERE {" AND ".join(where_clauses)}
                ORDER BY embedding <=> CAST(:query_vector AS vector)
                LIMIT :top_k
            """)

            async with async_session_factory() as session:
                results = await session.execute(sql, params)
                rows = results.fetchall()

            # 3. Filter by similarity threshold and update access count
            memories = []
            memory_ids_to_update = []
            for row in rows:
                score = float(row.score) if row.score else 0.0
                if score < self.SIMILARITY_THRESHOLD:
                    continue

                memories.append({
                    "id": row.id,
                    "content": row.content,
                    "memory_type": row.memory_type,
                    "importance": float(row.importance),
                    "score": round(score, 4),
                })
                memory_ids_to_update.append(row.id)

            # 4. Update access count and last_accessed_at (non-blocking)
            if memory_ids_to_update:
                try:
                    async with async_session_factory() as session:
                        await session.execute(
                            update(Memory)
                            .where(Memory.id.in_(memory_ids_to_update))
                            .values(
                                access_count=Memory.access_count + 1,
                                last_accessed_at=datetime.utcnow().isoformat(),
                            )
                        )
                        await session.commit()
                except Exception as e:
                    logger.warning(f"Failed to update memory access count: {e}")

            logger.info(f"Memories retrieved: {len(memories)} results")
            return memories

        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}", exc_info=True)
            return []

    async def extract_and_store(
        self,
        user_input: str,
        agent_answer: str,
        conversation_history: List[Dict],
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Extract valuable memories from a conversation turn and store them.

        Uses LLM to analyze the conversation and identify information worth
        remembering long-term (preferences, facts, behaviors).

        Args:
            user_input: User's message.
            agent_answer: Agent's response.
            conversation_history: Previous messages for context.
            user_id, agent_id, conversation_id: Scope metadata.

        Returns:
            List of stored memories.
        """
        logger.info(f"Extracting memories | user={user_id} agent={agent_id} conv={conversation_id}")

        try:
            # 1. Use LLM to extract memories
            extracted = await self._llm_extract_memories(
                user_input, agent_answer, conversation_history
            )

            if not extracted:
                logger.info("No memories worth storing extracted")
                return []

            # 2. Store each memory with embedding
            stored = []
            for mem in extracted:
                memory = await self._store_memory(
                    content=mem["content"],
                    memory_type=mem.get("memory_type", "fact"),
                    importance=mem.get("importance", 0.5),
                    user_id=user_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                )
                if memory:
                    stored.append(memory)

            logger.info(f"Memories stored: {len(stored)} items")
            return stored

        except Exception as e:
            logger.error(f"Memory extraction failed: {e}", exc_info=True)
            return []

    async def _llm_extract_memories(
        self,
        user_input: str,
        agent_answer: str,
        conversation_history: List[Dict],
    ) -> List[Dict[str, Any]]:
        """Use LLM to analyze conversation and extract memorable information.

        Returns list of {content, memory_type, importance}.
        """
        # Build conversation context for the extraction prompt
        recent_context = ""
        if conversation_history:
            # Include last 4 messages for context
            recent = conversation_history[-4:]
            for msg in recent:
                role = "顾客" if msg.get("role") == "user" else "客服"
                recent_context += f"{role}: {msg.get('content', '')[:100]}\n"

        extraction_prompt = f"""分析以下对话，提取值得长期记忆的信息。

对话历史：
{recent_context if recent_context else "（无）"}

本轮对话：
顾客: {user_input}
客服: {agent_answer}

提取规则：
1. 只提取有长期价值的信息，不要记录临时性对话内容
2. 记忆类型：
   - preference: 顾客偏好（价格范围、品牌喜好、功能需求等）
   - fact: 重要事实（已购商品、使用场景、预算等）
   - behavior: 行为模式（常问某类问题、关注点等）
3. 如果没有值得记忆的信息，返回空数组 []
4. importance: 0.0-1.0，越高越重要

以JSON数组格式返回，每项包含 content, memory_type, importance：
[{{"content": "顾客偏好500元以下的无人机", "memory_type": "preference", "importance": 0.7}}]

只返回JSON，不要其他文字。"""

        try:
            from app.models_center.service import ModelService
            model_service = ModelService()
            response = await model_service.chat(
                system_prompt="你是一个信息提取助手，负责从对话中提取值得长期记忆的关键信息。只返回JSON。",
                user_prompt=extraction_prompt,
                temperature=0.1,
                max_tokens=512,
            )

            raw_output = response.get("content", "").strip()
            # Clean up markdown code blocks if present
            if raw_output.startswith("```"):
                raw_output = raw_output.split("\n", 1)[1] if "\n" in raw_output else raw_output[3:]
                if raw_output.endswith("```"):
                    raw_output = raw_output[:-3]
                raw_output = raw_output.strip()

            memories = json.loads(raw_output)

            if not isinstance(memories, list):
                return []

            # Validate and clean
            valid = []
            for m in memories:
                if not isinstance(m, dict) or not m.get("content"):
                    continue
                mem_type = m.get("memory_type", "fact")
                if mem_type not in ("preference", "fact", "behavior", "history"):
                    mem_type = "fact"
                importance = float(m.get("importance", 0.5))
                importance = max(0.0, min(1.0, importance))
                valid.append({
                    "content": str(m["content"])[:500],
                    "memory_type": mem_type,
                    "importance": importance,
                })

            return valid

        except json.JSONDecodeError as e:
            logger.warning(f"Memory extraction LLM output not valid JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"LLM memory extraction failed: {e}", exc_info=True)
            return []

    async def _store_memory(
        self,
        content: str,
        memory_type: str,
        importance: float,
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Store a single memory with its embedding."""
        try:
            # Generate embedding for the memory content
            from app.models_center.service import ModelService
            model_service = ModelService()
            embeddings = await model_service.embed([content])
            embedding = embeddings[0] if embeddings else None

            # Store in database
            async with async_session_factory() as session:
                memory = Memory(
                    user_id=user_id,
                    agent_id=agent_id,
                    memory_type=memory_type,
                    content=content,
                    importance=importance,
                    embedding=embedding,
                    meta={"conversation_id": conversation_id} if conversation_id else {},
                    status="active",
                    access_count=0,
                )
                session.add(memory)
                await session.commit()
                await session.refresh(memory)

                logger.info(f"Memory stored | id={memory.id} type={memory_type} importance={importance}")
                return {
                    "id": memory.id,
                    "content": content,
                    "memory_type": memory_type,
                    "importance": importance,
                }

        except Exception as e:
            logger.error(f"Failed to store memory: {e}", exc_info=True)
            return None

    @staticmethod
    def format_memory_context(memories: List[Dict[str, Any]]) -> str:
        """Format retrieved memories into a context string for LLM injection.

        Args:
            memories: List of memory dicts from retrieve_memories().

        Returns:
            Formatted context string, or empty string if no memories.
        """
        if not memories:
            return ""

        type_labels = {
            "preference": "偏好",
            "fact": "事实",
            "behavior": "行为",
            "history": "历史",
        }

        parts = []
        for m in memories:
            label = type_labels.get(m.get("memory_type", "fact"), "记忆")
            parts.append(f"- [{label}] {m['content']}（相关度 {m.get('score', 0):.0%}）")

        return "\n".join(parts)

    # --- CRUD for API ---

    async def list_memories(
        self,
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        memory_type: Optional[str] = None,
        status: str = "active",
        page: int = 1,
        size: int = 20,
    ) -> Dict[str, Any]:
        """List memories with pagination."""
        async with async_session_factory() as session:
            query = select(Memory).where(Memory.status == status)

            if user_id is not None:
                query = query.where(Memory.user_id == user_id)
            if agent_id is not None:
                query = query.where(Memory.agent_id == agent_id)
            if memory_type:
                query = query.where(Memory.memory_type == memory_type)

            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            # Paginate
            query = query.order_by(Memory.id.desc()).offset((page - 1) * size).limit(size)
            result = await session.execute(query)
            memories = result.scalars().all()

            return {
                "items": [
                    {
                        "id": m.id,
                        "user_id": m.user_id,
                        "agent_id": m.agent_id,
                        "memory_type": m.memory_type,
                        "content": m.content,
                        "importance": m.importance,
                        "status": m.status,
                        "access_count": m.access_count,
                        "last_accessed_at": m.last_accessed_at,
                        "meta": m.meta,
                        "created_at": m.created_at,
                    }
                    for m in memories
                ],
                "total": total,
                "page": page,
                "size": size,
            }

    async def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get a single memory by ID."""
        async with async_session_factory() as session:
            m = await session.get(Memory, memory_id)
            if not m:
                return None
            return {
                "id": m.id,
                "user_id": m.user_id,
                "agent_id": m.agent_id,
                "memory_type": m.memory_type,
                "content": m.content,
                "importance": m.importance,
                "status": m.status,
                "access_count": m.access_count,
                "last_accessed_at": m.last_accessed_at,
                "meta": m.meta,
                "created_at": m.created_at,
            }

    async def update_memory(
        self,
        memory_id: int,
        importance: Optional[float] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update memory importance or status."""
        async with async_session_factory() as session:
            m = await session.get(Memory, memory_id)
            if not m:
                return None

            if importance is not None:
                m.importance = max(0.0, min(1.0, importance))
            if status is not None:
                m.status = status

            await session.commit()
            await session.refresh(m)

            return {
                "id": m.id,
                "importance": m.importance,
                "status": m.status,
            }

    async def delete_memory(self, memory_id: int) -> bool:
        """Soft-delete memory (set status to 'archived')."""
        async with async_session_factory() as session:
            m = await session.get(Memory, memory_id)
            if not m:
                return False
            m.status = "archived"
            await session.commit()
            return True

    async def create_memory(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Manually create a memory (API endpoint)."""
        result = await self._store_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            user_id=user_id,
            agent_id=agent_id,
        )
        return result or {"error": "Failed to create memory"}
