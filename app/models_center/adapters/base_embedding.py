"""
Base embedding adapter: unified interface for embedding providers.
"""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingAdapter(ABC):
    """Abstract base class for embedding adapters.

    Separated from chat adapters because a provider may offer chat but not
    embeddings (e.g., DeepSeek), and vice versa.
    """

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each is a list of floats).
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...
