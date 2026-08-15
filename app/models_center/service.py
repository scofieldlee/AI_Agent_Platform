"""
ModelService: unified entry point for all LLM operations.

Call chain: Agent -> ModelService -> Adapter -> Provider.

ModelService handles:
- Provider selection (Model Router)
- Fallback chain (if primary fails, try secondary)
- Token/cost logging
- Caching (Redis, future)

Architecture:
- Chat: DeepSeek (or other chat providers) via ChatAdapter
- Embedding: Local model (sentence-transformers) via EmbeddingAdapter
  Separated because some providers (e.g., DeepSeek) don't offer embeddings.
"""

import logging
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.models_center.adapters.base import BaseModelAdapter
from app.models_center.adapters.base_embedding import BaseEmbeddingAdapter

logger = logging.getLogger(__name__)


# Map provider code -> adapter class
ADAPTER_REGISTRY: Dict[str, Any] = {}


def _load_adapter_registry():
    """Lazy-load adapter classes."""
    global ADAPTER_REGISTRY
    if ADAPTER_REGISTRY:
        return

    try:
        from app.models_center.adapters.deepseek import DeepSeekAdapter
        ADAPTER_REGISTRY["deepseek"] = DeepSeekAdapter
    except Exception as e:
        logger.warning(f"Failed to load DeepSeek adapter: {e}")


def _mask_key(key: str) -> str:
    """Mask API key for logging."""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


