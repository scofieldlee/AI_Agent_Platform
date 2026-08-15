"""
Local embedding adapter: calls the embedding microservice.

The embedding service runs on Python 3.9 (separate venv) because torch
doesn't support Python 3.13 on macOS x86_64.

Architecture:
    Main App (Python 3.13) --HTTP--> Embedding Service (Python 3.9 + torch)
                                       |
                                       v
                                 BAAI/bge-small-zh-v1.5 (512-dim)

The embedding service must be running at http://localhost:8001.
Start it with: .venv-embedding/bin/python embedding_service.py
"""

import logging
import asyncio
from typing import List

import httpx

from app.models_center.adapters.base_embedding import BaseEmbeddingAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_SERVICE_URL = "http://127.0.0.1:8001"


class LocalEmbeddingAdapter(BaseEmbeddingAdapter):
    """Embedding adapter that calls the local embedding microservice.

    The microservice uses BAAI/bge-small-zh-v1.5 (512-dim, Chinese-optimized).
    No API key required — runs entirely offline after model download.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self._model_name = model_name
        self._dimension = settings.embedding_dimension  # 512
        self._client = httpx.AsyncClient(timeout=120.0)  # long timeout for batch embedding

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings by calling the embedding microservice.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each is a list of floats).
        """
        if not texts:
            return []

        try:
            response = await self._client.post(
                f"{EMBEDDING_SERVICE_URL}/embed",
                json={"texts": texts},
            )
            response.raise_for_status()
            data = response.json()

            # Update dimension from service response
            self._dimension = data.get("dimension", self._dimension)

            return data["embeddings"]

        except httpx.ConnectError:
            logger.error(
                f"Cannot connect to embedding service at {EMBEDDING_SERVICE_URL}. "
                f"Start it with: .venv-embedding/bin/python embedding_service.py"
            )
            raise
        except Exception as e:
            logger.error(f"Embedding service call failed: {e}", exc_info=True)
            raise

    @property
    def dimension(self) -> int:
        return self._dimension
