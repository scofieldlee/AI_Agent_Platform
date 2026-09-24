"""
DingTalk channel adapter (Stream mode).

Uses the official dingtalk-stream SDK: a WebSocket long connection that
receives bot messages WITHOUT a public webhook (same UX as Feishu).

Credentials: {"app_id": "<Client ID/AppKey>", "app_secret": "<Client Secret>"}

Replies: group → /v1.0/robot/groupMessages/send, p2p → /v1.0/robot/oToMessages/batchSend
(both keyed by robotCode == app_id for enterprise-internal apps).
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, Optional

import httpx

from app.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

DINGTALK_API = "https://api.dingtalk.com"


class DingTalkAdapter(ChannelAdapter):
    channel_type = "dingtalk"

    def __init__(self, channel_id: int, credentials: Dict[str, Any]):
        super().__init__(channel_id, credentials)
        self._client_id: str = credentials.get("app_id", "")
        self._client_secret: str = credentials.get("app_secret", "")
        self._token: Optional[str] = None
        self._token_expire_at: float = 0.0
        # conversationId -> {type, sender_id, webhook, robot_code}
        self._chat_meta: Dict[str, Dict[str, Any]] = {}
        self._stop_event = threading.Event()

    # --- Credential check / token ---

    async def _get_access_token(self) -> str:
        """Fetch and cache app access token (valid ~2h, refresh early)."""
        if self._token and time.time() < self._token_expire_at:
            return self._token
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{DINGTALK_API}/v1.0/oauth2/accessToken",
                json={"appKey": self._client_id, "appSecret": self._client_secret},
            )
            data = resp.json()
        if not data.get("accessToken"):
            raise RuntimeError(f"钉钉凭证校验失败: {data.get('message') or data}")
        self._token = data["accessToken"]
        expire = data.get("expireIn", 7200)
        self._token_expire_at = time.time() + max(expire - 300, 60)
        return self._token

    async def test_credentials(self) -> Dict[str, Any]:
        if not self._client_id or not self._client_secret:
            return {"success": False, "detail": "缺少 app_id（Client ID）或 app_secret（Client Secret）"}
        try:
            await self._get_access_token()
            return {"success": True, "detail": "凭证有效，已获取 access_token"}
        except Exception as e:
            return {"success": False, "detail": str(e)}

    # --- Receiving (Stream long connection) ---

    def start_receiving(self, on_message, loop=None) -> None:
        """Block on the Stream client loop. Run in a dedicated thread."""
        try:
            import dingtalk_stream
        except ImportError as e:
            raise RuntimeError("缺少 dingtalk-stream 依赖，请先安装: pip install dingtalk-stream") from e

        if loop is None:
            loop = asyncio.get_event_loop()
        self._stop_event.clear()

        outer = self

        class _BotHandler(dingtalk_stream.ChatbotHandler):
            async def process(self, callback):
                try:
                    data = getattr(callback, "data", None) or {}
                    msg = outer._parse_message(data)
                    if msg is not None:
                        asyncio.run_coroutine_threadsafe(on_message(msg), loop)
                except Exception:
                    logger.exception("DingTalk event parse failed")
                return dingtalk_stream.AckMessage.STATUS_OK, "OK"

        handler = _BotHandler()
        credential = dingtalk_stream.Credential(self._client_id, self._client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC, handler
        )
        logger.info(f"DingTalk Stream connecting | channel_id={self.channel_id}")
        # start() is a coroutine with an internal reconnect loop; run it on a
        # dedicated loop in this thread (blocks until stopped/crashed)
        asyncio.run(client.start())

    def _parse_message(self, data: Dict[str, Any]) -> Optional[InboundMessage]:
        """Normalize a ChatBotMessage into InboundMessage."""
        if not isinstance(data, dict):
            return None

        # Ignore messages sent by the bot itself
        if str(data.get("senderStaffId", "")) == str(data.get("robotCode", "")):
            return None

        conversation_id = data.get("conversationId", "")
        conversation_type = data.get("conversationType", "1")  # "1"=p2p, "2"=group
        text = (data.get("text") or {}).get("content", "").strip()

        # Group @mention: strip leading "@botname" tokens
        if conversation_type == "2":
            text = self._strip_at_mention(text, data)

        # Cache chat meta for replies (p2p needs senderStaffId, group needs conversationId)
        sender_id = data.get("senderStaffId") or data.get("senderId") or ""
        if conversation_id:
            self._chat_meta[conversation_id] = {
                "type": conversation_type,
                "sender_id": sender_id,
                "webhook": data.get("sessionWebhook", ""),
                "robot_code": data.get("robotCode") or self._client_id,
            }
            # Bound memory
            if len(self._chat_meta) > 200:
                self._chat_meta.pop(next(iter(self._chat_meta)))

        if not text:
            return InboundMessage(
                channel_id=self.channel_id,
                message_id=data.get("messageId", ""),
                external_user_id=sender_id,
                external_chat_id=conversation_id,
                chat_type="p2p" if conversation_type == "1" else "group",
                text="",
                raw={"message_type": data.get("msgtype", "")},
            )

        message_id = data.get("messageId", "")
        if not message_id:
            # Fingerprint for dedup when messageId missing
            import hashlib
            message_id = hashlib.md5(
                f"{conversation_id}:{sender_id}:{text}:{data.get('createAt', '')}".encode()
            ).hexdigest()

        return InboundMessage(
            channel_id=self.channel_id,
            message_id=message_id,
            external_user_id=sender_id,
            external_chat_id=conversation_id,
            chat_type="p2p" if conversation_type == "1" else "group",
            text=text,
            raw={"message_type": data.get("msgtype", "text")},
        )

    @staticmethod
    def _strip_at_mention(text: str, data: Dict[str, Any]) -> str:
        """Remove leading '@botname ' that DingTalk prepends in group @ messages."""
        cleaned = text.strip()
        bot_name = (data.get("chatbotUserName") or "").strip()
        if bot_name and cleaned.startswith(f"@{bot_name}"):
            cleaned = cleaned[len(bot_name) + 1:].strip()
        # Generic fallback: strip any leading @xxx token
        if cleaned.startswith("@"):
            parts = cleaned.split(" ", 1)
            cleaned = parts[1].strip() if len(parts) > 1 else ""
        return cleaned

    # --- Sending ---

    async def _api_send(self, path: str, body: Dict[str, Any]) -> None:
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{DINGTALK_API}{path}",
                headers={"x-acs-dingtalk-access-token": token},
                json=body,
            )
            data = resp.json()
        if resp.status_code >= 400:
            logger.error(f"DingTalk send failed via {path}: {data}")
            raise RuntimeError(f"钉钉消息发送失败: {data.get('message') or data}")

    async def send_text(self, external_chat_id: str, text: str) -> None:
        meta = self._chat_meta.get(external_chat_id)
        robot_code = (meta or {}).get("robot_code") or self._client_id
        msg_param = json.dumps({"content": text}, ensure_ascii=False)

        if meta and meta.get("type") == "2":
            # Group reply
            await self._api_send(
                "/v1.0/robot/groupMessages/send",
                {
                    "robotCode": robot_code,
                    "openConversationId": external_chat_id,
                    "msgKey": "sampleText",
                    "msgParam": msg_param,
                },
            )
        elif meta and meta.get("sender_id"):
            # P2P reply (requires senderStaffId)
            await self._api_send(
                "/v1.0/robot/oToMessages/batchSend",
                {
                    "robotCode": robot_code,
                    "userIds": [meta["sender_id"]],
                    "msgKey": "sampleText",
                    "msgParam": msg_param,
                },
            )
        elif meta and meta.get("webhook"):
            # Fallback: session webhook (per-message, always available)
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    meta["webhook"],
                    json={"msgtype": "text", "text": {"content": text}},
                )
            if resp.status_code >= 400:
                raise RuntimeError(f"钉钉 webhook 回复失败: {resp.text[:200]}")
        else:
            raise RuntimeError(f"无法回复：未知会话 {external_chat_id[:16]}（未收到过该会话的消息）")

    def stop(self) -> None:
        self._stop_event.set()
