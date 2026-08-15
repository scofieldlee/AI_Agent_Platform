"""
ProductQueryTool: query product information from the knowledge base.

This is the first concrete tool in the Tool Center.
It queries pgvector for product-related chunks and returns structured data.

Future: can be extended to query an external ERP/product database instead of
(or in addition to) the knowledge base.
"""

import logging
from typing import Dict, Any, List

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ProductQueryTool(BaseTool):
    """Query product information from the knowledge base.

    Searches the pgvector knowledge base for product-related content.
    Returns structured results with product name, section, content, and relevance score.

    Parameters:
    - query: Product name or feature to search (e.g., "Q150", "无人机")
    - max_results: Maximum number of results (default 5)
    """

    @property
    def name(self) -> str:
        return "product_query"

    @property
    def description(self) -> str:
        return (
            "查询商品信息工具。根据商品名称或关键词搜索知识库，"
            "返回结构化商品数据（商品名称、内容片段、相关度）。"
            "适用场景：顾客询问具体商品参数、价格、特点、对比时调用。"
        )

    @property
    def tool_type(self) -> str:
        return "business"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "商品名称或搜索关键词，如 'Q150'、'无人机'、'F11'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 5",
                },
            },
            "required": ["query"],
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "section": {"type": "string"},
                            "content": {"type": "string"},
                            "score": {"type": "number"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        }

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        """Search for product information in the knowledge base.

        Args:
            query: Product name or search keyword.
            max_results: Maximum results to return.

        Returns:
            ToolResult with structured product data.
        """
        try:
            # 1. Embed the query
            from app.models_center.service import ModelService
            model_service = ModelService()
            query_embedding = await model_service.embed([query])
            query_vector = query_embedding[0]

            # 2. Vector search in pgvector
            from app.database.session import async_session_factory
            from sqlalchemy import text

            async with async_session_factory() as session:
                sql = text("""
                    SELECT id, content, section, metadata as meta,
                           1 - (embedding <=> CAST(:query_vector AS vector)) as score
                    FROM chunks
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vector AS vector)
                    LIMIT :max_results
                """)

                results = await session.execute(
                    sql,
                    {"query_vector": str(query_vector), "max_results": max_results},
                )
                rows = results.fetchall()

            # 3. Build structured results
            products: List[Dict[str, Any]] = []
            for row in rows:
                score = float(row.score) if row.score else 0.0
                meta = row.meta if row.meta else {}
                title = (
                    meta.get("title", meta.get("商品名称", "Unknown"))
                    if isinstance(meta, dict) else "Unknown"
                )
                section = row.section or "General"
                content = row.content

                # Extract price if present in content (simple regex)
                price = self._extract_price(content)

                products.append({
                    "title": str(title),
                    "section": section,
                    "content": content[:500],
                    "price": price,
                    "score": round(score, 4),
                })

            total = len(products)
            logger.info(
                f"ProductQuery executed | query={query[:50]} | "
                f"results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "products": products,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"ProductQuery failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    @staticmethod
    def _extract_price(content: str) -> str:
        """Extract price from content text (simple pattern matching)."""
        import re

        # Match patterns like $59.99, USD $329.99, $269.99
        match = re.search(r"(?:USD\s*)?\$(\d+(?:\.\d{2})?)", content)
        if match:
            return f"${match.group(1)}"

        # Match Chinese price patterns
        match = re.search(r"(\d+(?:\.\d{2})?)\s*(?:美元|USD)", content)
        if match:
            return f"${match.group(1)}"

        return ""
