"""
OrderQueryTool: query order status and tracking information.

Searches the orders table by order number or customer phone number.
Returns structured order data including status, tracking, and delivery info.

This is the second concrete tool in the Tool Center, complementing
ProductQueryTool for a full customer service experience.
"""

import logging
from typing import Dict, Any, List

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Chinese status labels for display
STATUS_LABELS = {
    "pending": "待付款",
    "processing": "处理中",
    "shipped": "已发货",
    "delivered": "已签收",
    "cancelled": "已取消",
    "refunded": "已退款",
}


class OrderQueryTool(BaseTool):
    """Query order status and tracking information.

    Searches by order number (exact match) or customer phone number.
    Returns order details including product, status, tracking number, and carrier.

    Parameters:
    - order_number: Order number (e.g., "RK20260801001")
    - phone: Customer phone number for lookup
    - query: Free-text query — will try to extract order number or phone from it
    """

    @property
    def name(self) -> str:
        return "order_query"

    @property
    def description(self) -> str:
        return (
            "查询订单状态工具。根据订单号或手机号查询订单的物流状态、"
            "快递单号、承运商、商品信息。"
            "适用场景：顾客询问「我的订单到哪了」「发货了吗」「快递单号是多少」时调用。"
        )

    @property
    def tool_type(self) -> str:
        return "business"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "订单号，如 'RK20260801001'",
                },
                "phone": {
                    "type": "string",
                    "description": "顾客手机号，用于按手机号查询订单",
                },
                "query": {
                    "type": "string",
                    "description": "自由文本查询，工具会尝试从中提取订单号或手机号",
                },
            },
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "orders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "order_number": {"type": "string"},
                            "customer_name": {"type": "string"},
                            "product_name": {"type": "string"},
                            "quantity": {"type": "integer"},
                            "total_amount": {"type": "number"},
                            "status": {"type": "string"},
                            "status_label": {"type": "string"},
                            "tracking_number": {"type": "string"},
                            "carrier": {"type": "string"},
                            "created_at": {"type": "string"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        }

    async def execute(
        self,
        order_number: str = "",
        phone: str = "",
        query: str = "",
        **kwargs,
    ) -> ToolResult:
        """Query orders by order number, phone, or free-text query.

        Args:
            order_number: Exact order number to look up.
            phone: Customer phone for phone-based lookup.
            query: Free text — will try to extract order number or phone.

        Returns:
            ToolResult with matching orders.
        """
        import re

        try:
            # If only query is provided, try to extract order number or phone
            if not order_number and not phone and query:
                # Extract order number pattern: RK + digits
                order_match = re.search(r"RK\d{9,}", query.upper())
                if order_match:
                    order_number = order_match.group()

                # Extract phone pattern: 1[3-9]\d{9}
                phone_match = re.search(r"1[3-9]\d{9}", query)
                if phone_match:
                    phone = phone_match.group()

            if not order_number and not phone:
                return ToolResult(
                    success=True,
                    data={
                        "orders": [],
                        "total": 0,
                        "message": "未提供订单号或手机号，无法查询。请顾客提供订单号或下单手机号。",
                    },
                )

            from app.database.session import async_session_factory
            from sqlalchemy import text

            async with async_session_factory() as session:
                if order_number:
                    # Exact match on order number
                    sql = text("""
                        SELECT order_number, customer_name, customer_phone,
                               product_name, product_sku, quantity, total_amount,
                               currency, status, tracking_number, carrier,
                               shipping_address, created_at, updated_at
                        FROM orders
                        WHERE order_number = :order_number
                    """)
                    results = await session.execute(
                        sql, {"order_number": order_number}
                    )
                    rows = results.fetchall()
                else:
                    # Match on phone
                    sql = text("""
                        SELECT order_number, customer_name, customer_phone,
                               product_name, product_sku, quantity, total_amount,
                               currency, status, tracking_number, carrier,
                               shipping_address, created_at, updated_at
                        FROM orders
                        WHERE customer_phone = :phone
                        ORDER BY created_at DESC
                        LIMIT 5
                    """)
                    results = await session.execute(sql, {"phone": phone})
                    rows = results.fetchall()

            # Build structured results
            orders: List[Dict[str, Any]] = []
            for row in rows:
                status = row.status or "unknown"
                orders.append({
                    "order_number": row.order_number,
                    "customer_name": row.customer_name,
                    "customer_phone": row.customer_phone,
                    "product_name": row.product_name,
                    "product_sku": row.product_sku,
                    "quantity": row.quantity,
                    "total_amount": float(row.total_amount),
                    "currency": row.currency,
                    "status": status,
                    "status_label": STATUS_LABELS.get(status, status),
                    "tracking_number": row.tracking_number or "暂无",
                    "carrier": row.carrier or "暂无",
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })

            total = len(orders)
            logger.info(
                f"OrderQuery executed | order_number={order_number} "
                f"phone={phone} | results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "orders": orders,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"OrderQuery failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
