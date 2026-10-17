"""第 3 章练习 2：动态 instruction 与状态接力。

验收：
1. 从 Session State 读取用户等级、语言、产品类型；
2. 动态改变语气与处理规则；
3. 用 output_key 保存标准化分诊结论；
4. 覆盖缺少状态、普通用户、VIP 三种情况；
5. 状态中保留下一 Agent 可用的结果。

运行：uv run --env-file .env python c3_2.py
"""

from uuid import uuid4

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from _common import APP, USER, deepseek, run

INSTRUCTION = """你是客服分诊员。根据用户信息判断问题类型与优先级。

用户等级：{user_level?}
使用语言：{language?}
产品线：{product?}

规则：
- VIP：先致歉，优先级至少为 high；
- 普通用户：正常处理，优先级按问题严重程度判断；
- 某个字段为空时，不要猜测，把对应值写成 unknown。

只输出 JSON，字段固定为：
{"user_level": "...", "issue_type": "...", "priority": "low|normal|high", "reply_language": "...", "next_action": "..."}
"""


def build_agent() -> Agent:
    return Agent(
        name="triage_agent",
        model=deepseek(max_tokens=256),
        instruction=INSTRUCTION,
        description="读取用户上下文并输出标准化分诊结论",
        output_key="triage",
    )


async def run_case(agent, label, initial_state):
    service = InMemorySessionService()
    session_id = uuid4().hex
    await service.create_session(
        app_name=APP, user_id=USER, session_id=session_id, state=initial_state or {}
    )
    runner = Runner(agent=agent, app_name=APP, session_service=service)
    message = types.Content(
        role="user",
        parts=[types.Part(text="我的账号登录不上，比较着急。")],
    )
    async for _ in runner.run_async(
        user_id=USER, session_id=session_id, new_message=message
    ):
        pass

    session = await service.get_session(
        app_name=APP, user_id=USER, session_id=session_id
    )
    assert session is not None
    result = session.state.get("triage")
    assert isinstance(result, str), f"{label}: output_key 没有写入状态"
    assert "priority" in result and "next_action" in result
    print(f"[{label}] {result[:120]}")
    return result


async def main():
    agent = build_agent()

    await run_case(
        agent,
        "普通用户",
        {"user_level": "normal", "language": "中文", "product": "账号服务"},
    )
    vip = await run_case(
        agent,
        "VIP",
        {"user_level": "VIP", "language": "中文", "product": "账号服务"},
    )
    missing = await run_case(agent, "缺少状态", {})

    assert "high" in vip.lower(), "VIP 的优先级应至少为 high"
    assert "unknown" in missing.lower(), "缺状态时应写 unknown，而不是猜测"
    print("✅ 三种情况都写入了 output_key，且 VIP 规则生效")


if __name__ == "__main__":
    run(main)
