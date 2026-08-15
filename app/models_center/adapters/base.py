"""
Base model adapter: unified interface for all LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class BaseModelAdapter(ABC):
    """Abstract base class for model adapters.

    All providers (DeepSeek, OpenAI, Claude, Qwen) implement this interface.
    ModelService routes to the correct adapter based on task type and config.
    """

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Optional[List[Dict]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Generate a chat completion.

        Args:
            system_prompt: System prompt defining agent behavior.
            user_prompt: User's input prompt.
            conversation_history: Previous messages [{role, content}].
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            Dict with: content, prompt_tokens, completion_tokens, total_tokens, model
        """
        ...

    @abstractmethod
    async def embed(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each is a list of floats).
        """
        ...
