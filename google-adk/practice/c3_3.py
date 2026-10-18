"""第 3 章练习 3：结构化输出的工程边界（DeepSeek 版）。

两阶段方案：
1. 阶段一：准备并整理输入事实（本例用确定性数据，避免多一次模型调用）；
2. 阶段二：只做结构化输出，用 json_object + Pydantic + 业务检查三层保证。

验收：
- 输出可被 Pydantic 校验；
- 负责人、任务、截止日期、优先级、风险提示齐全；
- 业务规则另外检查，不只依赖 schema。

运行：uv run --env-file .env python c3_3.py
"""

import json
from datetime import date

from pydantic import BaseModel, Field, ValidationError

from _common import deepseek, run
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from _common import APP, USER


class ActionItem(BaseModel):
    owner: str = Field(min_length=1, description="负责人")
    task: str = Field(min_length=1, description="任务描述")
    due_date: str = Field(description="截止日期，格式 YYYY-MM-DD")
    priority: str = Field(description="优先级：low / normal / high")
    risk: str = Field(description="风险提示，没有风险时写 none")


class ActionItems(BaseModel):
    items: list[ActionItem]


MEETING_NOTES = """
周四产品会（2026-10-15）：
- 小王负责在 2026-10-19 前把登录页改版方案写完；
- 小李在 2026-10-21 前给出灰度发布清单，风险是测试环境不稳定；
- 老张在 2026-10-23 前确认法务文案，优先级高。
"""

INSTRUCTION = """你是会议纪要整理员。把会议记录整理成行动项。

只输出 JSON，格式为：
{"items": [{"owner": "...", "task": "...", "due_date": "YYYY-MM-DD", "priority": "low|normal|high", "risk": "..."}]}

要求：
- due_date 必须是 YYYY-MM-DD；
- risk 没有内容时写 none；
- 不要输出 JSON 以外的任何文字。
"""

# 阶段一：确定性输入。真实项目里也可以换成一次模型抽取。
facts = {"meeting_date": "2026-10-15", "notes": MEETING_NOTES}

agent = Agent(
    name="action_item_extractor",
    model=deepseek(max_tokens=512),
    instruction=INSTRUCTION,
    description="把会议记录整理成结构化行动项",
)


def business_check(result: ActionItems) -> list[str]:
    """schema 管不到的业务规则。"""
    problems = []
    allowed = {"low", "normal", "high"}
    for item in result.items:
        try:
            date.fromisoformat(item.due_date)
        except ValueError:
            problems.append(f"{item.owner}: 日期格式错误 {item.due_date}")
        if item.priority not in allowed:
            problems.append(f"{item.owner}: 非法优先级 {item.priority}")
    if not result.items:
        problems.append("没有抽取到任何行动项")
    return problems


async def main():
    service = InMemorySessionService()
    session_id = "c3_3"
    await service.create_session(app_name=APP, user_id=USER, session_id=session_id)
    runner = Runner(agent=agent, app_name=APP, session_service=service)
    message = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(facts, ensure_ascii=False))],
    )

    text = ""
    async for event in runner.run_async(
        user_id=USER, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text += event.content.parts[0].text or ""

    # 第一层：JSON 格式（容忍模型偶尔包一层代码块）
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    raw = json.loads(text)

    # 第二层：Pydantic 字段校验
    try:
        result = ActionItems.model_validate(raw)
    except ValidationError as exc:
        raise AssertionError(f"字段校验失败：{exc}") from exc

    # 第三层：业务检查
    problems = business_check(result)
    assert not problems, f"业务检查失败：{problems}"

    owners = {item.owner for item in result.items}
    assert {"小王", "小李", "老张"} <= owners, f"漏掉了行动项：{owners}"
    print(f"✅ 抽取到 {len(result.items)} 条行动项，三层校验全部通过")


if __name__ == "__main__":
    run(main)
