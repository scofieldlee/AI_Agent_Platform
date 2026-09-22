"""
Feishu (Lark) channel adapter.

Receives messages via the official lark-oapi WebSocket long connection
(no public webhook needed) and replies via the im/v1/messages API.

Credentials: {"app_id": "cli_xxx", "app_secret": "xxx"}
"""

import asyncio
import json
import logging
import re
import threading
import time
from typing import Any, Dict, Optional

import httpx

from app.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

FEISHU_BASE_URL = "https://open.feishu.cn"
# Group text mentions appear as "@_user_1" placeholders in content.text
_MENTION_RE = re.compile(r"@_user_\d+")


def _strip_mentions(text: str) -> str:
    cleaned = _MENTION_RE.sub("", text or "")
    return cleaned.strip()


class FeishuAdapter(ChannelAdapter):
    channel_type = "feishu"

    def __init__(self, channel_id: int, credentials: Dict[str, Any]):
        super().__init__(channel_id, credentials)
        self._app_id: str = credentials.get("app_id", "")
        self._app_secret: str = credentials.get("app_secret", "")
        self._token: Optional[str] = None
        self._token_expire_at: float = 0.0
        self._ws_client: Optional[Any] = None
        self._stop_event = threading.Event()

    # --- Credential check / token ---

    async def _get_tenant_access_token(self) -> str:
        """Fetch and cache tenant_access_token (valid ~2h, refresh early)."""
        if self._token and time.time() < self._token_expire_at:
            return self._token
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书凭证校验失败: code={data.get('code')} msg={data.get('msg')}")
        self._token = data["tenant_access_token"]
        expire = data.get("expire", 7200)
        self._token_expire_at = time.time() + max(expire - 300, 60)
        return self._token

    async def test_credentials(self) -> Dict[str, Any]:
        if not self._app_id or not self._app_secret:
            return {"success": False, "detail": "缺少 app_id 或 app_secret"}
        try:
            await self._get_tenant_access_token()
            return {"success": True, "detail": "凭证有效，已获取 tenant_access_token"}
        except Exception as e:
            return {"success": False, "detail": str(e)}

    # --- Receiving (WS long connection) ---

    def start_receiving(self, on_message, loop=None) -> None:
        """Block on the WebSocket client loop. Run in a dedicated thread."""
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        except ImportError as e:
            raise RuntimeError("缺少 lark-oapi 依赖，请先安装: pip install lark-oapi") from e

        if loop is None:
            loop = asyncio.get_event_loop()
        self._stop_event.clear()

        def _on_event(data: P2ImMessageReceiveV1) -> None:
            try:
                msg = self._parse_event(data)
                if msg is not None:
                    asyncio.run_coroutine_threadsafe(on_message(msg), loop)
            except Exception:
                logger.exception("Feishu event parse failed")

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(_on_event)
            .build()
        )
        self._ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.DEBUG,  # 联调期：DEBUG 观察事件帧
        )
        logger.info(f"Feishu WS connecting | channel_id={self.channel_id}")
        # Blocking run; reconnects are handled by the SDK internally
        self._ws_client.start()

    def _parse_event(self, data: Any) -> Optional[InboundMessage]:
        event = getattr(data, "event", None)
        if event is None:
            return None
        message = getattr(event, "message", None)
        sender = getattr(event, "sender", None)
        if message is None or sender is None:
            return None

        # Ignore messages sent by the bot itself
        if getattr(sender, "sender_type", "") == "app":
            return None

        message_type = getattr(message, "message_type", "")
        if message_type != "text":
            # Non-text: deliver a notice so the user knows why there is no reply
            text = ""
        else:
            content = json.loads(message.content or "{}")
            text = _strip_mentions(content.get("text", ""))

        sender_id = getattr(sender, "sender_id", None)
        open_id = getattr(sender_id, "open_id", "") or ""

        return InboundMessage(
            channel_id=self.channel_id,
            message_id=getattr(message, "message_id", ""),
            external_user_id=open_id,
            external_chat_id=getattr(message, "chat_id", ""),
            chat_type=getattr(message, "chat_type", "p2p"),
            text=text,
            raw={"message_type": message_type},
        )

    # --- Sending ---

    async def send_text(self, external_chat_id: str, text: str) -> None:
        token = await self._get_tenant_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{FEISHU_BASE_URL}/open-apis/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": external_chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
            data = resp.json()
        if data.get("code") != 0:
            logger.error(f"Feishu send failed: code={data.get('code')} msg={data.get('msg')}")
            raise RuntimeError(f"飞书消息发送失败: {data.get('msg')}")

    def stop(self) -> None:
        self._stop_event.set()
