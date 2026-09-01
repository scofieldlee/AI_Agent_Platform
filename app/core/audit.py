"""审计核心：业务语义装饰器 + 敏感信息脱敏工具。

设计（与 docs/操作日志方案设计.md 对齐）
---------------------------------------
- 中间件负责"保底采集"：所有写操作 + GET 白名单，记录 request_id/IP/UA/耗时/状态码；
- 本模块的 ``@audit`` 装饰器负责"提升上限"：给关键操作补充 action/resource/名称快照/
  summary/变更 diff，写入 ``audit_enrichment_var``，由中间件在响应结束时合并落库。

脱敏
----
入库前按字段名黑名单 + 值特征（``sk-`` 开头的 Key）双重兜底，避免把密码/token
明文写进日志表。
"""

from __future__ import annotations

import inspect
import logging
import re
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, Union

from app.core.request_context import audit_enrichment_var

logger = logging.getLogger(__name__)

__all__ = [
    "audit",
    "sanitize_body",
    "SENSITIVE_FIELDS",
    "build_summary",
    "ACTION_LABELS",
    "RESOURCE_LABELS",
]

# --- 动作/资源中文标签（前端与 summary 复用） ---
ACTION_LABELS = {
    "create": "创建",
    "update": "修改",
    "delete": "删除",
    "login": "登录",
    "logout": "登出",
    "approve": "审核通过",
    "reject": "驳回",
    "export": "导出",
    "execute": "执行",
    "publish": "发布",
    "disable": "停用",
    "restore": "恢复",
    "upload": "上传",
    "set_default": "设为默认",
    "bind": "绑定",
    "regenerate": "重新生成",
}

# 资源类型中文标签（summary / 前端复用）
RESOURCE_LABELS = {
    "user": "用户",
    "role": "角色",
    "permission": "权限",
    "agent": "Agent",
    "workflow": "工作流",
    "knowledge": "知识库",
    "document": "文档",
    "chunk": "知识分块",
    "asset": "素材",
    "knowledge_base": "多模态知识库",
    "model_config": "模型配置",
    "provider": "模型供应商",
    "task": "处理任务",
    "tool": "工具",
    "conversation": "对话",
    "memory": "记忆",
    "employee": "AI 员工",
    "system": "系统",
}

# 动作→默认动作词（summary 用）
_ACTION_VERB = {
    "create": "创建",
    "update": "更新",
    "delete": "删除",
    "login": "登录",
    "logout": "登出",
    "approve": "审核通过",
    "reject": "驳回",
    "export": "导出",
    "execute": "执行",
    "publish": "发布",
    "disable": "停用",
    "restore": "恢复",
    "upload": "上传",
    "set_default": "设为默认",
    "bind": "绑定",
    "regenerate": "重新生成",
}

# 字段名黑名单：命中即整体脱敏为 "***"
SENSITIVE_FIELDS = {
    "password",
    "new_password",
    "old_password",
    "current_password",
    "confirm_password",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "auth_token",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "jwt_secret_key",
    "secret_key",
    "authorization",
    "cookie",
    "set_cookie",
    "private_key",
    "hashed_password",
    "credential",
    "credentials",
    "session_id",
    "x_api_key",
    "proxy_auth",
    "ssh_key",
    "signature",
    "verification_code",
    "sms_code",
    "otp",
    "mfa_code",
    "pin",
    "key",
    "token_secret",
}

# 值特征兜底：形如 sk-xxx 的 Key / Bearer token / JWT 三段的字符串
_VALUE_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*|"
    r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+)",
    re.IGNORECASE,
)


def sanitize_body(data: Any, depth: int = 0) -> Any:
    """递归脱敏请求体。

    - dict 的 key 命中敏感字段黑名单 → 值整体替换为 ``"***"``；
    - 字符串值命中 Key/JWT 特征 → 替换为 ``"***"``；
    - 递归深度保护（防止恶意深层嵌套）。
    """
    if depth > 8 or data is None:
        return data
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            key = str(k).lower()
            if key in SENSITIVE_FIELDS:
                out[k] = "***"
            else:
                out[k] = sanitize_body(v, depth + 1)
        return out
    if isinstance(data, list):
        return [sanitize_body(item, depth + 1) for item in data]
    if isinstance(data, str):
        if _VALUE_SECRET_RE.search(data):
            return _VALUE_SECRET_RE.sub("***", data)
        return data
    return data


