"""
FastAPI application entry point.
AI Agent Platform - Enterprise AI Agent Infrastructure.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.database.session import engine, init_db
from app.database.redis_client import redis_client, close_redis

logger = logging.getLogger(__name__)


async def register_default_tools():
    """Register built-in tools in the registry and database at startup."""
    from app.tools.registry import get_registry
    from app.tools.adapters.product_query import ProductQueryTool
    from app.tools.adapters.order_query import OrderQueryTool
    from app.tools.adapters.inventory_query import InventoryQueryTool
    from app.tools.adapters.refund_query import RefundQueryTool
    from app.tools.adapters.logistics_query import LogisticsQueryTool
    from app.database.session import async_session_factory
    from app.models.tool import Tool
    from sqlalchemy import select

    registry = get_registry()

    # Register tools in memory
    registry.register(ProductQueryTool())
    registry.register(OrderQueryTool())
    registry.register(InventoryQueryTool())
    registry.register(RefundQueryTool())
    registry.register(LogisticsQueryTool())

    # Ensure tools exist in database (for execution logging)
    tool_instances = [
        ProductQueryTool(),
        OrderQueryTool(),
        InventoryQueryTool(),
        RefundQueryTool(),
        LogisticsQueryTool(),
    ]

    default_tools = [
        {
            "name": t.name,
            "code": t.name,
            "description": t.description,
            "tool_type": t.tool_type,
            "input_schema": t.input_schema,
            "output_schema": t.output_schema,
        }
        for t in tool_instances
    ]

    async with async_session_factory() as db:
        for tool_def in default_tools:
            result = await db.execute(
                select(Tool).where(Tool.name == tool_def["name"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing tool
                existing.description = tool_def["description"]
                existing.input_schema = tool_def["input_schema"]
                existing.output_schema = tool_def["output_schema"]
                existing.is_active = True
            else:
                # Create new tool
                db.add(Tool(**tool_def, status="active", version="1.0.0"))

        await db.commit()

    logger.info(f"Registered {registry.count()} tools in registry and database.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # --- Startup ---
    logger.info(f"Starting {settings.app_name}...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")

    # Initialize database tables
    await init_db()
    logger.info("Database initialized.")

    # Register default tools
    await register_default_tools()

    # Seed permissions, role-permissions, and admin user
    from app.auth.seed import run_auth_seed
    from app.database.session import async_session_factory
    async with async_session_factory() as seed_db:
        await run_auth_seed(seed_db)

    # Seed default workflow definition
    from app.workflows.seed import seed_default_workflow
    async with async_session_factory() as wf_db:
        await seed_default_workflow(wf_db)

    # Test Redis connection
    try:
        await redis_client.ping()
        logger.info("Redis connected.")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")

    # Recover orphan AI Employee tasks (running -> failed)
    try:
        from app.repositories import employee_repo
        async with async_session_factory() as emp_db:
            orphan_count = await employee_repo.fail_orphan_tasks(emp_db)
            if orphan_count:
                logger.warning(f"Recovered {orphan_count} orphan AI Employee tasks (marked as failed).")
    except Exception as e:
        logger.warning(f"AI Employee task recovery failed: {e}")

    logger.info(f"{settings.app_name} is ready!")

    yield

    # --- Shutdown ---
    logger.info(f"Shutting down {settings.app_name}...")
    await engine.dispose()
    await close_redis()
    logger.info("Cleanup complete.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="Enterprise AI Agent Platform - Infrastructure for Digital Employees",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routes ---
    from app.api.v1.endpoints import health, agents, conversations, knowledge, tools, analytics, memories, human_tasks, auth, workflow, monitoring, public, models, ai_employees

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
    app.include_router(conversations.router, prefix="/api/v1/conversations", tags=["conversations"])
    app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
    app.include_router(tools.router, prefix="/api/v1/tools", tags=["tools"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
    app.include_router(memories.router, prefix="/api/v1/memories", tags=["memories"])
    app.include_router(human_tasks.router, prefix="/api/v1/human-tasks", tags=["human-tasks"])
    app.include_router(workflow.router, prefix="/api/v1/workflow", tags=["workflow"])
    app.include_router(monitoring.router, prefix="/api/v1/monitoring", tags=["monitoring"])
    app.include_router(models.router, prefix="/api/v1/models", tags=["models"])
    app.include_router(public.router, prefix="/api/v1/public", tags=["public"])
    app.include_router(ai_employees.router, prefix="/api/v1/ai-employees", tags=["ai-employees"])

    # --- Static files ---
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/chat", response_class=HTMLResponse)
    async def chat_page():
        """Serve the chat UI for RAG conversation testing."""
        chat_file = Path(__file__).parent.parent / "static" / "chat.html"
        if chat_file.exists():
            return HTMLResponse(content=chat_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>chat.html not found</h1>", status_code=404)

    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "status": "running",
            "docs": "/docs",
            "chat": "/chat",
            "tools": "/api/v1/tools",
            "analytics": "/api/v1/analytics/stats",
            "monitoring": "/api/v1/monitoring/overview",
            "memories": "/api/v1/memories",
            "human_tasks": "/api/v1/human-tasks",
        }

    return app


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = create_app()
