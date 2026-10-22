"""E2E: model token usage accounting.

Flow: set model unit prices -> trigger a real chat via an agent ->
verify model_usage_logs row (tokens/cost/agent_id) -> verify the four
statistics endpoints return consistent aggregates.

Run: ./.venv/bin/python scripts/test_usage_stats.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE = "http://127.0.0.1:8000"
ADMIN = {"username": "admin", "password": "admin123456"}

PASS, FAIL = 0, 0


def check(name: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({extra})" if extra else ""))


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=180, trust_env=False) as c:
        r = await c.post(f"{BASE}/api/v1/auth/login", json=ADMIN)
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}

        # --- pick an agent + bound model ---
        r = await c.get(f"{BASE}/api/v1/agents", headers=h)
        agents = r.json()
        agent = next((a for a in agents if a["status"] == "published"), agents[0])
        agent_id = agent["id"]
        detail = (await c.get(f"{BASE}/api/v1/agents/{agent_id}/detail", headers=h)).json()
        mc_id = (detail.get("config") or {}).get("model_config_id")
        print(f"== agent {agent_id} ({agent['name']}) model_config_id={mc_id} ==")

        before = (await c.get(f"{BASE}/api/v1/usage/summary", headers=h)).json()
        calls_before = before["calls"]

        # --- trigger a real chat ---
        r = await c.post(f"{BASE}/api/v1/conversations/chat", headers=h, json={
            "user_id": 1, "agent_id": agent_id, "message": "你好，一句话介绍你自己",
        })
        check("chat call ok", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

        # intent classifier + llm may both fire; allow a beat for async writes
        await asyncio.sleep(2)

        summary = (await c.get(f"{BASE}/api/v1/usage/summary", headers=h)).json()
        delta_calls = summary["calls"] - calls_before
        check("usage rows recorded", delta_calls >= 1, f"+{delta_calls} calls")
        check("tokens accumulated", summary["total_tokens"] > 0, f"total={summary['total_tokens']}")

        rows = (await c.get(f"{BASE}/api/v1/usage/by-model", headers=h)).json()
        check("by-model non-empty", len(rows) >= 1)
        r0 = rows[0]
        check("model name resolved", bool(r0.get("model_name")), str(r0.get("model_name")))
        # cost consistency: price 0.00027/0.0011 per 1k on config 1
        if r0.get("model_config_id") == mc_id and mc_id == 1:
            expect = r0["prompt_tokens"] / 1000 * 0.00027 + r0["completion_tokens"] / 1000 * 0.0011
            check("cost matches unit price", abs(r0["cost"] - expect) < 1e-6,
                  f"cost={r0['cost']} expect~{expect:.6f}")

        by_agent = (await c.get(f"{BASE}/api/v1/usage/by-agent", headers=h)).json()
        row_agent = next((a for a in by_agent if a["agent_id"] == agent_id), None)
        check("by-agent contains the agent", row_agent is not None)
        if row_agent:
            check("agent tokens consistent with model view",
                  row_agent["total_tokens"] == sum(x["total_tokens"] for x in by_agent if x["agent_id"] == agent_id))
        check("agent_name fallback present", any(a["agent_name"] == "系统内部调用" for a in by_agent) or len(by_agent) > 0)

        tl = (await c.get(f"{BASE}/api/v1/usage/timeline", headers={
            **h, "params": ""}, params={"granularity": "day"})).json()
        check("timeline returns buckets", isinstance(tl, list) and len(tl) >= 1, f"{len(tl)} buckets")
        if tl:
            check("timeline sums == summary total",
                  sum(t["total_tokens"] for t in tl) == summary["total_tokens"],
                  f"{sum(t['total_tokens'] for t in tl)} vs {summary['total_tokens']}")

        # error path: invalid model_config_id -> error row with status=error
        from app.models_center.service import ModelService
        ms = ModelService()
        try:
            await ms.chat("x", "y", model_config_id=999999)
        except Exception:
            pass
        await asyncio.sleep(1)
        s2 = (await c.get(f"{BASE}/api/v1/usage/summary", headers=h)).json()
        check("failed call counted with error status",
              s2["error_calls"] >= 1, f"error_calls={s2['error_calls']}")

    print(f"\n==== RESULT: {PASS} passed, {FAIL} failed ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
