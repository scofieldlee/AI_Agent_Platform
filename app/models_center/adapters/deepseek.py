"""
DeepSeek model adapter.
DeepSeek API is OpenAI-compatible, uses the openai client library.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncOpenAI

from app.models_center.adapters.base import BaseModelAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class DeepSeekAdapter(BaseModelAdapter):
    """Adapter for DeepSeek API.

    Models:
    - deepseek-chat: General chat model (fast, cost-effective)
    - deepseek-reasoner: Reasoning model (for complex problems)
    - text-embedding-v3: Embedding model (via separate endpoint)

    Note: DeepSeek embedding API may use a different endpoint.
    For MVP, we use a compatible embedding service.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: Optional[str] = None,
        reasoning_model_id: Optional[str] = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.deepseek_api_key,
            base_url=base_url or settings.deepseek_base_url,
            max_retries=2,
        )
        self.chat_model = model_id or settings.chat_model
        self.reasoning_model = reasoning_model_id or settings.reasoning_model
        self.embedding_model = settings.embedding_model

    @property
    def supports_vision(self) -> bool:
        """Whether this adapter's model supports image input (multimodal).

        DeepSeek-Chat and DeepSeek-Reasoner are text-only models.
        Override in a vision-capable adapter (e.g., OpenAI GPT-4o adapter).
        """
        return False

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Check if an error is worth retrying (transient/server-side)."""
        status_code = getattr(error, "status_code", None)
        if status_code in (429, 500, 502, 503, 504):
            return True
        err_str = str(error).lower()
        if "service_unavailable" in err_str or "rate_limit" in err_str or "timeout" in err_str:
            return True
        return False

    async def _call_with_retry(self, func, *args, max_retries: int = 3, base_delay: float = 1.0, **kwargs):
        """Call an async function with exponential backoff retry on transient errors.

        Retries on 429/500/502/503/504 and timeout errors.
        Delay sequence: base_delay * (2^attempt) → 1s, 2s, 4s.
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if self._is_retryable(e) and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"DeepSeek transient error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.1f}s: {type(e).__name__}: {str(e)[:150]}"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = None,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Call DeepSeek chat API with automatic retry on transient errors."""
        if temperature is None:
            temperature = settings.chat_model_temperature

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_prompt})

        async def _do_call():
            return await self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        try:
            response = await self._call_with_retry(_do_call)

            return {
                "content": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": response.model,
            }
        except Exception as e:
            logger.error(f"DeepSeek chat failed after retries: {e}", exc_info=True)
            raise

    async def embed(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """DeepSeek does not provide an embedding API.

        Embeddings are handled by LocalEmbeddingAdapter (sentence-transformers).
        This method exists only to satisfy the BaseModelAdapter interface.
        """
        raise NotImplementedError(
            "DeepSeek does not support embeddings. "
            "Use LocalEmbeddingAdapter via ModelService.embed() instead."
        )

    async def chat_with_reasoning(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 8192,
    ) -> Dict[str, Any]:
        """Call DeepSeek reasoner model for complex tasks.

        The reasoner model provides chain-of-thought reasoning.
        Note: reasoning model does not support temperature parameter.
        """
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_prompt})

        try:
            response = await self._call_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.reasoning_model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
            )

            return {
                "content": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": response.model,
            }
        except Exception as e:
            logger.error(f"DeepSeek reasoning failed after retries: {e}", exc_info=True)
            raise

    async def chat_with_images(
        self,
        system_prompt: str,
        user_prompt: str,
        images: List[Dict[str, str]],
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Call chat API with image attachments (multimodal).

        Builds OpenAI-compatible multimodal messages with image_url content.

        Note: DeepSeek-Chat does NOT support images natively. This method
        exists for forward-compatibility — when a vision-capable model is
        configured via OpenAI-compatible API (e.g., GPT-4o, Qwen-VL),
        it will work. With DeepSeek, it will raise an API error which
        ModelService catches and falls back to text-only.

        Args:
            images: List of {base64, mime_type} dicts.
        """
        if temperature is None:
            temperature = settings.chat_model_temperature

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        # Build multimodal user message: text + images
        content_parts: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]

        for img in images:
            b64 = img.get("base64", "")
            mime = img.get("mime_type", "image/jpeg")
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}",
                },
            })

        messages.append({"role": "user", "content": content_parts})

        async def _do_call():
            return await self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        try:
            response = await self._call_with_retry(_do_call)

            return {
                "content": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": response.model,
            }
        except Exception as e:
            logger.error(f"Multimodal chat failed after retries: {e}", exc_info=True)
            raise
