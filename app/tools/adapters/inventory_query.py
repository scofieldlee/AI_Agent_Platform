"""
InventoryQueryTool: query product stock and pricing information.

Searches the inventory table by product name (ILIKE) or SKU.
Returns stock quantity, price, availability, and restock date.

Complements ProductQueryTool (which searches the knowledge base) by
providing real-time inventory data from the business database.
"""

import logging
from typing import Dict, Any, List

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Chinese status labels
STATUS_LABELS = {
    "active": "有货",
    "out_of_stock": "缺货",
    "discontinued": "停产",
}


class InventoryQueryTool(BaseTool):
    """Query product inventory and stock status.

    Searches by product name (fuzzy match) or SKU (exact match).
    Returns stock quantity, price, availability, and restock info.

    Parameters:
    - query: Product name or keyword (e.g., "无人机", "Q150", "F11")
    - sku: Exact SKU to look up
    """

    @property
    def name(self) -> str:
        return "inventory_query"

    @property
    def description(self) -> str:
        return (
            "查询库存状态工具。根据商品名称或SKU查询库存数量、价格、"
            "是否有货、预计到货时间。"
            "适用场景：顾客询问「有货吗」「多少钱」「什么时候能到货」时调用。"
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
                    "description": "商品名称或关键词，如 '无人机'、'Q150'、'F11'",
                },
                "sku": {
                    "type": "string",
                    "description": "精确SKU码，如 'RK-F11PRO'",
                },
            },
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
                            "sku": {"type": "string"},
                            "product_name": {"type": "string"},
                            "category": {"type": "string"},
                            "stock_quantity": {"type": "integer"},
                            "price": {"type": "number"},
                            "status": {"type": "string"},
                            "status_label": {"type": "string"},
                            "restock_date": {"type": "string"},
                            "in_stock": {"type": "boolean"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        }

    async def execute(
        self,
        query: str = "",
        sku: str = "",
        **kwargs,
    ) -> ToolResult:
        """Query inventory by product name or SKU.

        Args:
            query: Product name or keyword for fuzzy search.
            sku: Exact SKU for precise lookup.

        Returns:
            ToolResult with matching inventory items.
        """
        import re

        try:
            if not query and not sku:
                return ToolResult(
                    success=True,
                    data={
                        "products": [],
                        "total": 0,
                        "message": "未提供搜索关键词或SKU，无法查询库存。",
                    },
                )

            from app.database.session import async_session_factory
            from sqlalchemy import text

            # Preprocess query: extract meaningful keywords from natural language
            # e.g., "F11S Pro无人机有货吗？多少钱？" → ["F11S", "Pro", "无人机"]
            search_query = query
            if not sku:
                # Remove common Chinese question words and punctuation
                cleaned = re.sub(
                    r"[有货吗多少钱价格参数规格介绍对比区别推荐建议"
                    r"怎么样好不好什么哪个查询看问问一下告诉知道"
                    r"？?！!。，,.\s]+",
                    " ",
                    query,
                )
                # Split into tokens and filter out very short ones
                tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 2]
                if not tokens:
                    # Fallback: try the original query as a single pattern
                    tokens = [query]

            async with async_session_factory() as session:
                if sku:
                    # Exact SKU match
                    sql = text("""
                        SELECT sku, product_name, category, stock_quantity,
                               price, currency, status, restock_date,
                               created_at, updated_at
                        FROM inventory
                        WHERE sku = :sku
                    """)
                    results = await session.execute(sql, {"sku": sku})
                    rows = results.fetchall()
                else:
                    # Fuzzy match: search for ANY token in product name or category
                    # Build dynamic OR conditions for each token
                    conditions = []
                    params = {}
                    for i, token in enumerate(tokens):
                        conditions.append(f"product_name ILIKE :pat{i}")
                        conditions.append(f"category ILIKE :pat{i}")
                        conditions.append(f"sku ILIKE :pat{i}")
                        params[f"pat{i}"] = f"%{token}%"

                    where_clause = " OR ".join(conditions)

                    sql = text(f"""
                        SELECT sku, product_name, category, stock_quantity,
                               price, currency, status, restock_date,
                               created_at, updated_at
                        FROM inventory
                        WHERE {where_clause}
                        ORDER BY
                            CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                            stock_quantity DESC
                        LIMIT 10
                    """)
                    results = await session.execute(sql, params)
                    rows = results.fetchall()

            # Build structured results
            products: List[Dict[str, Any]] = []
            for row in rows:
                status = row.status or "unknown"
                stock_qty = row.stock_quantity or 0
                in_stock = stock_qty > 0 and status == "active"

                products.append({
                    "sku": row.sku,
                    "product_name": row.product_name,
                    "category": row.category,
                    "stock_quantity": stock_qty,
                    "price": float(row.price),
                    "currency": row.currency,
                    "status": status,
                    "status_label": STATUS_LABELS.get(status, status),
                    "restock_date": row.restock_date.isoformat() if row.restock_date else None,
                    "in_stock": in_stock,
                })

            total = len(products)
            logger.info(
                f"InventoryQuery executed | query={query} sku={sku} | results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "products": products,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"InventoryQuery failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
