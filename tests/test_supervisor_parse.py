"""
Unit tests for Supervisor decision JSON parsing (design doc §9.1).

Run: .venv/bin/python -m pytest tests/test_supervisor_parse.py -v
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.employee.runtime.supervisor import parse_decision, SupervisorOutputError
from app.employee.runtime.prompts import build_supervisor_prompt


def test_clean_json_block():
    text = '好的，我的决策如下：\n```json\n{"action": "dispatch_agent", "agent_id": 2, "reason": "需要先查询商品", "input": {}}\n```'
    d = parse_decision(text)
    assert d["action"] == "dispatch_agent"
    assert d["agent_id"] == 2


def test_dispatch_parallel():
    text = '```json\n{"action": "dispatch_parallel", "agents": [{"agent_id": 2, "input": {}}, {"agent_id": 7, "input": {}}], "reason": "并行"}\n```'
    d = parse_decision(text)
    assert d["action"] == "dispatch_parallel"
    assert len(d["agents"]) == 2


def test_finish():
    text = '```json\n{"action": "finish", "result": {"summary": "任务已完成"}}\n```'
    d = parse_decision(text)
    assert d["action"] == "finish"
    assert d["result"]["summary"] == "任务已完成"


def test_human_intervention():
    text = '{"action": "human_intervention", "reason": "缺少授权信息"}'
    d = parse_decision(text)
    assert d["action"] == "human_intervention"


def test_json_with_surrounding_prose():
    text = '根据当前情况，我认为下一步应该派发 Agent。\n{"action": "dispatch_agent", "agent_id": 5, "reason": "r", "input": {}}\n以上是我的决策。'
    d = parse_decision(text)
    assert d["action"] == "dispatch_agent"


def test_json_block_without_tag():
    text = '```json\n{"action": "finish", "result": {"summary": "done"}}\n```'
    d = parse_decision(text)
    assert d["action"] == "finish"


def test_nested_braces_fallback():
    # No code fence; nested braces should still parse via fallback
    text = '决策：{"action": "dispatch_agent", "agent_id": 3, "reason": "why", "input": {"message": "包含}大括号"}} 完成'
    d = parse_decision(text)
    assert d["agent_id"] == 3


def test_invalid_action_raises():
    try:
        parse_decision('{"action": "do_something_else", "agent_id": 1}')
        assert False, "should have raised"
    except SupervisorOutputError as e:
        assert "invalid action" in str(e)


def test_missing_agent_id_raises():
    try:
        parse_decision('```json\n{"action": "dispatch_agent", "reason": "x"}\n```')
        assert False, "should have raised"
    except SupervisorOutputError as e:
        assert "agent_id" in str(e)


def test_empty_output_raises():
    try:
        parse_decision("")
        assert False, "should have raised"
    except SupervisorOutputError:
        pass


def test_completely_garbage_raises():
    try:
        parse_decision("抱歉，我不知道下一步该怎么做。")
        assert False, "should have raised"
    except SupervisorOutputError:
        pass


def test_prompt_renders():
    prompt = build_supervisor_prompt(
        role_name="市场专员",
        role_prompt="完成市场调研任务",
        task_input={"message": "调研无人机市场"},
        roster=[
            {"agent_id": 2, "name": "商品客服Agent", "role": "商品问答",
             "description": "回答商品问题"},
            {"agent_id": 7, "name": "Listing生成", "role": "文案生成",
             "description": None},
        ],
        context_summary="(尚无已完成的步骤)",
        round_no=1,
        max_rounds=15,
        calls_left=20,
    )
    assert "市场专员" in prompt
    assert "agent_id=2" in prompt
    assert "agent_id=7" in prompt
    assert "调研无人机市场" in prompt
    assert "第 1 / 15 轮" in prompt
    assert '"action": "finish"' in prompt


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            fails += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
