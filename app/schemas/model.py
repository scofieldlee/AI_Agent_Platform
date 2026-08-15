"""
Schemas for Model Center: providers and model configurations.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Model Provider
# ---------------------------------------------------------------------------

class ModelProviderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    base_url: str = Field(..., min_length=1, max_length=500)
    is_active: bool = True
    config: dict = Field(default_factory=dict)


class ModelProviderCreate(ModelProviderBase):
    api_key: str = Field(..., min_length=1, max_length=500)


class ModelProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    base_url: Optional[str] = Field(None, min_length=1, max_length=500)
    api_key: Optional[str] = Field(None, min_length=1, max_length=500)
    is_active: Optional[bool] = None
    config: Optional[dict] = None


class ModelProviderResponse(ModelProviderBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Model Config
# ---------------------------------------------------------------------------

class ModelConfigBase(BaseModel):
    provider_id: int
    name: str = Field(..., min_length=1, max_length=200)
    model_id: str = Field(..., min_length=1, max_length=100)
    model_type: str = Field(default="chat", pattern=r"^(chat|reasoning|vision|embedding|rerank|speech)$")
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    input_cost_per_1k: Optional[float] = Field(None, ge=0)
    output_cost_per_1k: Optional[float] = Field(None, ge=0)
    is_active: bool = True
    is_default: bool = False
    config: dict = Field(default_factory=dict)


class ModelConfigCreate(ModelConfigBase):
    pass


class ModelConfigUpdate(BaseModel):
    provider_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    model_id: Optional[str] = Field(None, min_length=1, max_length=100)
    model_type: Optional[str] = Field(None, pattern=r"^(chat|reasoning|vision|embedding|rerank|speech)$")
    max_tokens: Optional[int] = Field(None, ge=1, le=128000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    input_cost_per_1k: Optional[float] = Field(None, ge=0)
    output_cost_per_1k: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    config: Optional[dict] = None


class ModelConfigResponse(ModelConfigBase):
    id: int
    provider: Optional[ModelProviderResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ModelConfigSelectable(BaseModel):
    """Lightweight model config item for dropdowns."""
    id: int
    name: str
    model_id: str
    model_type: str
    provider_code: str
    provider_name: str
    is_default: bool
