"""
Qwen model adapter (Alibaba DashScope).

DashScope provides an OpenAI-compatible endpoint at:
    https://dashscope.aliyuncs.com/compatible-mode/v1

Registered under provider code "qwen" in the Model Center.
Vision-capable models (qwen-vl-*) support image input.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any

from openai import AsyncOpenAI

from app.models_center.adapters.base import BaseModelAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class QwenAdapter(BaseModelAdapter):
    """Adapter for Qwen models via DashScope OpenAI-compatible API.

    Models (examples):
    - qwen-flash / qwen-plus / qwen-max: text chat models
    - qwen-vl-plus / qwen-vl-max: vision-language models
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: Optional[str] = None,
        reasoning_model_id: Optional[str] = None,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.dashscope_api_key,
            base_url=base_url
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_retries=2,
        )
        self.chat_model = model_id or "qwen-flash"
        self.reasoning_model = reasoning_model_id or self.chat_model
        self.embedding_model = "text-embedding-v4"

    @property
    def supports_vision(self) -> bool:
        """Whether this adapter's model supports image input (multimodal).

        Qwen-VL series models support vision; plain text models do not.
        """
        model = (self.chat_model or "").lower()
        return "vl" in model or "omni" in model

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Check if an error is worth retrying (transient/server-side)."""
        status_code = getattr(error, "status_code", None)
        if status_code in (429, 500, 502, 503, 504):
            return True
        err_str = str(error).lower()
        if any(k in err_str for k in ("service_unavailable", "rate_limit", "timeout", "throttling")):
            return True
        return False

    async def _call_with_retry(self, func, *args, max_retries: int = 3, base_delay: float = 1.0, **kwargs):
        """Call an async function with exponential backoff retry on transient errors."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if self._is_retryable(e) and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Qwen transient error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.1f}s: {type(e).__name__}: {str(e)[:150]}"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error

    def _build_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_prompt})
        return messages

    @staticmethod
    def _parse_response(response) -> Dict[str, Any]:
        usage = getattr(response, "usage", None)
        return {
            "content": response.choices[0].message.content,
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
            "model": response.model,
        }

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = None,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Call Qwen chat API with automatic retry on transient errors."""
        if temperature is None:
            temperature = settings.chat_model_temperature

        messages = self._build_messages(system_prompt, user_prompt, conversation_history)

        async def _do_call():
            return await self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        try:
            response = await self._call_with_retry(_do_call)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Qwen chat failed after retries: {e}", exc_info=True)
            raise

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embedding via DashScope text-embedding (OpenAI-compatible)."""
        async def _do_call():
            return await self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )

        try:
            response = await self._call_with_retry(_do_call)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Qwen embedding failed after retries: {e}", exc_info=True)
            raise

    async def chat_with_reasoning(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        max_tokens: int = 8192,
    ) -> Dict[str, Any]:
        """Call Qwen for reasoning tasks (uses the same configured model)."""
        messages = self._build_messages(system_prompt, user_prompt, conversation_history)

        try:
            response = await self._call_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.reasoning_model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
            )
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Qwen reasoning failed after retries: {e}", exc_info=True)
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
        """Call chat API with image attachments (multimodal, Qwen-VL series)."""
        if temperature is None:
            temperature = settings.chat_model_temperature

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        if conversation_history:
            messages.extend(conversation_history)

        content_parts: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for img in images:
            b64 = img.get("base64", "")
            mime = img.get("mime_type", "image/jpeg")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
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
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Qwen multimodal chat failed after retries: {e}", exc_info=True)
            raise
