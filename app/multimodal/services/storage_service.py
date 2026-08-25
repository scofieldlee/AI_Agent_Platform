"""存储服务 — 统一文件存储入口 + 路径策略.

业务层只依赖本服务，不直接操作文件系统。
"""

import logging
import mimetypes
from typing import Optional

import aiofiles
import aiofiles.os

from app.multimodal.adapters import get_storage
from app.multimodal.adapters.storage.base import StorageAdapter
from app.multimodal.adapters.storage.local_storage import LocalStorageAdapter

logger = logging.getLogger(__name__)


def get_storage_adapter() -> StorageAdapter:
    return get_storage()


async def save_original(kb_id: int, asset_id: int, file_data: bytes,
                        filename: str) -> str:
    """保存原始文件（永不被 AI 流程修改）。"""
    storage = get_storage()
    path = LocalStorageAdapter.original_path(kb_id, asset_id, filename)
    await storage.upload(file_data, path)
    return path


async def save_thumbnail(kb_id: int, asset_id: int, image_data: bytes) -> str:
    """保存缩略图。"""
    storage = get_storage()
    path = LocalStorageAdapter.thumbnail_path(kb_id, asset_id)
    await storage.upload(image_data, path)
    return path


async def save_preview(kb_id: int, asset_id: int, data: bytes, ext: str = "mp4") -> str:
    """保存预览文件。"""
    storage = get_storage()
    path = LocalStorageAdapter.preview_path(kb_id, asset_id) + f".{ext}"
    await storage.upload(data, path)
    return path


def derived_file_path(kb_id: int, asset_id: int, name: str) -> str:
    """衍生文件路径（关键帧/ASR文本等），处理器直接用本地写。"""
    return f"{LocalStorageAdapter.derived_dir(kb_id, asset_id)}/{name}"


async def ensure_asset_dirs(kb_id: int, asset_id: int) -> None:
    """确保素材标准目录结构存在。"""
    storage = get_storage()
    base = LocalStorageAdapter.asset_dir(kb_id, asset_id)
    for sub in ("original", "preview", "thumbnail", "derived"):
        await storage.make_dir(f"{base}/{sub}")


async def delete_asset_files(kb_id: int, asset_id: int) -> bool:
    """永久删除素材时清理整个文件目录。"""
    storage = get_storage()
    if isinstance(storage, LocalStorageAdapter):
        return await storage.delete_dir(LocalStorageAdapter.asset_dir(kb_id, asset_id))
    return False


async def read_file(path: str) -> bytes:
    return await get_storage().download(path)


def abs_file_path(path: str) -> str:
    """逻辑路径 → 绝对路径（ffmpeg / Vision API 等本地工具用）。"""
    return get_storage().abs_path(path)


def guess_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def file_url(path: Optional[str]) -> Optional[str]:
    """存储路径 → 前端可访问的 URL（本地存储走 API 端点）。"""
    if not path:
        return None
    return f"/api/v1/multimodal/files/{path}"
