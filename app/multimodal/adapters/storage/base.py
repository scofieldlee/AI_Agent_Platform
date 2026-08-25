"""Storage adapter — abstract base class.

业务层（AssetService 等）只依赖本抽象，不直接操作文件系统/对象存储，
未来切换 local → MinIO/OSS 只需新增实现。
"""

from abc import ABC, abstractmethod
from typing import Optional


class StorageAdapter(ABC):
    """统一文件存储接口。所有 path 均为相对存储根目录的逻辑路径。"""

    @abstractmethod
    async def upload(self, file_data: bytes, path: str) -> str:
        """写入文件，返回存储路径。"""

    @abstractmethod
    async def download(self, path: str) -> bytes:
        """读取文件内容。"""

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """删除文件，返回是否成功。"""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """文件是否存在。"""

    @abstractmethod
    async def get_url(self, path: str, expires: int = 3600) -> str:
        """获取访问 URL（本地实现返回 API 相对路径）。"""

    @abstractmethod
    async def get_metadata(self, path: str) -> dict:
        """获取文件元信息（size/mtime 等）。"""

    @abstractmethod
    async def copy(self, src: str, dst: str) -> bool:
        """复制文件。"""

    @abstractmethod
    async def move(self, src: str, dst: str) -> bool:
        """移动文件。"""

    @abstractmethod
    async def make_dir(self, path: str) -> None:
        """确保目录存在。"""

    @abstractmethod
    def abs_path(self, path: str) -> str:
        """逻辑路径 → 绝对路径（供 ffmpeg 等本地工具使用）。"""
