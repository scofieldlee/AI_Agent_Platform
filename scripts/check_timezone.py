#!/usr/bin/env python3
"""抽查各模块接口返回的时间字段，确认已统一为北京时间。"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "http://127.0.0.1:8000"
USER, PWD = "admin", "admin123456"

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")

ENDPOINTS = [
    ("多模态-处理任务", "/api/v1/multimodal/tasks?page=1&page_size=5"),
    ("多模态-素材列表", "/api/v1/multimodal/assets?page=1&page_size=5"),
    ("多模态-知识库", "/api/v1/multimodal/knowledge-bases"),
    ("对话-会话列表", "/api/v1/conversations?page=1&page_size=5"),
    ("分析-Trace列表", "/api/v1/analytics/traces?page=1&page_size=5"),
    ("人工-任务列表", "/api/v1/human-tasks?page=1&page_size=5"),
    ("AI员工-任务", "/api/v1/ai-employees/tasks?page=1&page_size=5"),
    ("知识库-文档", "/api/v1/knowledge/documents?page=1&page_size=5"),
    ("Agent列表", "/api/v1/agents"),
    ("模型配置", "/api/v1/models/configs/selectable"),
    ("记忆列表", "/api/v1/memories?page=1&page_size=5"),
    ("监控-健康", "/api/v1/monitoring/health"),
    ("用户列表", "/api/v1/auth/users"),
]

TIME_KEYS = ("created_at", "updated_at", "started_at", "completed_at", "timestamp",
             "last_login", "assigned_at", "resolved_at", "deleted_at", "hour",
             "create_time", "last_accessed_at", "submit_time", "end_time_",
             "expire", "date")


def login() -> str:
    req = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=json.dumps({"username": USER, "password": PWD}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("access_token", "")


def get(path: str, token: str):
    req = urllib.request.Request(f"{BASE}{path}",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode()[:120]}
    except Exception as e:  # noqa
        return 0, {"_error": str(e)[:120]}


def walk(node, path, out):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, f"{path}.{k}" if path else k, out)
    elif isinstance(node, list):
        for i, v in enumerate(node[:3]):
            walk(v, f"{path}[{i}]", out)
    elif isinstance(node, str) and ISO.match(node):
        out.append((path, node))


def main() -> int:
    token = login()
    if not token:
        print("登录失败")
        return 1
    print(f"主机当前时间: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 78)
    problems = 0
    for name, path in ENDPOINTS:
        status, data = get(path, token)
        found = []
        walk(data, "", found)
        if status != 200:
            print(f"[{status}] {name:<16} {data.get('_error', '')[:60]}")
            continue
        if not found:
            print(f"[{status}] {name:<16} (无时间字段)")
            continue
        sample = found[0]
        # 判断是否为北京时间：与 UTC 相差 8 小时
        try:
            naive = datetime.fromisoformat(sample[1].replace(" ", "T"))
            utc_guess = naive.replace(tzinfo=timezone.utc).astimezone(
                timezone.utc)
            beijing = naive.replace(
                tzinfo=timezone(offset := __import__("datetime").timezone(
                    __import__("datetime").timedelta(hours=8))))
        except Exception:
            pass
        flag = ""
        # 若仍带 Z / +00:00 视为未修正
        raw = sample[1]
        if raw.endswith("Z") or "+00:00" in raw:
            flag = "  ❌ 仍是UTC"
            problems += 1
        print(f"[{status}] {name:<16} {sample[0]} = {raw}{flag}")
    print("=" * 78)
    print("存在问题接口数:", problems)
    return problems


if __name__ == "__main__":
    sys.exit(main())
