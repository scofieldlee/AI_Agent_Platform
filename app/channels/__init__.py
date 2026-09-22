"""
Channel integration package: IM bots (Feishu / DingTalk / WeCom) that talk
to agents through the standard conversation pipeline.
"""

from app.channels.base import ChannelAdapter, InboundMessage, OutboundMessage
from app.channels.registry import (
    ADAPTER_REGISTRY,
    SUPPORTED_CHANNEL_TYPES,
    create_adapter,
    get_adapter_class,
)

__all__ = [
    "ChannelAdapter", "InboundMessage", "OutboundMessage",
    "ADAPTER_REGISTRY", "SUPPORTED_CHANNEL_TYPES",
    "create_adapter", "get_adapter_class",
]
