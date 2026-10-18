"""第 5 章练习 4：混合式客服系统。

结构：
  顶层 dispatcher（LLM 委派）→ 退款 / 物流 / 技术支持
  退款子团队（确定性流水线）→ 资格检查 → 审批检查 → 执行

关键约束：
- 退款动作不能只凭一次模型判断执行；
- 审批缺失时，工具本体必须拒绝，而不是靠提示词"请求模型不要调用"；
- 同一订单重复提交退款，只产生一条业务记录。

运行：uv run --env-file .env python c5_4.py
"""

from __future__ import annotations

from google.adk.agents import Agent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types

from _common import APP, USER, run

MODEL = lambda: LiteLlm(model="deepseek/deepseek-chat")

ORDERS = {
    "A100": {"status": "已签收", "amount": 299, "reason_ok": True},
    "B200": {"status": "运输中", "amount": 199, "reason_ok": False},
}

# 业务账本：真实项目里应放数据库，并以唯一键约束保证幂等。
REFUNDS: dict[str, dict] = {}
CALLS: list[str] = []


def check_eligibility(order_id: str, reason: str, tool_context: ToolContext) -> dict:
    """检查订单是否满足退款条件。

    Args:
        order_id: 订单号。
        reason: 用户给出的退款原因。
    """
    CALLS.append("check_eligibility")
    order = ORDERS.get(order_id)
    ok = bool(order and order["status"] == "已签收" and order["reason_ok"])
    tool_context.state["eligibility_ok"] = ok
    return {"ok": ok, "order_id": order_id, "reason": reason}


def check_approval(approval_code: str, tool_context: ToolContext) -> dict:
    """检查是否有人工审批码。演示环境只接受 APPROVED。

    Args:
        approval_code: 审批码；没有审批时传空字符串。
    """
    CALLS.append("check_approval")
    ok = approval_code == "APPROVED" and bool(tool_context.state.get("eligibility_ok"))
    tool_context.state["approval_ok"] = ok
    return {"ok": ok, "approval_code": approval_code}


def create_refund(order_id: str, amount: int, tool_context: ToolContext) -> dict:
    """执行退款。工具自己复核资格与审批，不信任模型文本。

    Args:
        order_id: 订单号。
        amount: 退款金额。
    """
    CALLS.append("create_refund")
    if not tool_context.state.get("eligibility_ok"):
        return {"ok": False, "error": "NOT_ELIGIBLE"}
    if not tool_context.state.get("approval_ok"):
        return {"ok": False, "error": "APPROVAL_REQUIRED"}
    if order_id in REFUNDS:
        return {"ok": True, "duplicate": True, "refund": REFUNDS[order_id]}

    REFUNDS[order_id] = {"order_id": order_id, "amount": amount}
    return {"ok": True, "duplicate": False, "refund": REFUNDS[order_id]}


eligibility_agent = Agent(
    name="eligibility",
    model=MODEL(),
    instruction="必须调用 check_eligibility 检查订单 A100 的退款资格，不要自己判断。",
    description="检查退款资格",
    tools=[check_eligibility],
)

approval_agent = Agent(
    name="approval",
    model=MODEL(),
    instruction="必须调用 check_approval 检查审批码。没有审批码就传空字符串。",
    description="检查人工审批",
    tools=[check_approval],
)

executor_agent = Agent(
    name="executor",
    model=MODEL(),
    instruction=(
        "必须调用 create_refund 尝试执行退款。"
        "工具会自行复核资格和审批；工具返回失败时，如实转述错误码，不要绕过。"
    ),
    description="执行退款",
    tools=[create_refund],
)

refund_team = SequentialAgent(
    name="refund_team",
    sub_agents=[eligibility_agent, approval_agent, executor_agent],
    description="处理退款申请：资格检查、审批检查、执行",
)

logistics_agent = Agent(
    name="logistics",
    model=MODEL(),
    instruction="回答物流问题：查不到单号时请用户提供订单号。",
    description="处理物流、配送、签收问题",
)

tech_agent = Agent(
    name="tech_support",
    model=MODEL(),
    instruction="回答账号、登录、App 使用问题。",
    description="处理技术支持和账号问题",
)

dispatcher = Agent(
    name="service_desk",
    model=MODEL(),
    instruction=(
        "你是客服前台，只做分流，不直接回答业务问题。"
        "退款、退货、退款进度 → refund_team；"
        "物流、配送、签收 → logistics；"
        "账号、登录、App → tech_support。"
    ),
    description="客服前台",
    sub_agents=[refund_team, logistics_agent, tech_agent],
)


async def run_agent(agent, query: str, session_id: str, state: dict | None = None):
    service = InMemorySessionService()
    await service.create_session(
        app_name=APP, user_id=USER, session_id=session_id, state=state or {}
    )
    runner = Runner(agent=agent, app_name=APP, session_service=service)
    message = types.Content(role="user", parts=[types.Part(text=query)])
    calls: list[str] = []
    transfers: list[dict] = []
    final_text = ""
    async for event in runner.run_async(
        user_id=USER, session_id=session_id, new_message=message
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            if part.function_call:
                calls.append(part.function_call.name)
                if part.function_call.name == "transfer_to_agent":
                    transfers.append(dict(part.function_call.args))
            elif part.text and event.is_final_response():
                final_text += part.text
    return calls, transfers, final_text


async def main():
    # ---------- 路径 1：无审批，工具必须拒绝 ----------
    REFUNDS.clear(); CALLS.clear()
    await run_agent(
        refund_team,
        "订单 A100 破损了，我要退款 299 元。没有审批码。",
        "refund_no_approval",
        state={"approval_code": ""},
    )
    assert CALLS == ["check_eligibility", "check_approval", "create_refund"], CALLS
    assert REFUNDS == {}, "没有审批时不应产生退款记录"
    print("✅ 无审批路径：流程走完，但工具拒绝执行，账本为空")

    # ---------- 路径 2：有审批，执行一次 ----------
    REFUNDS.clear(); CALLS.clear()
    await run_agent(
        refund_team,
        "订单 A100 破损了，我要退款 299 元。审批码 APPROVED。",
        "refund_approved",
        state={"approval_code": "APPROVED"},
    )
    assert CALLS == ["check_eligibility", "check_approval", "create_refund"], CALLS
    assert len(REFUNDS) == 1, REFUNDS
    assert REFUNDS["A100"]["amount"] == 299
    print("✅ 有审批路径：资格、审批、执行依次通过，只产生一条记录")

    # ---------- 路径 3：重复提交，幂等 ----------
    await run_agent(
        refund_team,
        "再提交一次订单 A100 的退款，审批码 APPROVED。",
        "refund_duplicate",
        state={"approval_code": "APPROVED"},
    )
    assert len(REFUNDS) == 1, "重复提交不应产生第二条记录"
    print("✅ 重复提交：业务主键去重，账本仍只有一条")

    # ---------- 路径 4：顶层路由 ----------
    calls, transfers, _ = await run_agent(
        dispatcher,
        "我的订单 A100 破损了，想申请退款。",
        "route_refund",
        state={"approval_code": "APPROVED"},
    )
    assert transfers, "顶层没有发生 transfer_to_agent"
    target = transfers[0].get("agent_name", "")
    assert target == "refund_team", f"路由到了 {target}，期望 refund_team"
    print(f"✅ 顶层路由：transfer_to_agent → {target}")


if __name__ == "__main__":
    run(main)
