"""
Database initialization script.
Creates tables, seeds default roles and permissions.

Usage:
    python scripts/init_db.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def init():
    """Initialize database with tables and seed data."""
    from app.database.session import init_db, async_session_factory
    from app.database.base import Base
    from app.models import (  # noqa: ensure models are imported
        User, UserProfile, Organization, Role, Permission,
        UserRole, RolePermission,
        Agent, AgentVersion,
        Workflow, WorkflowNode,
        KnowledgeBase, Document, Chunk,
        Conversation, Message,
        Memory, Tool, ModelProvider, ModelConfig,
    )

    print("Creating database tables...")
    await init_db()
    print("Tables created.")

    # Seed default data
    print("Seeding default data...")
    async with async_session_factory() as session:
        from sqlalchemy import select

        # Check if roles already exist
        result = await session.execute(select(Role).where(Role.code == "admin"))
        if not result.scalars().first():
            # Create default roles
            roles = [
                Role(name="Super Admin", code="super_admin", description="Full system access", is_system=True),
                Role(name="AI Admin", code="ai_admin", description="Manage agents, workflows, models", is_system=True),
                Role(name="Business Admin", code="business_admin", description="Manage knowledge, business agents", is_system=True),
                Role(name="Developer", code="developer", description="Develop tools, APIs, runtime", is_system=True),
                Role(name="Customer Service", code="customer_service", description="Handle human tasks", is_system=True),
                Role(name="User", code="user", description="End user, chat with agents", is_system=True),
            ]
            for role in roles:
                session.add(role)
            print(f"Created {len(roles)} default roles.")

        # Check if model provider exists
        result = await session.execute(select(ModelProvider).where(ModelProvider.code == "deepseek"))
        if not result.scalars().first():
            from app.core.config import settings
            provider = ModelProvider(
                name="DeepSeek",
                code="deepseek",
                base_url=settings.deepseek_base_url,
                api_key=settings.deepseek_api_key,
                is_active=True,
            )
            session.add(provider)
            await session.flush()

            # Create default models
            models = [
                ModelConfig(
                    provider_id=provider.id,
                    name="DeepSeek Chat",
                    model_id="deepseek-chat",
                    model_type="chat",
                    max_tokens=8192,
                    temperature=0.3,
                    is_default=True,
                ),
                ModelConfig(
                    provider_id=provider.id,
                    name="DeepSeek Reasoner",
                    model_id="deepseek-reasoner",
                    model_type="reasoning",
                    max_tokens=8192,
                    temperature=0.3,
                ),
            ]
            for model in models:
                session.add(model)
            print(f"Created DeepSeek provider with {len(models)} models.")

        await session.commit()

    print("\nDatabase initialization complete!")
    print("Default roles: super_admin, ai_admin, business_admin, developer, customer_service, user")
    print("Model provider: DeepSeek (deepseek-chat, deepseek-reasoner)")


if __name__ == "__main__":
    asyncio.run(init())
