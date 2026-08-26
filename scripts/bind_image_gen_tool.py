"""Bind image_generation tool to Agent #10 (multimodal KB assistant)."""
import asyncio
import sys

sys.path.insert(0, "/Users/scofieldlee/Documents/GitHub/AI_Agent_Platform")

from sqlalchemy import select
from app.database.session import async_session_factory
from app.models.agent import AgentToolBinding
from app.models.tool import Tool


async def main():
    async with async_session_factory() as db:
        agent_id = 10
        tool_name = "image_generation"

        tool = (await db.execute(select(Tool).where(Tool.name == tool_name))).scalar_one_or_none()
        if not tool:
            print(f"Tool {tool_name} not found in DB. Restart backend first.")
            return

        existing = (
            await db.execute(
                select(AgentToolBinding).where(
                    AgentToolBinding.agent_id == agent_id,
                    AgentToolBinding.tool_id == tool.id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            print(f"Agent {agent_id} already bound to {tool_name}")
            return

        db.add(AgentToolBinding(agent_id=agent_id, tool_id=tool.id, permission="allow"))
        await db.commit()
        print(f"Bound tool {tool_name} (id={tool.id}) to agent {agent_id}")


if __name__ == "__main__":
    asyncio.run(main())
