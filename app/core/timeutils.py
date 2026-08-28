"""统一时区工具 — 全平台时间以「系统时区」为唯一口径。

背景
----
数据库列全部是 ``timestamptz``（``DateTime(timezone=True)``），存的是正确的瞬时值，
本身没有错。问题出在**输出**：asyncpg 读回的 datetime 一律带 UTC 时区，
Pydantic 再序列化成 ``2026-08-28T18:38:36.031102Z``，前端直接截断字符串显示，
于是界面上看到的比北京时间慢 8 小时。

约定
----
1. **写入**：一律用 :func:`now()`（带系统时区偏移的 aware datetime）。
   写进 timestamptz 后瞬时值不变，兼容历史数据。
2. **读出 / 输出**：一律用 :func:`local_iso` / :func:`to_local_naive`，
   或在 API 层交给 :class:`app.core.timezone_middleware.BeijingTimeMiddleware`
   统一改写（覆盖 Pydantic 序列化后的裸字典与响应模型两种出口）。
3. **输出格式**：不带时区偏移的本地墙钟时间 ``YYYY-MM-DDTHH:MM:SS[.ffffff]``。
   这样前端无论是字符串截断、``dayjs()`` 还是 ``toLocaleString()``，
   在任何浏览器时区下都会显示成北京时间，符合单时区企业系统的预期。

时间源始终是主机系统时钟（``datetime.now()`` / ``time.time()``），
时区偏移由 ``settings.app_timezone`` 决定（默认 Asia/Shanghai，填 auto 跟随主机）。
"""

from __future__ import annotations

import os
import time
from datetime import datetime, date, timedelta, timezone, tzinfo
from typing import Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

__all__ = [
    "APP_TZ",
    "APP_TZ_NAME",
    "app_timezone",
    "now",
    "now_naive",
    "to_local",
    "to_local_naive",
    "local_iso",
    "local_str",
    "from_timestamp",
    "today_str",
]

_FALLBACK_TZ = timezone(timedelta(hours=8))  # 兜底：tzdata 缺失时按 UTC+8 处理


def app_timezone() -> tzinfo:
    """解析并返回当前生效的时区对象。

    ``settings.app_timezone`` 为 ``auto`` / 空 / ``system`` 时跟随主机系统时区，
    否则按 IANA 名称（如 ``Asia/Shanghai``）解析；解析失败回退到 UTC+8。
    """
    name = (getattr(settings, "app_timezone", "") or "").strip()
    if not name or name.lower() in ("auto", "system", "local"):
        local = datetime.now().astimezone().tzinfo
        return local or _FALLBACK_TZ
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return _FALLBACK_TZ


def _tz_name(tz: tzinfo) -> str:
    name = (getattr(settings, "app_timezone", "") or "").strip()
    if not name or name.lower() in ("auto", "system", "local"):
        return str(tz) or "local"
    return name


APP_TZ: tzinfo = app_timezone()
APP_TZ_NAME: str = _tz_name(APP_TZ)


def now() -> datetime:
    """当前时间（aware，带系统时区偏移）。写入数据库统一用这个。"""
    return datetime.now(APP_TZ)


def now_naive() -> datetime:
    """当前时间（naive，系统时区的墙钟值）。"""
    return datetime.now(APP_TZ).replace(tzinfo=None)


def to_local(value: Optional[Union[datetime, date, str]]) -> Optional[datetime]:
    """把任意时间值转换为系统时区下的 aware datetime。

    - naive datetime：按系统时区解释（数据库里若存的是本地墙钟值也适用）
    - aware datetime：换算到系统时区
    - ``date``：补零时分秒
    - ``str``：尝试解析 ISO-8601
    - ``None``：原样返回
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=APP_TZ)
        return value.astimezone(APP_TZ)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=APP_TZ)
    return None


def to_local_naive(value: Optional[Union[datetime, date, str]]) -> Optional[datetime]:
    """转换为系统时区下的 naive datetime（去掉偏移，保留本地墙钟值）。"""
    converted = to_local(value)
    return converted.replace(tzinfo=None) if converted else None


def local_iso(value: Optional[Union[datetime, date, str]]) -> Optional[str]:
    """输出为不带偏移的本地时间 ISO 串，如 ``2026-08-29T02:38:36.031102``。

    用于手工拼 dict 的接口（绕过了 Pydantic 序列化）。
    """
    if value is None:
        return None
    if isinstance(value, str):
        converted = to_local(value)
        return converted.replace(tzinfo=None).isoformat() if converted else value
    if isinstance(value, datetime):
        converted = to_local(value)
        return converted.replace(tzinfo=None).isoformat() if converted else None
    if isinstance(value, date):
        return value.isoformat()
    return None


def local_str(value: Optional[Union[datetime, date, str]],
              fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[str]:
    """输出为指定格式的本地时间字符串。"""
    naive = to_local_naive(value)
    return naive.strftime(fmt) if naive else None


def from_timestamp(ts: float) -> datetime:
    """Unix 时间戳 → 系统时区 aware datetime（区别于 datetime.fromtimestamp 的主机本地时区）。"""
    return datetime.fromtimestamp(ts, tz=APP_TZ)


def ensure_process_timezone() -> str:
    """把进程默认时区设为 app_timezone。

    影响 ``time.localtime()`` / logging 时间戳 / ``datetime.now()``（naive）等
    直接依赖进程 TZ 的调用，让它们与 :data:`APP_TZ` 保持同一口径。
    主机时区本身就是目标时区时无需处理（配置 auto 时直接返回）。
    """
    name = (getattr(settings, "app_timezone", "") or "").strip()
    if not name or name.lower() in ("auto", "system", "local"):
        return "system"
    os.environ["TZ"] = name
    if hasattr(time, "tzset"):  # Windows 无 tzset
        time.tzset()
    return name


def today_str(fmt: str = "%Y%m%d") -> str:
    """当天日期串（系统时区口径）。"""
    return now().strftime(fmt)
