"""
Multimodal Knowledge Base module-level constants.

Status machines and enumerations shared across models / services / processors.
"""

from typing import List


class AssetStatus:
    """Asset 状态机: UPLOADED → PROCESSING → ANALYZING → REVIEW_REQUIRED → INDEXING → READY

    异常分支: FAILED；删除分支: DELETED（软删除，进回收站）。
    """
    UPLOADED = "uploaded"
    PROCESSING = "processing"            # 缩略图/预览/关键帧等本地处理中
    ANALYZING = "analyzing"              # AI 分析中
    REVIEW_REQUIRED = "review_required"  # 等待人工审核
    INDEXING = "indexing"                # 向量化/建索引中
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"

    ALL = [UPLOADED, PROCESSING, ANALYZING, REVIEW_REQUIRED, INDEXING, READY, FAILED, DELETED]


class TaskStatus:
    """ProcessingTask 状态机: pending → processing → success/failed/cancelled"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType:
    """ProcessingTask 任务类型"""
    UPLOAD = "upload"
    THUMBNAIL = "thumbnail"
    PREVIEW = "preview"
    KEYFRAME = "keyframe"
    SHOT_DETECT = "shot_detect"
    ANALYSIS = "analysis"
    OCR = "ocr"
    ASR = "asr"
    SEGMENT = "segment"
    SLIDE_SPLIT = "slide_split"
    EMBEDDING = "embedding"
    INDEX = "index"


class FileType:
    """素材类型"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    PPT = "ppt"
    PDF = "pdf"
    DOCUMENT = "document"
    OTHER = "other"

    ALL = [IMAGE, VIDEO, AUDIO, PPT, PDF, DOCUMENT, OTHER]


class UnitType:
    """KnowledgeUnit 类型: 图片整体 / 视频镜头 / 音频分段 / PPT 页 / 文档片段"""
    IMAGE = "image"
    SHOT = "shot"
    SEGMENT = "segment"
    SLIDE = "slide"
    TEXT = "text"


class MetadataType:
    """Metadata 三来源: system(程序) / ai(模型) / user(人工)"""
    SYSTEM = "system"
    AI = "ai"
    USER = "user"


class TagSource:
    """标签来源: ai(自动生成) / user(人工)"""
    AI = "ai"
    USER = "user"


class UnitStatus:
    PENDING = "pending"
    INDEXED = "indexed"
    ERROR = "error"


class EmbeddingType:
    TEXT = "text"
    IMAGE = "image"
    MULTIMODAL = "multimodal"


class RelationType:
    RELATED = "related"
    REFERENCE = "reference"
    DERIVED_FROM = "derived_from"
    BELONGS_TO = "belongs_to"
    SIMILAR = "similar"
    ALTERNATIVE = "alternative"

    ALL = [RELATED, REFERENCE, DERIVED_FROM, BELONGS_TO, SIMILAR, ALTERNATIVE]


# 各类型素材的大小上限（MB）
MAX_FILE_SIZE_MB = {
    FileType.IMAGE: 50,
    FileType.VIDEO: 500,
    FileType.AUDIO: 200,
    FileType.PPT: 100,
    FileType.PDF: 100,
    FileType.DOCUMENT: 100,
    FileType.OTHER: 100,
}

# 扩展名 → 素材类型映射
EXTENSION_FILE_TYPE_MAP = {
    "jpg": FileType.IMAGE, "jpeg": FileType.IMAGE, "png": FileType.IMAGE,
    "gif": FileType.IMAGE, "webp": FileType.IMAGE, "bmp": FileType.IMAGE,
    "tiff": FileType.IMAGE, "svg": FileType.IMAGE, "heic": FileType.IMAGE,
    "mp4": FileType.VIDEO, "mov": FileType.VIDEO, "avi": FileType.VIDEO,
    "mkv": FileType.VIDEO, "webm": FileType.VIDEO, "flv": FileType.VIDEO,
    "wmv": FileType.VIDEO, "m4v": FileType.VIDEO,
    "mp3": FileType.AUDIO, "wav": FileType.AUDIO, "flac": FileType.AUDIO,
    "aac": FileType.AUDIO, "ogg": FileType.AUDIO, "m4a": FileType.AUDIO,
    "wma": FileType.AUDIO,
    "ppt": FileType.PPT, "pptx": FileType.PPT,
    "pdf": FileType.PDF,
    "doc": FileType.DOCUMENT, "docx": FileType.DOCUMENT,
    "xls": FileType.DOCUMENT, "xlsx": FileType.DOCUMENT,
    "txt": FileType.DOCUMENT, "md": FileType.DOCUMENT,
}

# 素材编码前缀（用于 asset_code 生成）
ASSET_CODE_PREFIX = {
    FileType.IMAGE: "IMG",
    FileType.VIDEO: "VIDEO",
    FileType.AUDIO: "AUDIO",
    FileType.PPT: "PPT",
    FileType.PDF: "PDF",
    FileType.DOCUMENT: "DOC",
    FileType.OTHER: "FILE",
}


def detect_file_type(filename: str) -> str:
    """根据扩展名推断素材类型，未知返回 other。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXTENSION_FILE_TYPE_MAP.get(ext, FileType.OTHER)


def allowed_file_types() -> List[str]:
    """上传允许的素材类型列表。"""
    return [FileType.IMAGE, FileType.VIDEO, FileType.AUDIO, FileType.PPT,
            FileType.PDF, FileType.DOCUMENT]
