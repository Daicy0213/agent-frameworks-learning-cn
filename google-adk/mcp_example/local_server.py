"""最小本地 MCP Server：只暴露一个订单查询工具，不联网。

启动方式（通常由 MCPToolset 作为子进程拉起，不需要手动运行）：
    python mcp_example/local_server.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-tools")

_ORDERS = {
    "A100": {"status": "已发货", "carrier": "顺丰"},
    "B200": {"status": "已签收", "carrier": "京东物流"},
}


@mcp.tool()
def order_status(order_id: str) -> dict:
    """查询订单状态。

    Args:
        order_id: 订单号，例如 A100。
    """
    order = _ORDERS.get(order_id)
    if order is None:
        return {"ok": False, "error": "ORDER_NOT_FOUND", "order_id": order_id}
    return {"ok": True, "order_id": order_id, **order}


if __name__ == "__main__":
    mcp.run()
