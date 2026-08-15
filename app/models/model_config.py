"""
Model configuration: providers, models, usage logs.
Model Center foundation.
"""

from typing import Optional, List
from sqlalchemy import String, Text, Integer, Float, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class ModelProvider(Base):
    """LLM provider (DeepSeek, OpenAI, Anthropic, Qwen, etc.)."""

    __tablename__ = "model_providers"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)  # deepseek, openai, anthropic, qwen
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)  # encrypted in production
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    models: Mapped[List["ModelConfig"]] = relationship(
        back_populates="provider", lazy="selectin", passive_deletes=True
    )


class ModelConfig(Base):
    """Model configuration (chat, reasoning, embedding, rerank, etc.)."""

    __tablename__ = "model_configs"

    provider_id: Mapped[int] = mapped_column(ForeignKey("model_providers.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g., "DeepSeek Chat"
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "deepseek-chat"
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # chat, reasoning, vision, embedding, rerank, speech
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    input_cost_per_1k: Mapped[Optional[float]] = mapped_column(Float)  # USD per 1K tokens
    output_cost_per_1k: Mapped[Optional[float]] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # default model for this type
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    provider: Mapped["ModelProvider"] = relationship(back_populates="models", passive_deletes=True)


class ModelUsageLog(Base):
    """Token usage and cost tracking per API call."""

    __tablename__ = "model_usage_logs"

    model_config_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_configs.id"), nullable=True, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success, error
    error: Mapped[Optional[str]] = mapped_column(Text)
