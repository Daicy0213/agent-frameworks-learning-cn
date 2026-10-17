"""通过 ADK Runner 调用工具；离线模型只验证协议和业务边界。"""

from __future__ import annotations

import json
import os

from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from .store import Principal, RefundStore


class ScenarioModel(BaseLlm):
    """按固定 JSON 场景发出工具调用，不具备自然语言理解能力。"""

    model: str = "offline-capstone"

    async def generate_content_async(self, llm_request: LlmRequest, stream=False):
        contents = llm_request.contents
        current = next(i for i in range(len(contents) - 1, -1, -1)
                       if contents[i].role == "user"
                       and any(p.text for p in contents[i].parts or []))
        scenario = json.loads("".join(p.text or "" for p in contents[current].parts))
        responses = [p.function_response for c in contents[current + 1:]
                     for p in c.parts or [] if p.function_response]
        if not responses:
            part = types.Part(function_call=types.FunctionCall(
                name="query_order", args={"order_id": scenario["order_id"]}))
        elif responses[-1].name == "query_order" and responses[-1].response.get("ok"):
            part = types.Part(function_call=types.FunctionCall(
                name="create_refund", args=scenario))
        else:
            part = types.Part(text=json.dumps(responses[-1].response, ensure_ascii=False))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def build_agent(store: RefundStore, principal: Principal, backend="offline", *,
                with_knowledge=False) -> Agent:
    if with_knowledge:
        from .knowledge import build_knowledge_agent
        return build_knowledge_agent(store, principal, backend)
    # principal 由服务器认证后绑定，模型没有可自行修改的 role/tenant 参数。
    def query_order(order_id: str) -> dict:
        """查询当前登录用户可以访问的订单。"""
        return store.query_order(principal, order_id)

    def create_refund(order_id: str, amount_cents: int, approval_id: str,
                      request_key: str) -> dict:
        """按已有人工审批退款。金额单位为分，重试须保持参数不变。"""
        return store.refund(principal, order_id, amount_cents, approval_id, request_key)

    if backend == "offline":
        model = ScenarioModel()
    else:
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise RuntimeError("在线实验需要 DEEPSEEK_API_KEY")
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        from google.adk.models.lite_llm import LiteLlm
        model = LiteLlm(model="deepseek/deepseek-chat", temperature=0, max_tokens=400, timeout=40, num_retries=0)
    return Agent(
        name="after_sales", model=model,
        instruction=("处理售后退款。先 query_order，再使用用户提交的原始参数调用 "
                     "create_refund。不得生成审批号或改动金额。工具拒绝即停止。"
                     "最终只返回工具结果 JSON，不自行宣布退款成功。"),
        tools=[query_order, create_refund],
    )