class ModelService:
    """Unified model service for all LLM operations.

    Usage:
        service = ModelService()
        response = await service.chat(system_prompt, user_prompt)
        embeddings = await service.embed(["hello", "world"])
    """

    def __init__(self):
        self._chat_adapter: Optional[BaseModelAdapter] = None
        self._embedding_adapter: Optional[BaseEmbeddingAdapter] = None
        self._init_adapters()

    def _init_adapters(self):
        """Initialize default chat and embedding adapters.

        MVP:
        - Chat: DeepSeek (deepseek-chat / deepseek-reasoner)
        - Embedding: Local sentence-transformers (BAAI/bge-small-zh-v1.5)

        Future: Model Router selects based on task/cost/latency.
        """
        _load_adapter_registry()

        # Chat adapter — DeepSeek (default fallback)
        try:
            from app.models_center.adapters.deepseek import DeepSeekAdapter
            self._chat_adapter = DeepSeekAdapter()
            logger.info(f"Default chat adapter initialized: DeepSeek ({settings.chat_model})")
        except Exception as e:
            logger.error(f"Failed to init default chat adapter: {e}")
            self._chat_adapter = None

        # Embedding adapter — Local model
        try:
            from app.models_center.adapters.local_embedding import LocalEmbeddingAdapter
            self._embedding_adapter = LocalEmbeddingAdapter(
                model_name=settings.embedding_model,
            )
            logger.info(
                f"Embedding adapter initialized: {settings.embedding_model} "
                f"(dim={self._embedding_adapter.dimension})"
            )
        except Exception as e:
            logger.error(f"Failed to init embedding adapter: {e}")
            self._embedding_adapter = None

    async def _get_chat_adapter(
        self,
        model_config_id: Optional[int] = None,
    ) -> BaseModelAdapter:
        """Get chat adapter for the requested model config.

        If model_config_id is provided, load provider/config from DB and
        instantiate the appropriate adapter. Otherwise return the default.
        """
        if not model_config_id:
            if not self._chat_adapter:
                raise RuntimeError("No default chat adapter available")
            return self._chat_adapter

        from app.repositories.model_repo import get_model_config
        from app.database.session import async_session_factory

        async with async_session_factory() as db:
            config = await get_model_config(db, model_config_id)
            if not config:
                raise RuntimeError(f"Model config {model_config_id} not found")
            if not config.is_active:
                raise RuntimeError(f"Model config {model_config_id} is inactive")

            provider = config.provider
            if not provider or not provider.is_active:
                raise RuntimeError(f"Provider for config {model_config_id} is inactive")

            adapter_cls = ADAPTER_REGISTRY.get(provider.code)
            if not adapter_cls:
                raise RuntimeError(f"Unsupported provider: {provider.code}")

            adapter = adapter_cls(
                api_key=provider.api_key,
                base_url=provider.base_url,
                model_id=config.model_id,
            )
            logger.info(
                f"Dynamic chat adapter loaded | config_id={model_config_id} "
                f"provider={provider.code} model={config.model_id} "
                f"api_key={_mask_key(provider.api_key)}"
            )
            return adapter

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = None,
        max_tokens: int = 4096,
        model_config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a chat completion via the configured chat model.

        Args:
            model_config_id: Optional model config ID. If provided, uses that
                provider/model. Otherwise uses the default adapter.

        Returns:
            Dict with: content, prompt_tokens, completion_tokens, total_tokens, model, confidence
        """
        adapter = await self._get_chat_adapter(model_config_id)

        try:
            result = await adapter.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                conversation_history=conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Add confidence estimate (simplified: if we got a response, confidence is decent)
            result["confidence"] = 0.75 if result.get("content") else 0.3

            # TODO: Log to model_usage_logs table
            logger.info(
                f"Model usage | model={result.get('model')} "
                f"tokens={result.get('total_tokens')} "
                f"prompt={result.get('prompt_tokens')} "
                f"completion={result.get('completion_tokens')}"
            )

            return result

        except Exception as e:
            logger.error(f"Model chat failed: {e}", exc_info=True)
            # TODO: Implement fallback chain (DeepSeek -> OpenAI -> Claude)
            raise

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings via the configured embedding model.

        Used by Knowledge Center for document indexing and query embedding.
        Routes to LocalEmbeddingAdapter (sentence-transformers).
        """
        if not self._embedding_adapter:
            raise RuntimeError("No embedding adapter available")

        return await self._embedding_adapter.embed(texts)

    async def chat_with_reasoning(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        model_config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Use reasoning model for complex tasks (complaints, multi-step analysis).

        Routes to deepseek-reasoner which provides chain-of-thought.
        """
        adapter = await self._get_chat_adapter(model_config_id)

        # Check if adapter supports reasoning
        if hasattr(adapter, "chat_with_reasoning"):
            return await adapter.chat_with_reasoning(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                conversation_history=conversation_history,
            )

        # Fallback to regular chat
        logger.warning("Reasoning model not available, falling back to chat model")
        return await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            conversation_history=conversation_history,
            model_config_id=model_config_id,
        )

    async def chat_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        images: List[Dict[str, str]],
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = None,
        max_tokens: int = 4096,
        model_config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a chat completion with image attachments (multimodal).

        Args:
            system_prompt: System prompt defining agent behavior.
            user_prompt: User's text prompt.
            images: List of {base64, mime_type} dicts for each image.
            conversation_history: Previous messages.
            temperature: Sampling temperature.
            max_tokens: Max tokens to generate.
            model_config_id: Optional model config ID.

        Returns:
            Dict with: content, prompt_tokens, completion_tokens, total_tokens, model, confidence

        Note: Requires a vision-capable model. If the current chat adapter
        does not support images, falls back to text-only with a notice.
        """
        adapter = await self._get_chat_adapter(model_config_id)

        # Check if adapter supports vision
        if hasattr(adapter, "chat_with_images") and getattr(adapter, "supports_vision", False):
            try:
                result = await adapter.chat_with_images(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    images=images,
                    conversation_history=conversation_history,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                result["confidence"] = 0.75 if result.get("content") else 0.3
                logger.info(
                    f"Multimodal model usage | model={result.get('model')} "
                    f"images={len(images)} tokens={result.get('total_tokens')}"
                )
                return result
            except Exception as e:
                logger.error(f"Multimodal chat failed: {e}", exc_info=True)
                raise

        # Fallback: text-only with notice
        logger.warning(
            "Chat adapter does not support images, falling back to text-only. "
            "Configure a vision-capable model (e.g., GPT-4o, Qwen-VL) for image support."
        )
        notice = f"\n\n[注意: 收到 {len(images)} 张图片，但当前模型不支持图片识别。请配置支持视觉的模型。]"
        return await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt + notice,
            conversation_history=conversation_history,
            temperature=temperature,
            max_tokens=max_tokens,
            model_config_id=model_config_id,
        )
