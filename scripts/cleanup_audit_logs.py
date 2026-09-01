#!/usr/bin/env python3
"""审计日志清理脚本 — 删除超过保留期的操作日志。

用法
----
    python scripts/cleanup_audit_logs.py            # 使用默认保留期（settings.audit_retention_days = 180）
    python scripts/cleanup_audit_logs.py --days 90  # 指定保留天数
    python scripts/cleanup_audit_logs.py --dry-run  # 只统计不删除

可挂到 crontab / 定时任务，例如每天凌晨执行一次：
    0 3 * * * cd /path/to/project && .venv/bin/python scripts/cleanup_audit_logs.py >> logs/audit-cleanup.log 2>&1
"""

import argparse
import asyncio
import logging
import os
import sys

# 允许从项目根直接运行
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("audit-cleanup")


async def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期的审计日志")
    parser.add_argument("--days", type=int, default=None,
                        help=f"保留天数（默认取 settings.audit_retention_days）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只统计将删除的条数，不实际删除")
    args = parser.parse_args()

    from app.core.config import settings
    from app.repositories import audit_repo
    from app.database.session import async_session_factory

    days = args.days or settings.audit_retention_days

    async with async_session_factory() as db:
        total = await audit_repo.count_audit_logs(db)
        logger.info(f"审计日志总数: {total}")

        if args.dry_run:
            # 仅统计超期条数
            from datetime import datetime, timedelta
            from sqlalchemy import select, func
            from app.models.audit_log import AuditLog

            cutoff = datetime.now().astimezone() - timedelta(days=days)
            expired = await db.scalar(
                select(func.count(AuditLog.id)).where(AuditLog.created_at < cutoff)
            ) or 0
            logger.info(f"[dry-run] 保留 {days} 天，将删除 {expired} 条（未执行）")
            return 0

        deleted = await audit_repo.delete_older_than(db, days)
        logger.info(f"已删除超过 {days} 天的审计日志: {deleted} 条")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
