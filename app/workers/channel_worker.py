"""
Channel message pump worker: connects IM channels (Feishu / DingTalk / WeCom)
to the standard agent conversation pipeline.

Usage (long-running process, like the multimodal worker):
    python -m app.workers.channel_worker

Flow per inbound message:
  Redis dedup -> load channel & agent -> map (channel, user, chat) to a
  platform conversation (30min session window) -> AgentRuntime.run ->
  save messages -> reply via channel adapter.
"""

import asyncio
import logging
import signal
import threading
from typing import Dict, Optional

import app.models  # noqa: F401  # register all models with Base.metadata
from app.channels import InboundMessage, create_adapter
from app.core.timeutils import now
from app.database.redis_client import redis_client
from app.database.session import async_session_factory
from app.repositories.channel_repo import (
    find_fresh_channel_conversation,
    get_channel,
    list_active_channels,
    upsert_channel_conversation,
)
from app.repositories.conversation_repo import (
    create_conversation,
    get_recent_history,
    save_message,
    update_conversation_status,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("channel-worker")

RECONCILE_INTERVAL_SECONDS = 60
DEDUP_TTL_SECONDS = 300


def _dedup_key(msg: InboundMessage) -> str:
    return f"ch:msg:{msg.channel_id}:{msg.message_id}"


class ChannelWorker:
    """Runs one WS thread per active channel; reconciles channel list periodically."""

    def __init__(self):
        self._threads: Dict[int, threading.Thread] = {}
        self._adapters: Dict[int, any] = {}
        self._stopping = False

    # --- message pipeline ---

    async def handle_message(self, msg: InboundMessage) -> None:
        # 1. Dedup (Feishu may redeliver events)
        try:
            if not await redis_client.set(
                _dedup_key(msg), 1, ex=DEDUP_TTL_SECONDS, nx=True
            ):
                logger.info(f"Duplicated message ignored: {msg.message_id}")
                return
        except Exception as e:
            logger.warning(f"Redis dedup unavailable ({e}); processing anyway")

        # 2. Load channel + agent state
        adapter = self._adapters.get(msg.channel_id)
        if adapter is None:
            logger.warning(f"Message from unknown channel {msg.channel_id}")
            return

        try:
            async with async_session_factory() as db:
                from app.models.agent import Agent

                channel = await get_channel(db, msg.channel_id)
                if channel is None or not channel.is_active:
                    return
                agent = await db.get(Agent, channel.agent_id)
                if agent is None or not agent.is_active or agent.status == "archived":
                    logger.warning(f"Agent {channel.agent_id} inactive; message dropped")
                    return

                # 3. Non-text messages: friendly notice
                if not msg.text:
                    await adapter.send_text(
                        msg.external_chat_id,
                        "暂时只支持文字消息哦，发段文字给我试试～",
                    )
                    return

                # 4. Map to a platform conversation (30min session window)
                platform_uid = await self._resolve_channel_user(db, channel, msg.external_user_id)
                mapping = await find_fresh_channel_conversation(
                    db,
                    channel.id,
                    external_user_id=msg.external_user_id,
                    external_chat_id=msg.external_chat_id,
                )
                external_uid = f"{channel.channel_type}:{msg.external_user_id}"
                new_conversation = False

                if mapping is None:
                    conv = await create_conversation(
                        db,
                        user_id=platform_uid,
                        agent_id=channel.agent_id,
                        title=msg.text[:50] or "IM 会话",
                        meta={
                            "external_user_id": external_uid,
                            "channel_id": channel.id,
                            "channel_type": channel.channel_type,
                        },
                    )
                    conversation_id = conv.id
                    new_conversation = True
                    await upsert_channel_conversation(
                        db,
                        channel_id=channel.id,
                        external_user_id=msg.external_user_id,
                        external_chat_id=msg.external_chat_id,
                        conversation_id=conversation_id,
                    )
                else:
                    conversation_id = mapping.conversation_id
                    if not await self._conversation_exists(db, conversation_id):
                        conv = await create_conversation(
                            db,
                            user_id=platform_uid,
                            agent_id=channel.agent_id,
                            title=msg.text[:50] or "IM 会话",
                            meta={
                                "external_user_id": external_uid,
                                "channel_id": channel.id,
                                "channel_type": channel.channel_type,
                            },
                        )
                        conversation_id = conv.id
                        new_conversation = True
                        await upsert_channel_conversation(
                            db,
                            channel_id=channel.id,
                            external_user_id=msg.external_user_id,
                            external_chat_id=msg.external_chat_id,
                            conversation_id=conversation_id,
                        )

                # 5. Save user message + history
                user_msg = await save_message(db, conversation_id, "user", platform_uid, msg.text)
                history_msgs = await get_recent_history(
                    db, conversation_id, before_msg_id=user_msg.id, limit=10
                )
                conversation_history = [
                    {"role": "user" if m.sender_type == "user" else "assistant", "content": m.content}
                    for m in history_msgs
                ]
                await db.commit()

                # 6. Run the standard agent pipeline
                from app.runtime.context import AgentContext
                from app.runtime.executor import AgentRuntime

                context = AgentContext(
                    user_id=platform_uid,
                    conversation_id=conversation_id,
                    agent_id=channel.agent_id,
                )
                runtime = AgentRuntime()
                result = await runtime.run(
                    msg.text,
                    context,
                    conversation_history=conversation_history,
                )
                answer = result.get("answer", "抱歉，我暂时无法处理这条消息。")

                agent_msg = await save_message(
                    db, conversation_id, "agent", channel.agent_id, answer,
                    meta={
                        "intent": result.get("intent"),
                        "confidence": result.get("confidence"),
                        "trace_id": result.get("trace_id"),
                        "need_human": result.get("need_human", False),
                        "channel": channel.channel_type,
                    },
                )
                await update_conversation_status(
                    db,
                    await self._get_conversation(db, conversation_id),
                    message_count_delta=2,
                    is_transferred=result.get("need_human", False) or None,
                    transfer_reason=result.get("transfer_reason"),
                )
                await db.commit()

            # 7. Reply via the channel
            await adapter.send_text(msg.external_chat_id, answer)
            logger.info(
                f"Channel msg done | channel={msg.channel_id} user={msg.external_user_id[:10]} "
                f"conv={conversation_id} new={new_conversation} answer={answer[:40]}"
            )

        except Exception as e:
            logger.error(f"Failed to handle channel message: {e}", exc_info=True)
            try:
                await adapter.send_text(
                    msg.external_chat_id, "抱歉，处理消息时出错了，请稍后再试。"
                )
            except Exception:
                pass

    @staticmethod
    async def _conversation_exists(db, conversation_id: int) -> bool:
        from app.models.conversation import Conversation

        return await db.get(Conversation, conversation_id) is not None

    @staticmethod
    async def _resolve_channel_user(db, channel, external_user_id: str) -> int:
        """Find or create a placeholder platform user for an IM user.

        Mirrors resolve_chat_user() in the conversations endpoint: keeps FK
        relationships on conversations/memories valid while the real identity
        stays in the username.
        """
        from sqlalchemy import select
        from app.models.user import User

        username = f"channel_{channel.channel_type}_{external_user_id}"
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is not None:
            return user.id

        user = User(
            email=f"{username}@platform.local",
            username=username,
            hashed_password="!",
            full_name=f"IM 用户 {external_user_id[:12]}",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return user.id

    @staticmethod
    async def _get_conversation(db, conversation_id: int):
        from app.models.conversation import Conversation

        return await db.get(Conversation, conversation_id)

    # --- channel lifecycle ---

    def _start_channel_thread(self, channel) -> None:
        from app.channels.registry import create_adapter

        adapter = create_adapter(channel.id, channel.channel_type, channel.credentials)
        self._adapters[channel.id] = adapter

        def _run():
            try:
                adapter.start_receiving(self.handle_message, loop=self._loop)
            except Exception as e:
                logger.error(f"Channel {channel.id} ({channel.channel_type}) stopped: {e}")
                self._adapters.pop(channel.id, None)

        t = threading.Thread(target=_run, name=f"channel-{channel.id}", daemon=True)
        self._threads[channel.id] = t
        t.start()
        logger.info(f"Channel thread started | id={channel.id} type={channel.channel_type} name={channel.name}")

    def _stop_channel_thread(self, channel_id: int) -> None:
        adapter = self._adapters.pop(channel_id, None)
        if adapter:
            try:
                adapter.stop()
            except Exception:
                pass
        self._threads.pop(channel_id, None)

    async def _reconcile(self) -> None:
        """Sync running threads with active feishu channels in DB."""
        async with async_session_factory() as db:
            channels = await list_active_channels(db, channel_type="feishu")
        active_ids = {c.id for c in channels}

        # stop threads whose channel disappeared or was disabled
        for cid in list(self._threads.keys()):
            if cid not in active_ids:
                logger.info(f"Stopping channel thread {cid}")
                self._stop_channel_thread(cid)

        for channel in channels:
            if channel.id not in self._threads:
                creds_ok = bool((channel.credentials or {}).get("app_id"))
                if not creds_ok:
                    logger.warning(f"Channel {channel.id} missing credentials, skipped")
                    continue
                self._start_channel_thread(channel)
                asyncio.ensure_future(self._mark_connected(channel.id))

    async def _mark_connected(self, channel_id: int) -> None:
        try:
            async with async_session_factory() as db:
                from sqlalchemy import update
                from app.models.channel import AgentChannel

                await db.execute(
                    update(AgentChannel)
                    .where(AgentChannel.id == channel_id)
                    .values(last_connected_at=now(), last_error=None)
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Mark connected failed for {channel_id}: {e}")

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        logger.info("Channel worker starting...")
        await self._reconcile()

        async def _reconcile_loop():
            while not self._stopping:
                await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
                if not self._stopping:
                    try:
                        await self._reconcile()
                    except Exception as e:
                        logger.error(f"Reconcile failed: {e}")

        reconcile_task = asyncio.ensure_future(_reconcile_loop())

        stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_running_loop().add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass
        await stop_event.wait()
        reconcile_task.cancel()
        for cid in list(self._threads.keys()):
            self._stop_channel_thread(cid)
        logger.info("Channel worker stopped")


def main():
    worker = ChannelWorker()
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
