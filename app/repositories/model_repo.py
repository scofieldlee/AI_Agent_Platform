"""
Model repository: data access for model providers and configurations.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import ModelProvider, ModelConfig


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

async def list_providers(db: AsyncSession, include_inactive: bool = False) -> List[ModelProvider]:
    """List all providers."""
    stmt = select(ModelProvider)
    if not include_inactive:
        stmt = stmt.where(ModelProvider.is_active.is_(True))
    stmt = stmt.order_by(ModelProvider.id.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_provider(db: AsyncSession, provider_id: int) -> Optional[ModelProvider]:
    """Get provider by ID."""
    return await db.get(ModelProvider, provider_id)


async def get_provider_by_code(db: AsyncSession, code: str) -> Optional[ModelProvider]:
    """Get provider by code."""
    result = await db.execute(
        select(ModelProvider).where(ModelProvider.code == code)
    )
    return result.scalar_one_or_none()


async def create_provider(
    db: AsyncSession,
    name: str,
    code: str,
    base_url: str,
    api_key: str,
    is_active: bool = True,
    config: Optional[dict] = None,
) -> ModelProvider:
    """Create a new provider."""
    provider = ModelProvider(
        name=name,
        code=code,
        base_url=base_url,
        api_key=api_key,
        is_active=is_active,
        config=config or {},
    )
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return provider


async def update_provider(
    db: AsyncSession,
    provider: ModelProvider,
    updates: Dict[str, Any],
) -> ModelProvider:
    """Update a provider."""
    for key, value in updates.items():
        if value is not None or key in ("is_active", "config"):
            setattr(provider, key, value)
    await db.flush()
    await db.refresh(provider)
    return provider


async def delete_provider(db: AsyncSession, provider: ModelProvider) -> None:
    """Delete a provider (hard delete). Fails if models still reference it."""
    await db.delete(provider)
    await db.flush()


# ---------------------------------------------------------------------------
# Model Configs
# ---------------------------------------------------------------------------

async def list_model_configs(
    db: AsyncSession,
    include_inactive: bool = False,
    provider_id: Optional[int] = None,
) -> List[ModelConfig]:
    """List all model configs with provider info."""
    stmt = select(ModelConfig).options(joinedload(ModelConfig.provider))
    if not include_inactive:
        stmt = stmt.where(ModelConfig.is_active.is_(True))
    if provider_id is not None:
        stmt = stmt.where(ModelConfig.provider_id == provider_id)
    stmt = stmt.order_by(ModelConfig.id.desc())
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())


async def get_model_config(db: AsyncSession, config_id: int) -> Optional[ModelConfig]:
    """Get model config by ID with provider info."""
    result = await db.execute(
        select(ModelConfig)
        .options(joinedload(ModelConfig.provider))
        .where(ModelConfig.id == config_id)
    )
    return result.scalar_one_or_none()


async def get_default_model_config(
    db: AsyncSession,
    model_type: str = "chat",
) -> Optional[ModelConfig]:
    """Get the default model config for a model type."""
    result = await db.execute(
        select(ModelConfig)
        .options(joinedload(ModelConfig.provider))
        .where(ModelConfig.model_type == model_type)
        .where(ModelConfig.is_active.is_(True))
        .where(ModelConfig.is_default.is_(True))
    )
    return result.scalar_one_or_none()


async def create_model_config(db: AsyncSession, data: Dict[str, Any]) -> ModelConfig:
    """Create a new model config."""
    config = ModelConfig(**data)
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


async def update_model_config(
    db: AsyncSession,
    config: ModelConfig,
    updates: Dict[str, Any],
) -> ModelConfig:
    """Update a model config."""
    for key, value in updates.items():
        if value is not None or key in ("is_active", "is_default", "config"):
            setattr(config, key, value)
    await db.flush()
    await db.refresh(config)
    return config


async def delete_model_config(db: AsyncSession, config: ModelConfig) -> None:
    """Delete a model config (hard delete)."""
    await db.delete(config)
    await db.flush()


async def set_default_model_config(
    db: AsyncSession,
    config_id: int,
    model_type: str,
) -> Optional[ModelConfig]:
    """Set a model config as the default for its type, unsetting others."""
    config = await get_model_config(db, config_id)
    if not config:
        return None

    # Unset other defaults of the same type
    await db.execute(
        select(ModelConfig)
        .where(ModelConfig.model_type == model_type)
        .where(ModelConfig.is_default.is_(True))
    )
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.model_type == model_type,
            ModelConfig.is_default.is_(True),
            ModelConfig.id != config_id,
        )
    )
    for other in result.scalars().all():
        other.is_default = False

    config.is_default = True
    await db.flush()
    await db.refresh(config)
    return config


async def list_selectable_configs(db: AsyncSession) -> List[Dict[str, Any]]:
    """List active chat/reasoning/vision configs for Agent dropdown."""
    result = await db.execute(
        select(ModelConfig, ModelProvider)
        .join(ModelProvider, ModelConfig.provider_id == ModelProvider.id)
        .where(ModelConfig.is_active.is_(True))
        .where(ModelProvider.is_active.is_(True))
        .where(ModelConfig.model_type.in_(["chat", "reasoning", "vision"]))
        .order_by(ModelConfig.id.desc())
    )
    rows = result.all()
    return [
        {
            "id": config.id,
            "name": config.name,
            "model_id": config.model_id,
            "model_type": config.model_type,
            "provider_code": provider.code,
            "provider_name": provider.name,
            "is_default": config.is_default,
        }
        for config, provider in rows
    ]
