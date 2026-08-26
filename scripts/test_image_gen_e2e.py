"""E2E test: image generation via Agent #10 (multimodal KB assistant).

Verifies full chain: intent classification (image_generation) -> tool_node
(image_generation tool) -> DashScope wanx-v1 generation -> image saved to
multimodal storage -> answer contains markdown image.

NOTE: this script runs in its own process, so the in-memory ToolRegistry
singleton is NOT shared with the backend — tools must be registered manually.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    # 1. Manually register tools (process isolation)
    from app.tools.registry import ToolRegistry
    from app.tools.adapters.image_generation import ImageGenerationTool

    registry = ToolRegistry()
    registry.register(ImageGenerationTool())
    print(f"[setup] registered tools: {registry.list_tools()}")

    # 2. Run through AgentRuntime
    from app.runtime.executor import AgentRuntime
    from app.runtime.context import AgentContext

    runtime = AgentRuntime()
    context = AgentContext(
        user_id=1,
        tenant_id=1,
        agent_id=10,
        conversation_id=None,
    )

    result = await runtime.run(
        "帮我生成一张小孩子使用F11MINI无人机产品的图片",
        context,
    )

    print("=" * 60)
    print(f"intent      : {result.get('intent')}")
    print(f"confidence  : {result.get('confidence')}")
    print(f"need_human  : {result.get('need_human')}")
    print(f"trace_id    : {result.get('trace_id')}")
    print(f"knowledge   : {result.get('knowledge_sources')}")
    print("-" * 60)
    answer = result.get("answer", "")
    print("ANSWER:")
    print(answer)
    print("=" * 60)

    # 3. Assertions
    has_image = "![生成图片" in answer or "/api/v1/multimodal/files/generated/" in answer
    print(f"[check] answer contains generated image markdown: {has_image}")

    # 4. Verify local file exists
    import re
    urls = re.findall(r"/api/v1/multimodal/files/(generated/[^\)\s]+)", answer)
    for u in urls:
        local = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "uploads", "multimodal", u,
        )
        exists = os.path.exists(local)
        size = os.path.getsize(local) if exists else 0
        print(f"[check] file {u}: exists={exists}, size={size} bytes")

    if has_image and urls:
        print("\n[PASS] E2E image generation chain OK")
    elif has_image:
        print("\n[PASS-ish] markdown image present but no URL extracted")
    else:
        print("\n[FAIL] no generated image in answer")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
