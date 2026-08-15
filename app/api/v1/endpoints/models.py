"""Model Center endpoints: manage LLM providers and model configurations."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.schemas.model import (
    ModelProviderCreate,
    ModelProviderUpdate,
    ModelProviderResponse,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelConfigResponse,
    ModelConfigSelectable,
)
from app.repositories import model_repo

router = APIRouter()


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@router.get("/providers", response_model=List[ModelProviderResponse], dependencies=[Depends(require_permission("model:view"))])
async def list_providers_endpoint(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List model providers."""
    return await model_repo.list_providers(db, include_inactive=include_inactive)


@router.post("/providers", response_model=ModelProviderResponse, status_code=201, dependencies=[Depends(require_permission("model:manage"))])
async def create_provider_endpoint(
    data: ModelProviderCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new provider."""
    existing = await model_repo.get_provider_by_code(db, data.code)
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider code '{data.code}' already exists")

    provider = await model_repo.create_provider(
        db,
        name=data.name,
        code=data.code,
        base_url=data.base_url,
        api_key=data.api_key,
        is_active=data.is_active,
        config=data.config,
    )
    await db.commit()
    return provider


@router.get("/providers/{provider_id}", response_model=ModelProviderResponse, dependencies=[Depends(require_permission("model:view"))])
async def get_provider_endpoint(provider_id: int, db: AsyncSession = Depends(get_db)):
    """Get provider by ID."""
    provider = await model_repo.get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.patch("/providers/{provider_id}", response_model=ModelProviderResponse, dependencies=[Depends(require_permission("model:manage"))])
async def update_provider_endpoint(
    provider_id: int,
    data: ModelProviderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a provider."""
    provider = await model_repo.get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    updates = data.model_dump(exclude_unset=True)
    provider = await model_repo.update_provider(db, provider, updates)
    await db.commit()
    await db.refresh(provider)
    return provider


@router.delete("/providers/{provider_id}", dependencies=[Depends(require_permission("model:manage"))])
async def delete_provider_endpoint(provider_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a provider."""
    provider = await model_repo.get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Check for referencing model configs
    configs = await model_repo.list_model_configs(db, include_inactive=True, provider_id=provider_id)
    if configs:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete provider '{provider.name}': {len(configs)} model config(s) still reference it.",
        )

    try:
        await model_repo.delete_provider(db, provider)
        await db.commit()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete provider: {str(e)}. Make sure no model configs reference it.",
        )
    return {"status": "deleted", "provider_id": provider_id}


# ---------------------------------------------------------------------------
# Model Configs
# ---------------------------------------------------------------------------

@router.get("/configs/selectable", response_model=List[ModelConfigSelectable], dependencies=[Depends(require_permission("model:view"))])
async def list_selectable_configs_endpoint(db: AsyncSession = Depends(get_db)):
    """List active chat/reasoning/vision configs for Agent dropdown."""
    return await model_repo.list_selectable_configs(db)


@router.get("/configs", response_model=List[ModelConfigResponse], dependencies=[Depends(require_permission("model:view"))])
async def list_model_configs_endpoint(
    include_inactive: bool = False,
    provider_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List model configurations."""
    return await model_repo.list_model_configs(
        db, include_inactive=include_inactive, provider_id=provider_id
    )


@router.post("/configs", response_model=ModelConfigResponse, status_code=201, dependencies=[Depends(require_permission("model:manage"))])
async def create_model_config_endpoint(
    data: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new model configuration."""
    provider = await model_repo.get_provider(db, data.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    config = await model_repo.create_model_config(db, data.model_dump())
    await db.commit()
    await db.refresh(config)
    # Re-fetch with provider info to avoid lazy-load issues
    config = await model_repo.get_model_config(db, config.id)
    return config


@router.get("/configs/{config_id}", response_model=ModelConfigResponse, dependencies=[Depends(require_permission("model:view"))])
async def get_model_config_endpoint(config_id: int, db: AsyncSession = Depends(get_db)):
    """Get model config by ID."""
    config = await model_repo.get_model_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Model config not found")
    return config


@router.patch("/configs/{config_id}", response_model=ModelConfigResponse, dependencies=[Depends(require_permission("model:manage"))])
async def update_model_config_endpoint(
    config_id: int,
    data: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a model configuration."""
    config = await model_repo.get_model_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Model config not found")

    updates = data.model_dump(exclude_unset=True)

    # Validate provider_id if updating
    if "provider_id" in updates:
        provider = await model_repo.get_provider(db, updates["provider_id"])
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

    config = await model_repo.update_model_config(db, config, updates)
    await db.commit()
    await db.refresh(config)
    config = await model_repo.get_model_config(db, config.id)
    return config


@router.delete("/configs/{config_id}", dependencies=[Depends(require_permission("model:manage"))])
async def delete_model_config_endpoint(config_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a model configuration."""
    config = await model_repo.get_model_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Model config not found")

    await model_repo.delete_model_config(db, config)
    await db.commit()
    return {"status": "deleted", "config_id": config_id}


@router.post("/configs/{config_id}/set-default", response_model=ModelConfigResponse, dependencies=[Depends(require_permission("model:manage"))])
async def set_default_model_config_endpoint(
    config_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Set a model config as default for its type."""
    config = await model_repo.get_model_config(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Model config not found")

    config = await model_repo.set_default_model_config(db, config_id, config.model_type)
    await db.commit()
    return config


@router.get("/configs/selectable", response_model=List[ModelConfigSelectable], dependencies=[Depends(require_permission("model:view"))])
async def list_selectable_configs_endpoint(db: AsyncSession = Depends(get_db)):
    """List active chat/reasoning/vision configs for Agent dropdown."""
    return await model_repo.list_selectable_configs(db)
