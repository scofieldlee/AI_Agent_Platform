"""
Channel adapter abstractions.

Every IM integration (Feishu / DingTalk / WeCom) implements ChannelAdapter:
receive inbound messages from the platform, reply outbound, and provide a
lightweight credential test. The channel worker is provider-agnostic and
only speaks in InboundMessage / OutboundMessage terms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InboundMessage:
    """Normalized inbound IM message."""

    channel_id: int
    message_id: str                      # platform message id (for dedup)
    external_user_id: str                # sender open_id / userid
    external_chat_id: str                # p2p chat id or group chat id
    chat_type: str                       # "p2p" | "group"
    text: str                            # cleaned text content (mentions stripped)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Normalized outbound reply."""

    external_chat_id: str
    text: str


class ChannelAdapter(ABC):
    """Abstract IM channel adapter."""

    channel_type: str = "abstract"

    def __init__(self, channel_id: int, credentials: Dict[str, Any]):
        self.channel_id = channel_id
        self.credentials = credentials or {}

    @abstractmethod
    async def test_credentials(self) -> Dict[str, Any]:
        """Validate credentials without opening the long connection.

        Returns {"success": bool, "detail": str}.
        """

    @abstractmethod
    def start_receiving(self, on_message, loop=None) -> None:
        """Open the platform long connection and start delivering
        InboundMessage objects to the async ``on_message`` callback.

        This call blocks (runs the platform client loop) — the worker runs
        it in a dedicated thread per channel and passes its asyncio loop so
        the adapter can bridge sync platform events into the loop.
        """

    @abstractmethod
    async def send_text(self, external_chat_id: str, text: str) -> None:
        """Send a text reply to a chat."""

    def stop(self) -> None:
        """Stop the connection (best effort)."""
