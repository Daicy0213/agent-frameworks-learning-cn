"""无模型 MCP 验收：发现、成功、业务失败、关闭连接。"""

import asyncio
from pathlib import Path
import sys

from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool import StdioConnectionParams
from mcp import StdioServerParameters


async def verify() -> dict:
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(Path(__file__).with_name("local_server.py"))],
            ),
            timeout=10,
        )
    )
    try:
        tools = await toolset.get_tools()
        assert [tool.name for tool in tools] == ["order_status"]
        success = await tools[0].run_async(args={"order_id": "A100"}, tool_context=None)
        missing = await tools[0].run_async(args={"order_id": "missing"}, tool_context=None)
        # MCP content 与 structuredContent 取决于服务端版本；观察原始结果再断言。
        import json

        def payload(result):
            structured = result.get("structuredContent")
            if structured is not None:
                return structured
            return json.loads(result["content"][0]["text"])

        ok, absent = payload(success), payload(missing)
        assert ok["ok"] is True and ok["status"] == "已发货"
        assert absent["ok"] is False and absent["error"] == "ORDER_NOT_FOUND"
        result = {"tools": [tool.name for tool in tools], "success": ok, "missing": absent}
    finally:
        # 必须在创建连接的同一异步作用域关闭，避免遗留 stdio 子进程。
        await toolset.close()
    result["closed"] = True
    return result


if __name__ == "__main__":
    print(asyncio.run(verify()))
