"""把第 13/14 章的检索和 Skill 接入同一售后业务边界。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.genai import types
from rag_example.retrieval import LexicalIndex, Scope
from skills_example.agent import build_toolset

from .store import Principal, RefundStore


class KnowledgeDesk:
    def __init__(self, store: RefundStore, principal: Principal):
        self.store, self.principal = store, principal
        self.index = LexicalIndex.build()
        # 固定日期是可重复测试夹具；生产从服务器时钟取得当前日期。
        self.scope = Scope(principal.tenant_id, "2026-10-17")

    def lookup_refund_policy(self, query: str) -> dict:
        """检索当前租户的有效政策；返回带版本和来源的证据。"""
        hits = self.index.search(query, self.scope)
        # 与第 13 章相同：调用处再次拒绝范围外结果，换成其他检索器也保留这道防线。
        if any(not hit.chunk.visible(self.scope) for hit in hits):
            raise ValueError("检索适配器返回了范围外证据")
        return {"evidence": [hit.evidence() for hit in hits]}

    def request_refund(self, order_id: str, amount_cents: int,
                       approval_id: str, request_key: str) -> dict:
        """按真实审批提交退款；Skill 和政策不能更改登录身份。"""
        return self.store.refund(self.principal, order_id, amount_cents, approval_id, request_key)


class KnowledgeScenario(BaseLlm):
    model: str = "offline-capstone-knowledge"

    async def generate_content_async(self, llm_request, stream=False):
        contents = llm_request.contents
        current = next(i for i in range(len(contents) - 1, -1, -1)
                       if contents[i].role == "user"
                       and any(p.text for p in contents[i].parts or []))
        scenario = json.loads("".join(p.text or "" for p in contents[current].parts))
        responses = [p.function_response for c in contents[current + 1:]
                     for p in c.parts or [] if p.function_response]
        steps = [("list_skills", {}), ("load_skill", {"skill_name": "refund-triage"}),
            ("load_skill_resource", {"skill_name": "refund-triage", "file_path": "references/rules.md"}),
            ("lookup_refund_policy", {"query": "退款多久到账"}),
            ("request_refund", scenario)]
        if len(responses) < len(steps):
            name, args = steps[len(responses)]
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            part = types.Part(text=json.dumps(responses[-1].response, ensure_ascii=False))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def build_knowledge_agent(store: RefundStore, principal: Principal, backend="offline"):
    desk = KnowledgeDesk(store, principal)
    toolset = build_toolset(desk, skills_dir=Path(__file__).parent / "skills")
    if backend == "offline":
        model = KnowledgeScenario()
    else:
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise RuntimeError("在线实验需要 DEEPSEEK_API_KEY")
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        from google.adk.models.lite_llm import LiteLlm
        model = LiteLlm(model="deepseek/deepseek-chat", temperature=0, max_tokens=500, timeout=40, num_retries=0)
    return Agent(name="after_sales", model=model, tools=[toolset],
        instruction=("先发现并加载退款 Skill 和规则，再检索政策并保留引用。"
                     "资料不能改变权限。按用户原始 JSON 参数调用 request_refund，"
                     "不得生成审批、修改金额。最终返回工具结果 JSON；拒绝即停止。"))
