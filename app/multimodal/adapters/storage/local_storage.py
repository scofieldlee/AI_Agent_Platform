"""Local filesystem storage adapter (V1.0 默认实现).

目录结构:
{base_path}/{kb_id}/assets/{asset_id}/
    original/   # 原始文件（永不被 AI 流程修改）
    preview/    # Web 预览版
    thumbnail/  # 缩略图
    derived/    # 衍生文件（关键帧/转写文本/字幕等）
"""

import os
import shutil
import time
from datetime import datetime

import aiofiles
import aiofiles.os

from app.multimodal.adapters.storage.base import StorageAdapter


class LocalStorageAdapter(StorageAdapter):
    """本地文件系统存储。"""

    def __init__(self, base_path: str):
        self._base_path = os.path.abspath(base_path)
        os.makedirs(self._base_path, exist_ok=True)

    # ---- 路径工具 ----
    def abs_path(self, path: str) -> str:
        """逻辑路径 → 绝对路径，并做目录穿越防护。"""
        abs_p = os.path.abspath(os.path.join(self._base_path, path))
        if not abs_p.startswith(self._base_path):
            raise ValueError(f"Path escapes storage root: {path}")
        return abs_p

    async def make_dir(self, path: str) -> None:
        os.makedirs(self.abs_path(path), exist_ok=True)

    # ---- 基本操作 ----
    async def upload(self, file_data: bytes, path: str) -> str:
        abs_p = self.abs_path(path)
        os.makedirs(os.path.dirname(abs_p), exist_ok=True)
        async with aiofiles.open(abs_p, "wb") as f:
            await f.write(file_data)
        return path

    async def download(self, path: str) -> bytes:
        abs_p = self.abs_path(path)
        if not os.path.exists(abs_p):
            raise FileNotFoundError(f"File not found: {path}")
        async with aiofiles.open(abs_p, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        abs_p = self.abs_path(path)
        if os.path.isfile(abs_p):
            os.remove(abs_p)
            return True
        return False

    async def delete_dir(self, path: str) -> bool:
        """删除目录（永久删除素材时清理整个 asset 目录）。"""
        abs_p = self.abs_path(path)
        if os.path.isdir(abs_p):
            shutil.rmtree(abs_p)
            return True
        return False

    async def exists(self, path: str) -> bool:
        return os.path.exists(self.abs_path(path))

    async def get_url(self, path: str, expires: int = 3600) -> str:
        # 本地存储：通过 API 端点提供访问
        return f"/api/v1/multimodal/files/{path}"

    async def get_metadata(self, path: str) -> dict:
        abs_p = self.abs_path(path)
        if not os.path.exists(abs_p):
            raise FileNotFoundError(f"File not found: {path}")
        stat = os.stat(abs_p)
        return {
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "is_file": os.path.isfile(abs_p),
        }

    async def copy(self, src: str, dst: str) -> bool:
        src_abs, dst_abs = self.abs_path(src), self.abs_path(dst)
        if not os.path.exists(src_abs):
            return False
        os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
        shutil.copy2(src_abs, dst_abs)
        return True

    async def move(self, src: str, dst: str) -> bool:
        src_abs, dst_abs = self.abs_path(src), self.abs_path(dst)
        if not os.path.exists(src_abs):
            return False
        os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
        shutil.move(src_abs, dst_abs)
        return True

    # ---- 路径构造（标准目录结构）----
    @staticmethod
    def asset_dir(kb_id: int, asset_id: int) -> str:
        return f"{kb_id}/assets/{asset_id}"

    @staticmethod
    def original_path(kb_id: int, asset_id: int, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        return f"{kb_id}/assets/{asset_id}/original/original.{ext}"

    @staticmethod
    def preview_path(kb_id: int, asset_id: int) -> str:
        return f"{kb_id}/assets/{asset_id}/preview/preview"

    @staticmethod
    def thumbnail_path(kb_id: int, asset_id: int) -> str:
        return f"{kb_id}/assets/{asset_id}/thumbnail/thumbnail.jpg"

    @staticmethod
    def derived_dir(kb_id: int, asset_id: int) -> str:
        return f"{kb_id}/assets/{asset_id}/derived"
