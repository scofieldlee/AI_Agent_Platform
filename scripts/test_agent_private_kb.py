"""E2E: agent-private knowledge bases.

Covers: create/auto-bind, multi-KB code suffix, import, global-list
visibility (admin sees badge / regular user hidden), retrieval isolation
(global search never leaks agent-private chunks), per-agent binding scope,
promote-to-global, agent deletion cascade.

Run: ./.venv/bin/python scripts/test_agent_private_kb.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE = "http://127.0.0.1:8000"
ADMIN = {"username": "admin", "password": "admin123456"}
CS = {"username": "cs_agent", "password": "cs123456"}

PASS, FAIL = 0, 0


def check(name: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{tag}] {name}" + (f"  ({extra})" if extra else ""))


async def login(client: httpx.AsyncClient, creds: dict) -> str:
    r = await client.post(f"{BASE}/api/v1/auth/login", json=creds)
    r.raise_for_status()
    return r.json()["access_token"]


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120, trust_env=False) as c:
        admin_tok = await login(c, ADMIN)
        cs_tok = await login(c, CS)
        ah = {"Authorization": f"Bearer {admin_tok}"}
        ch = {"Authorization": f"Bearer {cs_tok}"}

        # --- setup: fresh agent ---
        suffix = asyncio.get_event_loop().time().__trunc__()
        r = await c.post(f"{BASE}/api/v1/agents", json={
            "name": "E2E专属KB测试", "code": f"e2e_priv_kb_{suffix}",
            "agent_type": "config",
        }, headers=ah)
        r.raise_for_status()
        agent = r.json()
        agent_id = agent["id"]
        print(f"\n== setup agent id={agent_id} code={agent['code']} ==")

        # --- 1. create private KB (auto-bind) ---
        r = await c.post(f"{BASE}/api/v1/agents/{agent_id}/kb", json={
            "name": "售后话术库", "description": "E2E 测试专属 KB",
        }, headers=ah)
        check("create private KB -> 201", r.status_code == 201, r.text[:120])
        kb1 = r.json()
        check("visibility == agent_private", kb1.get("visibility") == "agent_private")
        check("owner_agent_id == agent", kb1.get("owner_agent_id") == agent_id)
        check("code auto = agent_{code}_kb", kb1["code"] == f"agent_{agent['code']}_kb", kb1["code"])

        # --- 2. second KB gets suffix ---
        r = await c.post(f"{BASE}/api/v1/agents/{agent_id}/kb", json={"name": "产品参数库"}, headers=ah)
        kb2 = r.json()
        check("second KB code suffix _2", kb2.get("code", "").endswith("_2"), kb2.get("code", ""))
        r = await c.get(f"{BASE}/api/v1/agents/{agent_id}/kb", headers=ah)
        check("list private KBs -> 2", len(r.json()) == 2)

        # --- 3. import document into private KB (csv table, same as KB import) ---
        csv = "项目,说明\n七天无理由退货,自签收之日起7天内可申请退货退款\n专属E2E暗号,MAGNET-X7\n"
        r = await c.post(
            f"{BASE}/api/v1/agents/{agent_id}/kb/{kb1['id']}/import",
            files={"file": ("faq.csv", csv.encode("utf-8"), "text/csv")},
            headers=ah,
        )
        check("import csv -> completed", r.status_code == 200 and r.json().get("chunks", 0) > 0,
              r.text[:160])
        r = await c.get(f"{BASE}/api/v1/agents/{agent_id}/kb/{kb1['id']}/documents", headers=ah)
        check("documents listed", r.status_code == 200 and len(r.json()) >= 1)

        # --- 4. visibility: admin sees badge info, cs_agent hidden ---
        r = await c.get(f"{BASE}/api/v1/knowledge", headers=ah)
        admin_view = {k["id"] for k in r.json()}
        check("admin global list contains private KB", kb1["id"] in admin_view)
        check("admin payload carries visibility flag",
              any(k["id"] == kb1["id"] and k.get("visibility") == "agent_private" for k in r.json()))

        r = await c.get(f"{BASE}/api/v1/knowledge", headers=ch)
        cs_view = {k["id"] for k in r.json()}
        check("cs_agent global list hides private KB", kb1["id"] not in cs_view and kb2["id"] not in cs_view)

        # --- 5. cs_agent cannot touch agent private KB endpoints ---
        r = await c.get(f"{BASE}/api/v1/agents/{agent_id}/kb", headers=ch)
        check("cs_agent list private KBs -> 403/404", r.status_code in (403, 404), str(r.status_code))

        # --- 6. retrieval isolation: global search excludes private chunks ---
        from app.knowledge.retrievers.vector_retriever import retrieve_knowledge
        res = await retrieve_knowledge("专属E2E暗号 MAGNET-X7", top_k=10)
        leaked = any("MAGNET-X7" in s["content"] for s in res.get("sources", []))
        check("global search does NOT leak private chunk", not leaked,
              f"avg_score={res.get('avg_score')}")

        # scoped search WITH the binding finds it
        res2 = await retrieve_knowledge("专属E2E暗号 MAGNET-X7", top_k=10,
                                        knowledge_base_ids=[kb1["id"]])
        found = any("MAGNET-X7" in s["content"] for s in res2.get("sources", []))
        check("scoped search (bound KB) finds private chunk", found)

        # --- 7. knowledge_node scoping: agent-bound kb ids resolve ---
        from app.workflows.nodes import _agent_bound_kb_ids
        bound = await _agent_bound_kb_ids(agent_id)
        check("agent bindings resolve to bound KBs", bound is not None and kb1["id"] in bound,
              str(bound))

        # --- 8. promote to global ---
        r = await c.post(f"{BASE}/api/v1/agents/{agent_id}/kb/{kb1['id']}/promote", headers=ah)
        check("promote -> 200", r.status_code == 200, r.text[:120])
        r = await c.get(f"{BASE}/api/v1/agents/{agent_id}/kb", headers=ah)
        remaining = {k["id"] for k in r.json()}
        check("promoted KB leaves private list", kb1["id"] not in remaining)
        # still bound & searchable via binding
        bound2 = await _agent_bound_kb_ids(agent_id)
        check("binding kept after promote", kb1["id"] in (bound2 or []))
        # global retrieval now finds it (it is public)
        res3 = await retrieve_knowledge("专属E2E暗号 MAGNET-X7", top_k=10)
        found3 = any("MAGNET-X7" in s["content"] for s in res3.get("sources", []))
        check("global search finds promoted KB content", found3)

        # --- 9. delete agent: soft-delete keeps KBs; hard delete cascades ---
        r = await c.delete(f"{BASE}/api/v1/agents/{agent_id}", headers=ah)
        check("delete agent (soft) -> 200", r.status_code in (200, 204), str(r.status_code))
        r = await c.get(f"{BASE}/api/v1/agents/{agent_id}/kb/{kb2['id']}/documents", headers=ah)
        check("soft-delete keeps private KB data", r.status_code == 200, str(r.status_code))
        # hard delete via DB -> FK CASCADE removes the private KB
        import asyncio as _aio
        async def _hard_delete():
            from sqlalchemy import delete as sa_delete
            from app.database.session import async_session_factory
            from app.models.agent import Agent
            async with async_session_factory() as db:
                await db.execute(sa_delete(Agent).where(Agent.id == agent_id))
                await db.commit()
        await _hard_delete()
        r = await c.get(f"{BASE}/api/v1/knowledge/{kb2['id']}/documents", headers=ah)
        check("hard delete cascades private KB", r.status_code == 404, str(r.status_code))

    print(f"\n==== RESULT: {PASS} passed, {FAIL} failed ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
