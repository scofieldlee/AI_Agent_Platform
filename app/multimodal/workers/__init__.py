"""Workers — 异步任务执行入口.

Worker 主循环: python -m app.multimodal.workers.task_worker
（task_queue_service 位于 app.multimodal.services，此处不做 re-export，
避免包初始化阶段的循环/错误导入。）
"""
