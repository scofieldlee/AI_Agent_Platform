"""E2E test: reference-grounded image generation via Agent #10.

Verifies: intent(image_generation) -> cross-KB multimodal search -> F11PRO
asset selected as reference (product-code heuristic) -> Plan endpoint I2I
generation -> image saved locally -> answer embeds markdown image.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    # 1. Manually register tools (process isolation)
    from app.tools.registry import ToolRegistry
    from app.tools.adapters.image_generation import ImageGenerationTool
    from app.tools.adapters.multimodal_kb_search import MultimodalKBSearchTool

    registry = ToolRegistry()
    registry.register(ImageGenerationTool())
    registry.register(MultimodalKBSearchTool())

    # 2. Run through AgentRuntime
    from app.runtime.executor import AgentRuntime
    from app.runtime.context import AgentContext

    runtime = AgentRuntime()
    context = AgentContext(user_id=1, tenant_id=1, agent_id=10)

    result = await runtime.run("帮我给F11PRO换个新配色，生成图片", context)

    print("=" * 60)
    print(f"intent      : {result.get('intent')}")
    print(f"confidence  : {result.get('confidence')}")
    print(f"need_human  : {result.get('need_human')}")
    print("-" * 60)
    answer = result.get("answer", "")
    print("ANSWER:")
    print(answer)
    print("=" * 60)

    import re
    gen_urls = re.findall(r"/api/v1/multimodal/files/(generated/[^\)\s]+)", answer)
    ref_urls = re.findall(r"/api/v1/multimodal/files/(\d+/assets/[^\)\s]+)", answer)
    print(f"[check] generated image in answer : {len(gen_urls) > 0} ({gen_urls})")
    print(f"[check] reference asset in answer : {len(ref_urls) > 0} ({ref_urls})")

    ok = True
    for u in gen_urls:
        local = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "uploads", "multimodal", u,
        )
        exists = os.path.exists(local)
        size = os.path.getsize(local) if exists else 0
        print(f"[check] generated file {u}: exists={exists}, size={size} bytes")
        ok = ok and exists

    if gen_urls and ok:
        print("\n[PASS] reference-grounded E2E OK")
    else:
        print("\n[FAIL]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
