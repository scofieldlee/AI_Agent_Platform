"""OCRRecognitionTool: extract text from images / PDFs / business cards.

Bridges Agent workflows with the Model Center's vision capability (Qwen-VL).
Accepts base64 payloads or public URLs; PDFs are rendered page-by-page via
PyMuPDF and each page is OCRed, then merged into a single text result.
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20MB
MAX_PDF_PAGES_HARD_LIMIT = 20

GENERAL_PROMPT = (
    "你是高精度 OCR 引擎。请逐字提取图片中的全部文字内容：\n"
    "1. 保持原有阅读顺序与排版结构（段落分明、表格用文本表格还原）\n"
    "2. 不要翻译、不要总结、不要添加图片中不存在的内容\n"
    "3. 无法辨认的字符用 [?] 标注\n"
    "4. 如果图片中没有文字，仅返回：（空白图片）"
)

BUSINESS_CARD_PROMPT = (
    "这是一张名片的图片。请提取名片上的信息并以 JSON 格式输出，"
    "字段包括：name（姓名）、name_en（英文名）、company（公司）、"
    "department（部门）、title（职位）、mobile（手机）、tel（电话）、"
    "email（邮箱）、website（网址）、address（地址）、other（其他信息）。"
    "名片上不存在的字段填 null，不要编造。只输出 JSON，不要其他解释。"
)


class OCRRecognitionTool(BaseTool):
    """Recognize text in images / PDF pages / business cards via vision model."""

    @property
    def name(self) -> str:
        return "ocr_recognition"

    @property
    def description(self) -> str:
        return (
            "OCR 文字识别工具。识别图片、PDF、名片等文件中的文字内容并结构化返回。"
            "支持两种场景：general（通用文字识别，保持排版）和 business_card"
            "（名片结构化提取，输出姓名/公司/职位/电话/邮箱等 JSON）。"
            "PDF 自动逐页转换识别（默认前 5 页）。"
        )

    @property
    def tool_type(self) -> str:
        return "knowledge"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": (
                        "文件内容的 base64（支持图片或 PDF，可带 data URL 前缀）。"
                        "与 file_url 二选一。"
                    ),
                },
                "file_url": {
                    "type": "string",
                    "description": "可访问的文件 URL（http/https 或本平台 /api/v1/multimodal/files/ 路径）。与 image_base64 二选一。",
                },
                "scene": {
                    "type": "string",
                    "enum": ["general", "business_card"],
                    "description": "识别场景：general=通用文字识别（默认），business_card=名片结构化提取",
                    "default": "general",
                },
                "max_pdf_pages": {
                    "type": "integer",
                    "description": "PDF 最多识别页数，默认 5，上限 20",
                    "default": 5,
                },
            },
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "合并后的全文"},
                "scene": {"type": "string"},
                "file_type": {"type": "string"},
                "page_count": {"type": "integer"},
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer"},
                            "text": {"type": "string"},
                        },
                    },
                },
                "structured": {"type": "object", "description": "business_card 场景的结构化结果"},
            },
        }

    async def execute(
        self,
        image_base64: str = None,
        file_url: str = None,
        scene: str = "general",
        max_pdf_pages: int = 5,
        agent_id: Any = None,
        conversation_id: Any = None,
        trace_id: Any = None,
        **kwargs,
    ) -> ToolResult:
        try:
            import pymupdf

            # 1. Resolve file bytes
            file_bytes, source = await self._resolve_file(image_base64, file_url)
            if not file_bytes:
                return ToolResult(
                    success=False,
                    error="未提供文件内容：请传入 image_base64 或 file_url",
                )
            if len(file_bytes) > MAX_FILE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"文件过大（{len(file_bytes) // 1024 // 1024}MB），上限 20MB",
                )

            # 2. Convert to images (PDF -> per-page PNG, others as-is)
            if file_bytes[:5] == b"%PDF-":
                pages = self._pdf_to_images(file_bytes, min(max(max_pdf_pages or 5, 1), MAX_PDF_PAGES_HARD_LIMIT))
                file_type = "pdf"
            else:
                mime = self._detect_mime(file_bytes)
                if not mime:
                    return ToolResult(
                        success=False,
                        error="无法识别的文件类型：仅支持图片（png/jpg/webp/gif/bmp）或 PDF",
                    )
                pages = [(1, file_bytes, mime)]
                file_type = "image"

            if not pages:
                return ToolResult(success=False, error="PDF 未解析出任何页面")

            # 3. OCR each page concurrently via vision model
            from app.models_center.service import ModelService

            service = ModelService()
            prompt = BUSINESS_CARD_PROMPT if scene == "business_card" else GENERAL_PROMPT

            async def ocr_page(page_no: int, data: bytes, mime: str) -> Dict[str, Any]:
                b64 = base64.b64encode(data).decode()
                result = await service.chat_with_images(
                    system_prompt="你是专业的 OCR 文字识别助手，只输出识别结果本身。",
                    user_prompt=prompt,
                    images=[{"base64": b64, "mime_type": mime}],
                    temperature=0.0,
                    max_tokens=4096,
                )
                return {"page": page_no, "text": (result.get("content") or "").strip()}

            results = list(await asyncio.gather(
                *(ocr_page(p, d, m) for p, d, m in pages)
            ))
            results.sort(key=lambda r: r["page"])

            full_text = "\n\n".join(
                (f"--- 第 {r['page']} 页 ---\n{r['text']}" if file_type == "pdf" and len(results) > 1 else r["text"])
                for r in results
            )

            # 4. Business card: parse structured JSON from first page
            structured: Optional[Dict[str, Any]] = None
            if scene == "business_card":
                structured = self._parse_card_json(results[0]["text"])

            logger.info(
                f"OCRRecognitionTool done | type={file_type} pages={len(results)} "
                f"scene={scene} source={source[:80]}"
            )
            return ToolResult(
                success=True,
                data={
                    "text": full_text,
                    "scene": scene,
                    "file_type": file_type,
                    "page_count": len(results),
                    "results": results,
                    "structured": structured,
                },
            )

        except Exception as e:
            logger.error(f"OCRRecognitionTool failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _resolve_file(
        self, image_base64: Optional[str], file_url: Optional[str]
    ) -> tuple:
        """Return (file_bytes, source_description)."""
        if image_base64:
            b64 = image_base64.strip()
            if b64.startswith("data:"):
                b64 = b64.split(",", 1)[1]
            try:
                return base64.b64decode(b64, validate=False), "base64"
            except Exception:
                return None, "base64"

        if file_url:
            url = file_url.strip()
            if url.startswith("/"):
                url = f"http://127.0.0.1:8000{url}"  # platform-internal file path
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content, url
        return None, ""

    @staticmethod
    def _pdf_to_images(pdf_bytes: bytes, max_pages: int) -> List[tuple]:
        """Render PDF pages to PNG bytes via PyMuPDF. Returns [(page_no, png_bytes, 'image/png')]."""
        import pymupdf

        pages = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc, start=1):
                if i > max_pages:
                    break
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))  # 2x zoom for accuracy
                pages.append((i, pix.tobytes("png"), "image/png"))
        return pages

    @staticmethod
    def _detect_mime(data: bytes) -> Optional[str]:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        if data[:3] == b"GIF":
            return "image/gif"
        if data[:2] == b"BM":
            return "image/bmp"
        return None

    @staticmethod
    def _parse_card_json(text: str) -> Optional[Dict[str, Any]]:
        """Best-effort parse of business card JSON from model output."""
        import json
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
