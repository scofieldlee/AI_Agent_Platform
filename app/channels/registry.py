"""
Channel adapter registry.
"""

from typing import Dict, Type

from app.channels.base import ChannelAdapter
from app.channels.dingtalk_adapter import DingTalkAdapter
from app.channels.feishu_adapter import FeishuAdapter

ADAPTER_REGISTRY: Dict[str, Type[ChannelAdapter]] = {
    "feishu": FeishuAdapter,
    "dingtalk": DingTalkAdapter,
    # "wecom": WeComAdapter,   # Phase 2
}

SUPPORTED_CHANNEL_TYPES = list(ADAPTER_REGISTRY.keys())


def get_adapter_class(channel_type: str) -> Type[ChannelAdapter]:
    if channel_type not in ADAPTER_REGISTRY:
        raise ValueError(f"不支持的渠道类型: {channel_type}（当前支持: {SUPPORTED_CHANNEL_TYPES}）")
    return ADAPTER_REGISTRY[channel_type]


def create_adapter(channel_id: int, channel_type: str, credentials: dict) -> ChannelAdapter:
    return get_adapter_class(channel_type)(channel_id, credentials)
