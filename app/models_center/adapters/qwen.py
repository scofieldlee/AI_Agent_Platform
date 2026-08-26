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

import httpx
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
            or settings.dashscope_base_url
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_retries=2,
        )
        self.chat_model = model_id or "qwen-flash"
        self.reasoning_model = reasoning_model_id or self.chat_model
        self.embedding_model = "text-embedding-v4"

    @property
    def supports_vision(self) -> bool:
        """Whether this adapter's model supports image input (multimodal).

        - Qwen-VL series (qwen-vl-*): explicit vision models
        - Qwen3.x plus/max on Plan endpoint: natively multimodal
        """
        model = (self.chat_model or "").lower()
        return (
            "vl" in model
            or "omni" in model
            or ("plus" in model and "qwen3" in model)
            or ("max" in model and "qwen3" in model)
        )

    @property
    def supports_image_generation(self) -> bool:
        """Whether this adapter supports image generation.

        DashScope Tongyi Wanxiang (wan2.7-image / wan2.7-image-pro) is
        available on the OpenAI-compatible /images/generations endpoint.
        """
        return True

    @property
    def supports_video_generation(self) -> bool:
        """Whether this adapter supports video generation.

        Token Plan includes HappyHorse video models (happyhorse-1.1-t2v /
        happyhorse-1.1-i2v) served on the Plan video-synthesis endpoint.
        """
        return True

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Check if an error is worth retrying (transient/server-side)."""
        # Network-level timeouts (e.g. httpx.ReadTimeout on the rate-limited
        # Plan image endpoint, which allows ~1 request/minute)
        try:
            import httpx
            if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
                return True
        except ImportError:
            pass
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

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        model: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate images via DashScope.

        Token Plan users can generate images using Plan models such as
        ``qwen-image-3.0-pro`` / ``qwen-image-2.0`` / ``wan2.7-image`` /
        ``wan2.7-image-pro``. These models are billed against the Token Plan
        quota and must be called through the Plan multimodal-generation
        endpoint with the Plan API key.

        ``qwen-image-3.0-pro`` also supports image-to-image (I2I) editing:
        pass up to 3 reference images (base64 data URLs) via
        ``reference_images`` and they will be sent alongside the text prompt.

        For non-Plan models (e.g. ``wanx-v1``), fall back to the standard
        DashScope ``ImageSynthesis`` endpoint using the embedding/vision key.
        """
        # Prefer caller-supplied model; default to a Plan-supported image model.
        image_model = model or "qwen-image-3.0-pro"

        plan_image_models = {
            "qwen-image-2.0",
            "qwen-image-2.0-pro",
            "qwen-image-3.0-pro",
            "wan2.7-image",
            "wan2.7-image-pro",
        }

        if image_model in plan_image_models:
            return await self._generate_image_plan(
                prompt, size, n, image_model, reference_images,
            )

        # Fallback: standard DashScope ImageSynthesis endpoint
        return await self._generate_image_standard(prompt, size, n, image_model)

    async def _generate_image_plan(
        self,
        prompt: str,
        size: str,
        n: int,
        model: str,
        reference_images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Call the Token Plan multimodal-generation endpoint.

        Reference:
        https://platform.qianwenai.com/docs/token-plan/best-practices/multimodal-generation
        https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference
        """
        api_key = settings.dashscope_api_key
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY (Token Plan key) is required for Plan image generation")

        # Plan endpoint uses "1024*1024" style size notation.
        plan_size = size.replace("x", "*")

        # Build multimodal content: reference images (max 3) + text prompt.
        content: List[Dict[str, Any]] = []
        for ref in (reference_images or [])[:3]:
            if not ref:
                continue
            image_value = ref
            if not ref.startswith(("data:", "http://", "https://")):
                # Plain base64 -> wrap as data URL (DashScope requirement)
                image_value = f"data:image/png;base64,{ref}"
            content.append({"image": image_value})
        content.append({"text": prompt})

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": {"size": plan_size},
        }

        async def _do_post():
            # Plan image models are rate-limited (~1 req/min) and I2I can be
            # slow; use a generous timeout.
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        try:
            # Longer backoff for the rate-limited Plan image endpoint
            data = await self._call_with_retry(_do_post, max_retries=2, base_delay=30.0)
        except Exception as e:
            logger.error(f"Qwen Plan image generation failed: {e}", exc_info=True)
            raise

        output = data.get("output", {})
        choices = output.get("choices", [])
        images = []
        for choice in choices:
            message = choice.get("message", {})
            for item in message.get("content", []):
                image_url = item.get("image")
                if image_url:
                    images.append({
                        "url": image_url,
                        "b64_json": None,
                        "revised_prompt": None,
                    })

        if not images:
            # Some Plan models may return results under a different key; surface raw output for debugging.
            logger.warning(f"Plan image generation returned no image URLs. Response output: {output}")
            raise RuntimeError("Plan image generation returned no image URLs")

        # The Plan endpoint currently returns one image per request; honour `n` by limiting.
        if n and n > 0:
            images = images[:n]

        return {
            "images": images,
            "model": model,
            "prompt": prompt,
        }

    async def _generate_image_standard(
        self,
        prompt: str,
        size: str,
        n: int,
        model: str,
    ) -> Dict[str, Any]:
        """Generate images via the standard DashScope ImageSynthesis API."""
        from dashscope import ImageSynthesis

        # DashScope ImageSynthesis expects size like "1024*1024"
        dash_size = size.replace("x", "*")
        # Prefer the embedding/vision key (standard endpoint)
        api_key = settings.dashscope_embedding_api_key or settings.dashscope_api_key

        async def _do_call():
            return await asyncio.to_thread(
                ImageSynthesis.call,
                model=model,
                prompt=prompt,
                n=n,
                size=dash_size,
                api_key=api_key,
            )

        try:
            response = await self._call_with_retry(_do_call)
            output = getattr(response, "output", {}) or {}
            images = []
            for item in output.get("results", []):
                images.append({
                    "url": item.get("url") if isinstance(item, dict) else getattr(item, "url", None),
                    "b64_json": None,
                    "revised_prompt": None,
                })
            return {
                "images": images,
                "model": model,
                "prompt": prompt,
            }
        except Exception as e:
            logger.error(f"Qwen standard image generation failed: {e}", exc_info=True)
            raise

    async def generate_video(
        self,
        prompt: str,
        model: Optional[str] = None,
        resolution: str = "720P",
        ratio: str = "16:9",
        duration: int = 5,
        first_frame_image: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a video via the Token Plan video-synthesis endpoint.

        Uses Plan-included HappyHorse models, billed against the Token Plan
        quota (no extra per-second charges):

        - Text-to-video (T2V): ``happyhorse-1.1-t2v`` — prompt only.
        - Image-to-video (I2V): ``happyhorse-1.1-i2v`` — a single
          ``first_frame_image`` (base64 data URL or public URL) drives the
          first frame, with the text prompt steering the motion/content.

        The API is asynchronous: submit task (X-DashScope-Async) → poll
        ``GET /api/v1/tasks/{task_id}`` every 15s → fetch ``video_url``.
        Video URLs expire after 24 hours, so callers should download and
        persist the file immediately.

        Reference:
        https://platform.qianwenai.com/docs/token-plan/best-practices/multimodal-generation
        https://help.aliyun.com/zh/model-studio/happyhorse-image-to-video-api-reference
        """
        api_key = settings.dashscope_api_key
        if not api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY (Token Plan key) is required for Plan video generation"
            )
        if not api_key.startswith("sk-sp-"):
            logger.warning(
                "Video generation is using a non-Plan API key (%s...); "
                "this may incur charges outside the Token Plan.",
                api_key[:6],
            )

        # Model selection: explicit model wins; otherwise I2V when a first
        # frame is supplied, T2V for pure text prompts.
        if model:
            video_model = model
        elif first_frame_image:
            video_model = settings.qwen_video_i2v_model
        else:
            video_model = settings.qwen_video_t2v_model

        # Validate duration ([3, 15] seconds per API spec)
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = 5
        duration = max(3, min(15, duration))

        payload: Dict[str, Any] = {
            "model": video_model,
            "input": {"prompt": prompt},
            "parameters": {
                "resolution": resolution,
                "duration": duration,
            },
        }

        if first_frame_image:
            image_value = first_frame_image
            if not first_frame_image.startswith(("data:", "http://", "https://")):
                # Plain base64 -> data URL (API requirement)
                image_value = f"data:image/png;base64,{first_frame_image}"
            payload["input"]["media"] = [
                {"type": "first_frame", "url": image_value}
            ]
            # I2V output ratio follows the first frame; ratio param only
            # applies to text-to-video.
        else:
            payload["parameters"]["ratio"] = ratio

        submit_url = (
            "https://token-plan.cn-beijing.maas.aliyuncs.com"
            "/api/v1/services/aigc/video-generation/video-synthesis"
        )
        poll_base = "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/tasks"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        # 1. Submit the async task
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await self._call_with_retry(
                lambda: self._post_json(client, submit_url, headers, payload),
                max_retries=2,
                base_delay=10.0,
            )
            task_id = (resp.get("output") or {}).get("task_id")
            if not task_id:
                raise RuntimeError(
                    f"Video generation task submission failed: {resp}"
                )
            logger.info(
                f"Video task submitted | model={video_model} task_id={task_id} "
                f"resolution={resolution} duration={duration}s "
                f"first_frame={'yes' if first_frame_image else 'no'}"
            )

        # 2. Poll for completion
        video_url = await self._poll_video_task(
            client_factory=lambda: httpx.AsyncClient(timeout=60),
            poll_url=f"{poll_base}/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        return {
            "videos": [{"url": video_url}],
            "task_id": task_id,
            "model": video_model,
            "prompt": prompt,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "first_frame_used": bool(first_frame_image),
        }

    @staticmethod
    async def _post_json(
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """POST JSON and raise on HTTP errors (retry-friendly)."""
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    async def _poll_video_task(
        self,
        client_factory,
        poll_url: str,
        headers: Dict[str, str],
    ) -> str:
        """Poll an async video task until SUCCEEDED/FAILED/timeout.

        Status flow: PENDING → RUNNING → SUCCEEDED / FAILED.
        Returns the video URL on success.
        """
        poll_interval = settings.qwen_video_poll_interval_seconds
        max_wait = settings.qwen_video_max_wait_seconds
        elapsed = 0
        consecutive_errors = 0

        async with client_factory() as client:
            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    response = await client.get(poll_url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    consecutive_errors = 0
                except Exception as e:
                    # Transient poll errors shouldn't abort the flow — the
                    # task keeps running server-side; just retry next cycle.
                    consecutive_errors += 1
                    logger.warning(
                        f"Video task poll failed ({consecutive_errors}x, "
                        f"elapsed={elapsed}s): {type(e).__name__}: {str(e)[:120]}"
                    )
                    if consecutive_errors >= 5:
                        raise RuntimeError(
                            f"Video task polling failed repeatedly: {e}"
                        )
                    continue

                output = data.get("output") or {}
                status = output.get("task_status")

                if status == "SUCCEEDED":
                    video_url = output.get("video_url")
                    if not video_url:
                        raise RuntimeError(
                            f"Video task SUCCEEDED but no video_url returned: {output}"
                        )
                    logger.info(
                        f"Video task completed after ~{elapsed}s | url={video_url[:80]}..."
                    )
                    return video_url

                if status in ("FAILED", "CANCELED", "UNKNOWN"):
                    raise RuntimeError(
                        f"Video generation task {status}: "
                        f"code={output.get('code')} message={output.get('message')}"
                    )

                logger.debug(f"Video task pending | status={status} elapsed={elapsed}s")

        raise RuntimeError(
            f"Video generation timed out after {max_wait}s (task still not finished)"
        )
