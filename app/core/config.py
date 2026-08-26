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

    # --- Multimodal Knowledge Base ---
    multimodal_storage_path: str = "uploads/multimodal"   # 本地存储根目录（相对项目根或绝对路径）
    multimodal_max_image_mb: int = 50                     # 图片大小上限 (MB)
    multimodal_max_video_mb: int = 500                    # 视频大小上限 (MB)
    multimodal_max_audio_mb: int = 200                    # 音频大小上限 (MB)
    multimodal_max_ppt_mb: int = 100                      # PPT 大小上限 (MB)

    # --- DashScope (通义千问) ---
    dashscope_api_key: str = ""                           # DASHSCOPE_API_KEY (Plan Key，聊天/视觉)
    dashscope_base_url: str = ""                          # DASHSCOPE_BASE_URL (OpenAI 兼容端点；空则用标准端点)
    dashscope_embedding_api_key: str = ""                 # DASHSCOPE_EMBEDDING_API_KEY (旧 Key，embedding/vision 原生 SDK)
    qwen_vl_model: str = "qwen3.7-plus"                    # 视觉理解模型（Token Plan 端点原生多模态）
    qwen_video_t2v_model: str = "happyhorse-1.1-t2v"       # 文生视频模型（Token Plan 内）
    qwen_video_i2v_model: str = "happyhorse-1.1-i2v"       # 图生视频模型（首帧驱动，Token Plan 内）
    qwen_video_poll_interval_seconds: int = 15             # 异步任务轮询间隔（官方建议 15s）
    qwen_video_max_wait_seconds: int = 900                 # 视频生成最长等待时间（任务通常 1-5 分钟）
    qwen_video_download_timeout_seconds: int = 600         # 生成结果视频下载超时
    qwen_multimodal_embedding_model: str = "multimodal-embedding-one-peace-v1"
    qwen_text_embedding_model: str = "text-embedding-v4"  # 降级用文本 Embedding（1024 维，与多模态同维）
    qwen_asr_model: str = "paraformer-v2"                 # 语音识别模型
    multimodal_embedding_dimension: int = 1024            # 通义多模态 Embedding 维度

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
