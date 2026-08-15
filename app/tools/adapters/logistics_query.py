"""
LogisticsQueryTool: query logistics tracking and delivery status.

Searches the logistics_tracking table by tracking number or order number.
Returns structured tracking data including carrier, status, current location,
estimated delivery, and full tracking event timeline.

This tool provides detailed logistics information, complementing OrderQueryTool
which only returns basic tracking number and carrier.
"""

import logging
import re
from typing import Dict, Any, List

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Chinese status labels for display
STATUS_LABELS = {
    "pending": "待发货",
    "picked_up": "已揽收",
    "in_transit": "运输中",
    "out_for_delivery": "派送中",
    "delivered": "已签收",
    "exception": "异常",
}


class LogisticsQueryTool(BaseTool):
    """Query logistics tracking and delivery status.

    Searches by tracking number (exact match) or order number (exact match).
    Returns detailed tracking information including carrier, current status,
    location, estimated delivery, and a full event timeline.

    Parameters:
    - tracking_number: Express tracking number (e.g., "SF1234567890CN")
    - order_number: Order number to find associated tracking
    - query: Free-text query — will try to extract tracking/order number
    """

    @property
    def name(self) -> str:
        return "logistics_query"

    @property
    def description(self) -> str:
        return (
            "查询物流轨迹工具。根据快递单号或订单号查询物流状态、当前位置、"
            "预计送达时间和完整的物流轨迹（每个节点的时间和描述）。"
            "适用场景：顾客询问「快递到哪了」「什么时候能到」「物流轨迹」"
            "「包裹在什么位置」时调用。"
        )

    @property
    def tool_type(self) -> str:
        return "business"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tracking_number": {
                    "type": "string",
                    "description": "快递单号，如 'SF1234567890CN'",
                },
                "order_number": {
                    "type": "string",
                    "description": "订单号，用于查询该订单关联的物流信息",
                },
                "query": {
                    "type": "string",
                    "description": "自由文本查询，工具会尝试从中提取快递单号或订单号",
                },
            },
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "trackings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tracking_number": {"type": "string"},
                            "order_number": {"type": "string"},
                            "carrier": {"type": "string"},
                            "status": {"type": "string"},
                            "status_label": {"type": "string"},
                            "current_location": {"type": "string"},
                            "estimated_delivery": {"type": "string"},
                            "shipping_address": {"type": "string"},
                            "events": {"type": "array"},
                        },
                    },
                },
                "total": {"type": "integer"},
            },
        }

    async def execute(
        self,
        tracking_number: str = "",
        order_number: str = "",
        query: str = "",
        **kwargs,
    ) -> ToolResult:
        """Query logistics tracking by tracking number, order number, or free-text.

        Args:
            tracking_number: Exact tracking number to look up.
            order_number: Order number to find associated tracking.
            query: Free text — will try to extract tracking or order number.

        Returns:
            ToolResult with matching tracking records.
        """
        try:
            # If only query is provided, try to extract identifiers
            if not tracking_number and not order_number and query:
                # Extract tracking number pattern: letters + digits + CN
                tracking_match = re.search(
                    r"[A-Z]{2}\d{10,}CN", query.upper()
                )
                if tracking_match:
                    tracking_number = tracking_match.group()

                # Extract order number pattern: RK + digits
                order_match = re.search(r"RK\d{9,}", query.upper())
                if order_match:
                    order_number = order_match.group()

            if not tracking_number and not order_number:
                return ToolResult(
                    success=True,
                    data={
                        "trackings": [],
                        "total": 0,
                        "message": "未提供快递单号或订单号，无法查询物流信息。",
                    },
                )

            from app.database.session import async_session_factory
            from sqlalchemy import text
            import json

            async with async_session_factory() as session:
                if tracking_number:
                    sql = text("""
                        SELECT tracking_number, order_number, carrier, status,
                               current_location, estimated_delivery, shipping_address,
                               tracking_events, created_at, updated_at
                        FROM logistics_tracking
                        WHERE tracking_number = :tracking_number
                    """)
                    results = await session.execute(
                        sql, {"tracking_number": tracking_number}
                    )
                    rows = results.fetchall()
                else:
                    sql = text("""
                        SELECT tracking_number, order_number, carrier, status,
                               current_location, estimated_delivery, shipping_address,
                               tracking_events, created_at, updated_at
                        FROM logistics_tracking
                        WHERE order_number = :order_number
                        ORDER BY created_at DESC
                    """)
                    results = await session.execute(
                        sql, {"order_number": order_number}
                    )
                    rows = results.fetchall()

            # Build structured results
            trackings: List[Dict[str, Any]] = []
            for row in rows:
                status = row.status or "unknown"
                # Parse tracking events from JSONB
                events = row.tracking_events or []
                if isinstance(events, str):
                    try:
                        events = json.loads(events)
                    except Exception:
                        events = []

                estimated_delivery = (
                    row.estimated_delivery.isoformat()
                    if row.estimated_delivery
                    else None
                )

                trackings.append({
                    "tracking_number": row.tracking_number,
                    "order_number": row.order_number,
                    "carrier": row.carrier or "暂无",
                    "status": status,
                    "status_label": STATUS_LABELS.get(status, status),
                    "current_location": row.current_location or "暂无",
                    "estimated_delivery": estimated_delivery,
                    "shipping_address": row.shipping_address or "",
                    "events": events,
                })

            total = len(trackings)
            logger.info(
                f"LogisticsQuery executed | tracking_number={tracking_number} "
                f"order_number={order_number} | results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "trackings": trackings,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"LogisticsQuery failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