def build_summary(action: str, resource_type: str, resource_name: Optional[str]) -> str:
    """根据动作/资源类型/名称拼人类可读的 summary。"""
    verb = _ACTION_VERB.get(action, action or "操作")
    label = RESOURCE_LABELS.get(resource_type or "", resource_type or "资源")
    if resource_name:
        return f"{verb}了{label} {resource_name}"
    return f"{verb}了{label}"


# --- @audit 装饰器 ---

# resource_id / resource_name / summary 允许：静态值，或 接收 ctx(dict) 的可调用对象
_Value = Union[str, int, Callable[[dict], Any]]
_Ctx = dict


async def _maybe_await(value: Any) -> Any:
    """兼容同步/异步可调用返回值。"""
    if inspect.isawaitable(value):
        return await value
    return value


def _resolve(value: _Value, ctx: _Ctx) -> Any:
    """把静态值或回调解析为实际值。"""
    if callable(value):
        try:
            return value(ctx)
        except TypeError:
            # 兼容回调只想取部分参数的情况
            return value
    return value


def _pick_path_param(kwargs: dict, key: str) -> Any:
    """从 endpoint 已解析参数中取路径参数（兼容 key 名大小写/下划线）。"""
    if key in kwargs:
        return kwargs[key]
    lower_map = {str(k).lower(): v for k, v in kwargs.items()}
    return lower_map.get(key.lower())


def audit(
    action: str,
    resource_type: str,
    *,
    resource_id: Optional[_Value] = None,
    resource_name: Optional[_Value] = None,
    summary: Optional[_Value] = None,
    username: Optional[_Value] = None,
    get_resource: Optional[Callable] = None,
    resource_name_attr: str = "name",
    capture_changes: bool = False,
    diff_before: Optional[Callable] = None,
    diff_after: Optional[Callable] = None,
):
    """关键操作审计装饰器（增强业务语义）。

    用法
    ----
    .. code-block:: python

        @router.delete("/assets/{asset_id}", dependencies=[ManagePerm])
        @audit(
            action="delete", resource_type="asset",
            get_resource=lambda db, asset_id: asset_repo.get_asset(db, asset_id),
            resource_name_attr="original_filename",
        )
        async def soft_delete_asset(asset_id: int, db=Depends(get_db)):
            ...

    说明
    ----
    - ``resource_id`` 默认取路径参数（与资源字段名一致，如 ``asset_id``）；
    - ``get_resource`` 在 endpoint 执行前调用（用于删除场景取 before 状态 / 名称快照），
      可同步或异步，入参与 endpoint 同名参数对齐（自动过滤多余 kwargs）；
    - ``capture_changes=True`` 时，用 ``diff_before``（取 before 值）与 ``diff_after``
      （取 after 值）计算字段级 diff 写入 ``changes``；
    - 装饰器把结果写入 ``audit_enrichment_var``，由审计中间件合并落库；
      本身不落库、不阻塞、不抛错（记录失败不影响业务）。
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx: _Ctx = dict(kwargs)
            enrichment: dict = {
                "action": action,
                "resource_type": resource_type,
                "capture_changes": capture_changes,
            }
            db = kwargs.get("db")
            resource = None
            before_vals: dict = {}

            # 1) 取 before 资源（删除/更新前快照，用于名称与 diff）
            if get_resource is not None:
                try:
                    sig = inspect.signature(get_resource)
                    call_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
                    if db is not None and "db" in sig.parameters and "db" not in call_kwargs:
                        call_kwargs["db"] = db
                    resource = await _maybe_await(get_resource(**call_kwargs))
                except Exception as e:  # noqa: BLE001 审计失败不影响业务
                    logger.warning(f"[audit] get_resource failed for {action} {resource_type}: {e}")

            # 1.5) 在 endpoint 执行前立即捕获 before 值快照。
            #      注意：ORM 对象是会话内同一引用，endpoint 会原地修改它，
            #      若在 endpoint 之后再读 before 会拿到已被修改的值，导致 diff 恒为空。
            if capture_changes and resource is not None:
                before_vals = await _collect_diff(diff_before, resource, ctx, kwargs)

            # 2) 执行 endpoint（异常由 FastAPI 处理，此处不捕获）
            result = await func(*args, **kwargs)

            # 3) 计算富化字段
            try:
                # resource_id 解析优先级：
                #   显式指定 > get_resource 返回对象的 id > 路径参数 {resource_type}_id > 任一 _id 参数
                if resource_id is not None:
                    rid = _resolve(resource_id, ctx)
                    if rid is not None:
                        enrichment["resource_id"] = str(rid)
                elif resource is not None and getattr(resource, "id", None) is not None:
                    enrichment["resource_id"] = str(resource.id)
                else:
                    path_id = _pick_path_param(kwargs, f"{resource_type}_id")
                    if path_id is None and kwargs:
                        # 兼容形如 doc_id / asset_id 的常见命名（取最靠后的 _id，通常是最具体的资源）
                        for key in reversed(list(kwargs)):
                            if key.endswith("_id") and key != "db":
                                path_id = kwargs[key]
                                break
                    if path_id is not None:
                        enrichment["resource_id"] = str(path_id)

                # resource_name：显式 > before 资源属性 > after 结果属性
                if resource_name is not None:
                    rn = _resolve(resource_name, ctx)
                    if rn:
                        enrichment["resource_name"] = str(rn)
                elif resource is not None:
                    rn = getattr(resource, resource_name_attr, None)
                    if rn:
                        enrichment["resource_name"] = str(rn)
                else:
                    result_name = _try_get_name(result, resource_name_attr)
                    if result_name:
                        enrichment["resource_name"] = str(result_name)

                # summary：显式 > 自动拼
                if summary is not None:
                    sm = _resolve(summary, ctx)
                    if sm:
                        enrichment["summary"] = str(sm)
                else:
                    enrichment["summary"] = build_summary(
                        action,
                        resource_type,
                        enrichment.get("resource_name"),
                    )

                # username：显式覆盖（如登录场景，此时请求尚无 Authorization 头）
                if username is not None:
                    un = _resolve(username, ctx)
                    if un:
                        enrichment["username"] = str(un)

                # changes diff
                if capture_changes:
                    after_vals = await _collect_diff(diff_after, result, ctx, kwargs)
                    changes = _diff_dicts(before_vals, after_vals)
                    if changes:
                        enrichment["changes"] = changes
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[audit] enrichment failed for {action} {resource_type}: {e}")

            audit_enrichment_var.set(enrichment)
            return result

        return wrapper

    return decorator


def _try_get_name(obj: Any, attr: str) -> Optional[str]:
    """从返回值/返回 dict 中尽力取名称。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        for key in (attr, "name", "title", "filename", "username", "resource_name"):
            if key in obj and obj[key]:
                return str(obj[key])
        return None
    for key in (attr, "name", "title", "filename", "username"):
        val = getattr(obj, key, None)
        if val:
            return str(val)
    return None


