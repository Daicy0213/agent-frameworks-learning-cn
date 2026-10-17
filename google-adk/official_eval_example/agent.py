"""真实 ADK Runner + 确定性模型替身；可显式切换到 DeepSeek。"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator

from google.adk.agents import Agent
from google.adk.models import LlmRequest, LlmResponse
from google.adk.models.base_llm import BaseLlm
from google.genai import types


def query_order(order_id: str) -> dict:
    """查询演示订单；不存在时返回结构化错误。"""
    if order_id == "A1001":
        return {"ok": True, "order_id": order_id, "status": "已签收"}
    return {"ok": False, "order_id": order_id, "error": "ORDER_NOT_FOUND"}


def answer_for(order_id: str | None) -> str:
    if order_id is None:
        return "请提供完整订单号。"
    if order_id == "A1001":
        return "订单 A1001 已签收。"
    return f"未找到订单 {order_id}，请核对订单号。"


class OrderModel(BaseLlm):
    """只替换模型决策；工具执行、事件与官方指标仍由 ADK 运行。"""

    model: str = "offline-order-model"

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        contents = llm_request.contents or []
        latest = contents[-1] if contents else None
        responses = [
            part.function_response
            for part in (latest.parts or []) if part.function_response
        ] if latest else []
        if responses:
            result = responses[-1].response
            text = answer_for(result["order_id"])
            part = types.Part(text=text)
        else:
            query = "".join(
                part.text or ""
                for content in reversed(contents)
                if content.role == "user"
                for part in content.parts or []
            )
            match = re.search(r"\b[A-Z]\d{4}\b", query)
            order_id = match.group() if match else None
            if order_id and os.getenv("ADK_EVAL_INJECT_BUG") != "skip_tool":
                part = types.Part(function_call=types.FunctionCall(
                    name="query_order", args={"order_id": order_id}
                ))
            else:
                # 故意制造“回答正确、却没有查订单”的回归。
                part = types.Part(text=answer_for(order_id))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


backend = os.getenv("ADK_EVAL_BACKEND", "offline")
if backend == "offline":
    model = OrderModel()
elif backend == "deepseek":
    from google.adk.models.lite_llm import LiteLlm

    if not os.getenv("DEEPSEEK_API_KEY"):
        raise ValueError("在线评估需要 DEEPSEEK_API_KEY")
    model = LiteLlm(model="deepseek/deepseek-chat", temperature=0)
else:
    raise ValueError("ADK_EVAL_BACKEND 仅支持 offline 或 deepseek")

root_agent = Agent(
    name="order_eval_agent",
    model=model,
    instruction=(
        "查询订单必须调用 query_order，参数原样使用订单号。"
        "缺订单号时不调用工具，只回答：请提供完整订单号。"
        "查询成功只回答：订单 A1001 已签收。"
        "订单不存在只回答：未找到订单 Z9999，请核对订单号。"
    ),
    tools=[query_order],
)
