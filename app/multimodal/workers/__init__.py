"""Workers — 异步任务执行入口."""

from app.multimodal.workers import task_queue_service
from app.multimodal.workers.task_worker import main as run_worker

__all__ = ["task_queue_service", "run_worker"]
