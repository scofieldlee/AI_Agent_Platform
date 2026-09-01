"""Audit core unit tests: 脱敏、summary、diff 计算。"""

import pytest

from app.core.audit import (
    sanitize_body,
    build_summary,
    _diff_dicts,
    _collect_diff,
)


class TestSanitizeBody:
    def test_sensitive_fields_masked(self):
        data = {
            "username": "admin",
            "password": "secret123",
            "api_key": "sk-abcdefgh123456",
            "name": "ok",
        }
        out = sanitize_body(data)
        assert out["username"] == "admin"
        assert out["password"] == "***"
        assert out["api_key"] == "***"
        assert out["name"] == "ok"

    def test_nested_and_lists(self):
        data = {
            "credentials": {"token": "abc", "safe": 1},
            "items": [{"password": "x"}, "sk-12345678"],
        }
        out = sanitize_body(data)
        # credentials 属敏感字段名 → 整个值脱敏
        assert out["credentials"] == "***"
        assert out["items"][0]["password"] == "***"
        assert out["items"][1] == "***"  # sk- 值特征兜底

    def test_secret_value_pattern_masked(self):
        assert sanitize_body("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc") == "***"
        assert sanitize_body("normal string") == "normal string"


class TestBuildSummary:
    def test_with_name(self):
        assert build_summary("delete", "asset", "ruko") == "删除了素材 ruko"

    def test_without_name(self):
        assert build_summary("login", "user", None) == "登录了用户"

    def test_unknown_action(self):
        # 未映射动作 → 使用原始动作词
        assert build_summary("whatever", "system", None) == "whatever了系统"


class TestDiff:
    def test_diff_dicts_only_changed(self):
        before = {"a": 1, "b": 2, "c": 3}
        after = {"a": 1, "b": 9, "c": 3}
        diff = _diff_dicts(before, after)
        assert diff == {"b": {"before": 2, "after": 9}}

    def test_diff_empty_when_same(self):
        assert _diff_dicts({"a": 1}, {"a": 1}) == {}

    def test_diff_added_and_removed(self):
        diff = _diff_dicts({"a": 1}, {"b": 2})
        assert diff["a"] == {"before": 1, "after": None}
        assert diff["b"] == {"before": None, "after": 2}


@pytest.mark.asyncio
async def test_collect_diff_passes_source_positionally():
    """回调首个位置参数应收到 source（无论参数名）。"""
    before = await _collect_diff(
        lambda source: {"name": source["name"]},
        {"name": "x"},
        {},
        {},
    )
    assert before == {"name": "x"}

    after = await _collect_diff(
        lambda result: {"name": result.get("name")},
        {"name": "y"},
        {},
        {},
    )
    assert after == {"name": "y"}
