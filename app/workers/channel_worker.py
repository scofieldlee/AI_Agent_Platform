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
                channel = await get_channel(db, msg.channel_id)
                if channel is None or not channel.is_active:
                    return

                # 3. Non-text messages: friendly notice
                if not msg.text:
                    await adapter.send_text(
                        msg.external_chat_id,
                        "暂时只支持文字消息哦，发段文字给我试试～",
                    )
                    return

                # 4. Resolve IM user to a platform placeholder user
                platform_uid = await self._resolve_channel_user(db, channel, msg.external_user_id)

                # 5. Route by binding target
                if channel.target_type == "employee":
                    # Two-phase reply: ack immediately, result pushed on completion
                    await adapter.send_text(
                        msg.external_chat_id,
                        "已收到，正在为您分析处理（多 Agent 协同，预计 30~60 秒），完成后自动推送结果。",
                    )
                    answer = await self._run_employee_target(db, channel, adapter, msg, platform_uid)
                else:
                    answer = await self._run_agent_target(db, channel, adapter, msg, platform_uid)

            # 7. Reply via the channel
            await adapter.send_text(msg.external_chat_id, answer)
            logger.info(
                f"Channel msg done | channel={msg.channel_id} user={msg.external_user_id[:10]} "
                f"target={channel.target_type} answer={answer[:40]}"
            )

        except Exception as e:
            logger.error(f"Failed to handle channel message: {e}", exc_info=True)
            try:
                await adapter.send_text(
                    msg.external_chat_id, "抱歉，处理消息时出错了，请稍后再试。"
                )
            except Exception:
                pass

    async def _run_agent_target(self, db, channel, adapter, msg: InboundMessage, platform_uid: int) -> str:
        """Standard single-Agent pipeline (existing behavior)."""
        from app.models.agent import Agent

        agent = await db.get(Agent, channel.agent_id)
        if agent is None or not agent.is_active or agent.status == "archived":
            logger.warning(f"Agent {channel.agent_id} inactive; message dropped")
            return "该服务暂时不可用，请联系管理员。"

        # Map to a platform conversation (30min session window)
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

        # Save user message + history
        user_msg = await save_message(db, conversation_id, "user", platform_uid, msg.text)
        history_msgs = await get_recent_history(
            db, conversation_id, before_msg_id=user_msg.id, limit=10
        )
        conversation_history = [
            {"role": "user" if m.sender_type == "user" else "assistant", "content": m.content}
            for m in history_msgs
        ]
        await db.commit()

        # Run the standard agent pipeline
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
        return answer

    async def _run_employee_target(self, db, channel, adapter, msg: InboundMessage, platform_uid: int) -> str:
        """AI Employee team target: multi-phase reply with progress push.

        Phase 1 (caller): ack "已收到，正在处理".
        Phase 2 (here):   run the task in background; poll every few seconds
                          and push a progress line whenever a member step
                          completes; push the final summary when done.
        """
        from app.employee import service as employee_service
        from app.employee.runtime.executor import EmployeeRuntime
        from app.repositories import employee_repo
        from sqlalchemy import select
        from app.models.ai_employee import AIEmployeeTaskStep

        employee = await employee_service.get_published_employee(db, channel.employee_id)
        if employee is None:
            return "绑定的 AI 员工不可用，请联系管理员。"

        snapshot = await employee_service.build_snapshot(db, employee)

        # Validate member agents are still available (same guard as the API)
        from app.models.agent import Agent
        for agent_info in snapshot.get("agents", []):
            agent = await db.get(Agent, agent_info["agent_id"])
            if not agent or not agent.is_active:
                return f"团队成员「{agent_info.get('name', '?')}」已不可用，请联系管理员。"

        task = await employee_repo.create_task(
            db,
            employee_id=employee.id,
            user_id=platform_uid,
            title=msg.text[:100] or "IM 任务",
            input_data={"message": msg.text},
            employee_snapshot=snapshot,
            context={"artifacts": {}, "decisions": []},
            tenant_id=None,
        )
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        logger.info(
            f"Employee task created from IM | task={task_id} employee={employee.name} "
            f"conv_source={channel.channel_type}"
        )

        # Run to completion in the background; this coroutine polls progress
        runner = asyncio.create_task(EmployeeRuntime().run_task(task_id))

        async def _fetch_progress():
            async with async_session_factory() as db2:
                t = await employee_repo.get_task(db2, task_id)
                steps = (await db2.execute(
                    select(AIEmployeeTaskStep)
                    .where(AIEmployeeTaskStep.task_id == task_id)
                    .order_by(AIEmployeeTaskStep.id)
                )).scalars().all()
                return t, steps

        POLL_INTERVAL = 6
        MAX_WAIT_SECONDS = 480
        last_done = 0
        waited = 0

        while True:
            await asyncio.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL

            try:
                t, steps = await _fetch_progress()
            except Exception as e:
                logger.warning(f"Progress poll failed: {e}")
                continue

            status = t.status if t else "running"
            done = [s for s in steps if s.status == "completed"]

            # Progress push: a member step just completed
            if len(done) > last_done and status in ("running", "pending"):
                last_done = len(done)
                latest = done[-1]
                label = (getattr(latest, "role", None) or latest.step_key or "环节")[:20]
                try:
                    await adapter.send_text(
                        msg.external_chat_id,
                        f"⏳ 进度更新：已完成 {len(done)} 个环节（{label}），任务继续处理中…",
                    )
                except Exception as e:
                    logger.warning(f"Progress push failed: {e}")

            # Terminal states
            if status in ("completed", "failed", "cancelled"):
                if not runner.done():
                    await asyncio.wait_for(runner, timeout=10)
                break

            if waited >= MAX_WAIT_SECONDS:
                if not runner.done():
                    runner.cancel()
                    logger.warning(f"Employee task {task_id} exceeded {MAX_WAIT_SECONDS}s; cancelled")
                return "任务处理超时，已通知后台继续记录。请稍后重试或换个更具体的问题。"

        if status == "failed":
            logger.error(f"Employee task {task_id} failed")
            return "抱歉，本次任务处理失败，请稍后再试或换个问法。"
        if status == "cancelled":
            return "任务已取消。"

        result = t.result or {}
        summary = (result.get("summary") or "").strip()
        if not summary:
            # Fallback: last non-empty step output
            for step in reversed(steps):
                text = ""
                if isinstance(step, dict):
                    text = (step.get("output") or {}).get("summary") or ""
                elif getattr(step, "output", None):
                    text = (step.output or {}).get("summary") or ""
                if text and text.strip():
                    summary = text.strip()
                    break
        return summary or "任务已完成，但没有产生文字结果。"

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