async def _collect_diff(
    callback: Optional[Callable],
    source: Any,
    ctx: _Ctx,
    kwargs: dict,
) -> dict:
    """调用 diff 回调取字段值字典；回调可同步/异步。

    首个位置参数直接接收 ``source``（无论其名为 source/result/before 等），
    其余参数从 endpoint kwargs 中按名补齐。
    """
    if callback is None or source is None:
        return {}
    try:
        sig = inspect.signature(callback)
        params = list(sig.parameters.values())
        positional: list = []
        call_kwargs: dict = {}
        if params:
            first = params[0]
            if first.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                positional.append(source)
                params = params[1:]
        for p in params:
            if p.name in kwargs and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                call_kwargs[p.name] = kwargs[p.name]
        value = await _maybe_await(callback(*positional, **call_kwargs))
        return value or {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audit] diff callback failed: {e}")
        return {}


def _diff_dicts(before: dict, after: dict) -> dict:
    """计算字段级 diff：{"field": {"before": x, "after": y}}（仅记录有变化的字段）。"""
    changes: dict = {}
    all_keys = set(before) | set(after)
    for key in all_keys:
        bv = before.get(key)
        av = after.get(key)
        if _jsonable(bv) != _jsonable(av):
            changes[key] = {"before": bv, "after": av}
    return changes


def _jsonable(value: Any) -> Any:
    """把非 JSON 可序列化对象（如 datetime/ORM）转成可比较/可入库的值。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    from datetime import datetime, date

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(value)
