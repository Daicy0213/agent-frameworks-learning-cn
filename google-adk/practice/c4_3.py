"""第 4 章练习 3：AgentTool 与普通工具的职责划分。

验收：
1. 主 Agent 用普通函数工具取得结构化行情数据；
2. 把"解释数据并识别风险"交给一个 AgentTool；
3. 最终输出同时包含数据摘要、分析结论和风险声明；
4. 说明为什么取数适合确定性工具、分析适合 AgentTool；
5. 观察"调用-返回"语义：AgentTool 执行完，控制权回到主 Agent。

运行：uv run --env-file .env python c4_3.py
"""

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool
from google.genai import types

from _common import APP, USER, run

MODEL = lambda: LiteLlm(model="deepseek/deepseek-chat")


def get_market_data(symbol: str) -> dict:
    """查询一只股票的确定性行情数据。

    Args:
        symbol: 股票代码，例如 AAPL。
    """
    data = {
        "AAPL": {"price": 228.5, "change_pct": -3.2, "pe": 34.1, "volume": "52M"},
        "MSFT": {"price": 421.0, "change_pct": 1.1, "pe": 36.8, "volume": "21M"},
    }
    if symbol.upper() not in data:
        return {"ok": False, "error": "SYMBOL_NOT_FOUND", "symbol": symbol}
    return {"ok": True, "symbol": symbol.upper(), **data[symbol.upper()]}


# 只负责"解释与风险判断"，不接触原始数据源。
analyst = Agent(
    name="analyst",
    model=MODEL(),
    instruction=(
        "你是股票风险分析师。根据输入里的行情数据，用 3 句话给出："
        "① 趋势判断；② 一条主要风险；③ 一句风险声明。"
        "不要编造输入里没有的数字。"
    ),
    description="根据结构化行情数据做解释和风险识别",
)

coordinator = Agent(
    name="market_brief",
    model=MODEL(),
    instruction=(
        "你是市场简报助手，工作顺序固定："
        "1) 必须先调用 get_market_data 取得原始数据；"
        "2) 再调用 analyst，把上一步返回的完整数据作为输入；"
        "3) 最后输出三部分：原始数据摘要、分析结论、风险声明。"
        "不允许跳过任何一步，也不允许自己编造数据。"
    ),
    description="取数 + 分析的市场简报助手",
    tools=[get_market_data, AgentTool(agent=analyst)],
)


async def main():
    service = InMemorySessionService()
    session_id = "c4_3"
    await service.create_session(app_name=APP, user_id=USER, session_id=session_id)
    runner = Runner(agent=coordinator, app_name=APP, session_service=service)

    message = types.Content(
        role="user",
        parts=[types.Part(text="看一下 AAPL 的行情，并给出一份简要市场简报。")],
    )

    calls: list[str] = []
    final_text = ""
    async for event in runner.run_async(
        user_id=USER, session_id=session_id, new_message=message
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            if part.function_call:
                calls.append(part.function_call.name)
            elif part.text and event.is_final_response():
                final_text += part.text

    print("工具调用顺序：", calls)
    print("最终回复：", final_text[:300])

    # 1) 取数必须走确定性工具
    assert "get_market_data" in calls, "没有调用行情工具"
    # 2) 分析必须走 AgentTool
    assert "analyst" in calls, "没有把分析交给 analyst"
    # 3) 必须是"先取数、后分析"的调用-返回关系
    assert calls.index("get_market_data") < calls.index("analyst"), "调用顺序不对"
    # 4) AgentTool 返回后，主 Agent 仍然产出最终回复
    assert final_text.strip(), "主 Agent 没有在 AgentTool 返回后继续完成简报"

    print("✅ 取数走函数工具、分析走 AgentTool，且控制权返回主 Agent")


if __name__ == "__main__":
    run(main)
