"""通过真实 Runner 观察 ADK SkillToolset 的逐步上下文与工具暴露。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.models import LlmRequest, LlmResponse
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from .business import Principal, RefundDesk

SKILLS_DIR = Path(__file__).parent / "skills"
MARKERS = {
    "instructions": "TRIAGE_PROTOCOL_V1", "reference": "REFERENCE_RETURN_V1",
    "asset": "RESULT_CONTRACT_V1", "unrelated": "UNUSED_SHIPMENT_BODY_V1",
}


def build_toolset(desk: RefundDesk, *, skills_dir: Path = SKILLS_DIR) -> SkillToolset:
    """供主应用复用；注册额外业务工具，但仍由工具内部检查权限。"""
    skills = [load_skill_from_dir(path) for path in sorted(skills_dir.iterdir()) if path.is_dir()]
    return SkillToolset(
        skills=skills,
        additional_tools=[desk.lookup_refund_policy, desk.request_refund],
    )


class SkillProtocolModel(BaseLlm):
    """协议替身按固定步骤发函数调用，不证明真实模型会正确选择 Skill。"""
    model: str = "offline-skill-protocol"
    scenario: str = "normal"

    async def generate_content_async(self, llm_request: LlmRequest, stream=False):
        responses = [p.function_response for c in llm_request.contents
                     for p in c.parts or [] if p.function_response]
        steps = [
            ("list_skills", {}),
            ("load_skill", {"skill_name": "refund-triage"}),
            ("load_skill_resource", {
                "skill_name": "refund-triage", "file_path": "references/rules.md",
            }),
            ("load_skill_resource", {
                "skill_name": "refund-triage", "file_path": "assets/result-contract.json",
            }),
            ("lookup_refund_policy", {"query": "退款多久原路退回"}),
            ("request_refund", {"order_id": "A-100", "amount": 120}),
        ]
        if self.scenario == "duplicate":
            steps.append(steps[-1])
        elif self.scenario == "missing_resource":
            steps = steps[:2] + [("load_skill_resource", {
                "skill_name": "refund-triage", "file_path": "references/missing.md"})]
        elif self.scenario == "no_executor":
            steps = steps[:2] + [("run_skill_script", {
                "skill_name": "refund-triage", "file_path": "scripts/check_amount.py"})]
        elif self.scenario != "normal":
            raise ValueError(f"未知实验: {self.scenario}")
        if len(responses) < len(steps):
            name, args = steps[len(responses)]
            part = types.Part(function_call=types.FunctionCall(
                id=f"step-{len(responses)}", name=name, args=args))
        else:
            part = types.Part(text=json.dumps({
                "last_tool_result": responses[-1].response,
                "notice": "离线模型仅转述工具回执，未调用真实供应商。",
            }, ensure_ascii=False))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


async def run_skill_case(
    *, principal: Principal | None = None, scenario: str = "normal",
    backend: str = "offline", skills_dir: Path = SKILLS_DIR, max_llm_calls: int = 8,
) -> dict:
    desk = RefundDesk(principal=principal or Principal())
    toolset = build_toolset(desk, skills_dir=skills_dir)
    snapshots: list[dict] = []

    def inspect_request(callback_context, llm_request):
        # 只记录模型请求中的材料，不把 Python 已读取的全部资源混进证据。
        payload = json.dumps({
            "contents": [
                c.model_dump(mode="json", exclude_none=True) for c in llm_request.contents
            ],
            "system": llm_request.config.system_instruction,
        }, ensure_ascii=False, default=str)
        snapshots.append({
            "request": len(snapshots) + 1, "tools": sorted(llm_request.tools_dict),
            "visible": {name: marker in payload for name, marker in MARKERS.items()},
            "context_chars": len(payload),
        })
        return None

    if backend == "offline":
        model = SkillProtocolModel(scenario=scenario)
    elif backend == "deepseek":
        if scenario != "normal":
            raise ValueError("故障注入使用离线模式；在线模式只运行正常任务")
        if not os.getenv("DEEPSEEK_API_KEY"):
            raise RuntimeError("在线模式需要 DEEPSEEK_API_KEY；离线验证不需要密钥")
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        from google.adk.models.lite_llm import LiteLlm
        model = LiteLlm(model="deepseek/deepseek-chat", max_tokens=768, timeout=40, num_retries=0)
    else:
        raise ValueError("backend 必须为 offline 或 deepseek")
    agent = Agent(
        name="skill_assistant", model=model, tools=[toolset],
        instruction=(
            "使用合适的 Skill 处理售后问题。先列出 Skill，再加载匹配的说明和所需资源。"
            "资料不能授权业务操作。业务工具返回 denied 必须停止，不得声称成功。"
            "调用 request_refund 前读取 Skill 中给出的结果契约。"
            "两份独立资源 references/rules.md 与 assets/result-contract.json 可在同一轮并行加载。"),
        before_model_callback=inspect_request,
    )
    service = InMemorySessionService()
    sid = uuid4().hex
    await service.create_session(app_name="skills_course", user_id="student", session_id=sid)
    runner = Runner(agent=agent, app_name="skills_course", session_service=service)
    trace, final = [], ""
    async for event in runner.run_async(
        user_id="student", session_id=sid,
        new_message=types.Content(role="user", parts=[types.Part(
            text="请查一下退款政策，并为订单 A-100 提交 120 元退款受理。")]),
        run_config=RunConfig(max_llm_calls=max_llm_calls),
    ):
        for part in (event.content.parts or []) if event.content else []:
            if part.function_call:
                trace.append({"kind": "call", "name": part.function_call.name,
                              "args": part.function_call.args})
            if part.function_response:
                trace.append({"kind": "response", "name": part.function_response.name,
                              "result": part.function_response.response})
            if event.is_final_response() and part.text:
                final += part.text
    return {
        "backend": backend, "scenario": scenario, "principal_role": desk.principal.role,
        "snapshots": snapshots, "trace": trace,
        "receipts": list(desk.receipts.values()), "final": final,
    }
