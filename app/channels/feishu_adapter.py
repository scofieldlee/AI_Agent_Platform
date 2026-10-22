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
        # P2: callback handler injected by the worker (set_card_action_handler)
        self._card_action_handler = None
        self._loop = None
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
        self._loop = loop
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

        card_handler = None
        encrypt_key, verify_token = self._card_secret()
        if self._card_action_handler and encrypt_key and verify_token:
            def _on_card_action(data):
                """Card button callback → platform action → respond with a card."""
                try:
                    result = self._dispatch_card_action(data)
                    return result  # dict card JSON or None
                except Exception:
                    logger.exception("Feishu card action failed")
                    return None

            card_handler = (
                lark.CardActionHandler.builder(encrypt_key, verify_token)
                .register(_on_card_action)
                .build()
            )
            logger.info(f"Feishu card actions enabled | channel_id={self.channel_id}")

        # 卡片回调回调必须在构造 ws.Client 时传入。
        # 部分 lark-oapi 版本（如 1.7.3）的 Client.__init__ 尚未支持 card_handler
        # 关键字，直接传参会抛 TypeError 导致渠道启动即崩，故做能力探测 + 降级。
        client_kwargs: Dict[str, Any] = {
            "event_handler": handler,
            "log_level": lark.LogLevel.DEBUG,  # 联调期：DEBUG 观察事件帧
        }
        if card_handler is not None:
            client_kwargs["card_handler"] = card_handler
        try:
            self._ws_client = lark.ws.Client(self._app_id, self._app_secret, **client_kwargs)
        except TypeError as e:
            if "card_handler" not in client_kwargs:
                raise
            logger.warning(
                f"lark-oapi 当前版本不支持 ws.Client(card_handler=...)，"
                f"降级为无卡片回调模式：{e}"
            )
            client_kwargs.pop("card_handler", None)
            self._ws_client = lark.ws.Client(self._app_id, self._app_secret, **client_kwargs)
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

    async def send_rich(self, external_chat_id: str, msg: "RichMessage") -> None:
        """Send an interactive card (markdown body + link buttons)."""
        from app.channels.feishu_card import render_feishu_card

        token = await self._get_tenant_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{FEISHU_BASE_URL}/open-apis/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": external_chat_id,
                    "msg_type": "interactive",
                    "content": render_feishu_card(msg),
                },
            )
            data = resp.json()
        if data.get("code") != 0:
            logger.error(f"Feishu card send failed: code={data.get('code')} msg={data.get('msg')}")
            raise RuntimeError(f"飞书卡片发送失败: {data.get('msg')}")
        # P2: return message_id so callers can update the card later
        return (data.get("data") or {}).get("message_id")
    async def update_card(self, message_id: str, msg) -> None:
        """Update an existing interactive card (Feishu PATCH). Used for
        progressive updates (e.g. AI employee task progress) without spamming."""
        from app.channels.feishu_card import render_feishu_card

        token = await self._get_tenant_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                f"{FEISHU_BASE_URL}/open-apis/im/v1/messages/{message_id}",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "msg_type": "interactive",
                    "content": render_feishu_card(msg),
                },
            )
            data = resp.json()
        if data.get("code") != 0:
            logger.warning(f"Feishu card update failed: code={data.get('code')} msg={data.get('msg')}")

    def _card_secret(self) -> tuple:
        """(encrypt_key, verification_token) from credentials; empty = disabled."""
        c = self.credentials or {}
        return c.get("card_encrypt_key", ""), c.get("card_verification_token", "")
        if data.get("code") != 0:
            logger.error(f"Feishu send failed: code={data.get('code')} msg={data.get('msg')}")
            raise RuntimeError(f"飞书消息发送失败: {data.get('msg')}")

    def set_card_action_handler(self, handler) -> None:
        """Inject the worker's card-action callback (async fn(channel, payload, sig, chat_id, user_id))."""
        self._card_action_handler = handler

    def _dispatch_card_action(self, data):
        """Parse a card.action.trigger event, verify, and dispatch to the
        injected async handler. Returns the response card (dict) or None."""
        import json as _json

        def _get(obj, *names):
            for n in names:
                v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
                if v is not None:
                    return v
            return None

        action_data = _get(data, "action") or {}
        value = _get(action_data, "value") or {}
        if isinstance(value, str):
            try:
                value = _json.loads(value)
            except Exception:
                value = {}
        action = value.get("action")
        if not action:
            return None

        context = _get(data, "context") or {}
        chat_id = _get(context, "open_chat_id") or ""
        operator = _get(data, "operator") or {}
        open_id = _get(operator, "open_id") or ""
        open_message_id = _get(data, "open_message_id") or ""

        if self._card_action_handler is None:
            return None

        # Dispatch async; the handler returns a response card dict (or None)
        fut = asyncio.run_coroutine_threadsafe(
            self._card_action_handler(chat_id, open_id, open_message_id, value),
            self._loop,
        )
        try:
            return fut.result(timeout=25)
        except Exception:
            logger.exception("Card action handler timeout/error")
            return None

    def stop(self) -> None:
        self._stop_event.set()
