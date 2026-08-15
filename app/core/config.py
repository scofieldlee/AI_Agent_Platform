"""
Application configuration management.
Loads settings from environment variables / .env file.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "AI Agent Platform"
    debug: bool = True
    environment: str = "development"
    secret_key: str = "dev-secret-key"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://scofieldlee@localhost:5432/ai_agent_platform"
    database_sync_url: str = "postgresql://scofieldlee@localhost:5432/ai_agent_platform"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- DeepSeek ---
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    # --- Model Configuration ---
    chat_model: str = "deepseek-chat"
    chat_model_temperature: float = 0.3
    reasoning_model: str = "deepseek-reasoner"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512

    # --- Knowledge Base ---
    obsidian_vault_path: str = ""
    chunk_size: int = 500
    chunk_overlap: int = 50
    vector_search_top_k: int = 20
    rerank_top_k: int = 5
    knowledge_confidence_threshold: float = 0.75

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Auth / JWT ---
    jwt_secret_key: str = "super-secret-change-in-production-2026"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60          # 1 hour
    refresh_token_expire_days: int = 7             # 7 days

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Global settings instance
settings = Settings()
