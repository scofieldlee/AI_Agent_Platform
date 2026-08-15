"""
RefundQueryTool: query refund and return/exchange status.

Searches the refunds table by refund number, order number, or customer phone.
Returns structured refund data including status, amount, type, and reason.

This tool extends the customer service agent's after-sale capabilities,
complementing OrderQueryTool for a full post-purchase experience.
"""

import logging
import re
from typing import Dict, Any, List

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Chinese status labels for display
STATUS_LABELS = {
    "pending": "待审核",
    "processing": "处理中",
    "approved": "已通过",
    "rejected": "已拒绝",
    "completed": "已完成",
}

# Refund type labels
TYPE_LABELS = {
    "refund": "仅退款",
    "return_exchange": "退货换货",
}


class RefundQueryTool(BaseTool):
    """Query refund and return/exchange status.

    Searches by refund number (exact match), order number (exact match),
    or customer phone number. Returns refund details including status,
    amount, type, and reason.

    Parameters:
    - refund_number: Refund number (e.g., "RF20260803001")
    - order_number: Order number to find associated refund
    - phone: Customer phone number for lookup
    - query: Free-text query — will try to extract refund/order number or phone
    """

    @property
    def name(self) -> str:
        return "refund_query"

    @property
    def description(self) -> str:
        return (
            "查询退款/退换货状态工具。根据退款单号、订单号或手机号查询退款申请的"
            "处理进度、退款金额、退款类型和原因。"
            "适用场景：顾客询问「我的退款到哪一步了」「退款什么时候到账」"
            "「退货申请通过了吗」「怎么退款」时调用。"
        )

    @property
    def tool_type(self) -> str:
        return "business"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "refund_number": {
                    "type": "string",
                    "description": "退款单号，如 'RF20260803001'",
                },
                "order_number": {
                    "type": "string",
                    "description": "订单号，用于查询该订单关联的退款",
                },
                "phone": {
                    "type": "string",
                    "description": "顾客手机号，用于按手机号查询退款",
                },
                "query": {
                    "type": "string",
                    "description": "自由文本查询，工具会尝试从中提取退款单号、订单号或手机号",
                },
            },
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "refunds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "refund_number": {"type": "string"},
                            "order_number": {"type": "string"},
                            "customer_name": {"type": "string"},
                            "product_name": {"type": "string"},
                            "refund_amount": {"type": "number"},
                            "refund_type": {"type": "string"},
                            "refund_type_label": {"type": "string"},
                            "status": {"type": "string"},
                            "status_label": {"type": "string"},
                            "reason": {"type": "string"},
                            "created_at": {"type": "string"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        }

    async def execute(
        self,
        refund_number: str = "",
        order_number: str = "",
        phone: str = "",
        query: str = "",
        **kwargs,
    ) -> ToolResult:
        """Query refunds by refund number, order number, phone, or free-text.

        Args:
            refund_number: Exact refund number to look up.
            order_number: Order number to find associated refund.
            phone: Customer phone for phone-based lookup.
            query: Free text — will try to extract identifiers.

        Returns:
            ToolResult with matching refunds.
        """
        try:
            # If only query is provided, try to extract identifiers
            if not refund_number and not order_number and not phone and query:
                # Extract refund number pattern: RF + digits
                refund_match = re.search(r"RF\d{8,}", query.upper())
                if refund_match:
                    refund_number = refund_match.group()

                # Extract order number pattern: RK + digits
                order_match = re.search(r"RK\d{9,}", query.upper())
                if order_match:
                    order_number = order_match.group()

                # Extract phone pattern: 1[3-9]\d{9}
                phone_match = re.search(r"1[3-9]\d{9}", query)
                if phone_match:
                    phone = phone_match.group()

            if not refund_number and not order_number and not phone:
                return ToolResult(
                    success=True,
                    data={
                        "refunds": [],
                        "total": 0,
                        "message": "未提供退款单号、订单号或手机号，无法查询退款信息。",
                    },
                )

            from app.database.session import async_session_factory
            from sqlalchemy import text

            async with async_session_factory() as session:
                if refund_number:
                    sql = text("""
                        SELECT refund_number, order_number, customer_name, customer_phone,
                               product_name, product_sku, quantity, refund_amount,
                               currency, refund_type, status, reason,
                               created_at, updated_at
                        FROM refunds
                        WHERE refund_number = :refund_number
                    """)
                    results = await session.execute(sql, {"refund_number": refund_number})
                    rows = results.fetchall()
                elif order_number:
                    sql = text("""
                        SELECT refund_number, order_number, customer_name, customer_phone,
                               product_name, product_sku, quantity, refund_amount,
                               currency, refund_type, status, reason,
                               created_at, updated_at
                        FROM refunds
                        WHERE order_number = :order_number
                        ORDER BY created_at DESC
                    """)
                    results = await session.execute(sql, {"order_number": order_number})
                    rows = results.fetchall()
                else:
                    sql = text("""
                        SELECT refund_number, order_number, customer_name, customer_phone,
                               product_name, product_sku, quantity, refund_amount,
                               currency, refund_type, status, reason,
                               created_at, updated_at
                        FROM refunds
                        WHERE customer_phone = :phone
                        ORDER BY created_at DESC
                        LIMIT 5
                    """)
                    results = await session.execute(sql, {"phone": phone})
                    rows = results.fetchall()

            # Build structured results
            refunds: List[Dict[str, Any]] = []
            for row in rows:
                status = row.status or "unknown"
                refund_type = row.refund_type or "refund"
                refunds.append({
                    "refund_number": row.refund_number,
                    "order_number": row.order_number,
                    "customer_name": row.customer_name,
                    "customer_phone": row.customer_phone,
                    "product_name": row.product_name,
                    "product_sku": row.product_sku,
                    "quantity": row.quantity,
                    "refund_amount": float(row.refund_amount),
                    "currency": row.currency,
                    "refund_type": refund_type,
                    "refund_type_label": TYPE_LABELS.get(refund_type, refund_type),
                    "status": status,
                    "status_label": STATUS_LABELS.get(status, status),
                    "reason": row.reason or "",
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })

            total = len(refunds)
            logger.info(
                f"RefundQuery executed | refund_number={refund_number} "
                f"order_number={order_number} phone={phone} | results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "refunds": refunds,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"RefundQuery failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
