"""
用于测试DeepSeek是否支持output_schema这个变量的传入
"""

import os

from google.adk.models import LiteLlm

assert os.environ.get("DEEPSEEK_API_KEY"), "请先设置 DEEPSEEK_API_KEY"

from pydantic import BaseModel, Field
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP, USER = "adk_ch02", "student"


async def run_once(agent, query, session_id="demo", verbose=False):
    """通用一次性问答：新建 Runner+Session，返回最终文本（可选打印事件流）。"""
    ss = InMemorySessionService()
    await ss.create_session(app_name=APP, user_id=USER, session_id=session_id)
    runner = Runner(agent=agent, app_name=APP, session_service=ss)
    # 输入 msg
    msg = types.Content(role="user", parts=[types.Part(text=query)])
    final = ""
    async for ev in runner.run_async(user_id=USER, session_id=session_id, new_message=msg):
        # verbose(啰嗦) 将打印所有event
        if verbose and ev.content and ev.content.parts:
            for p in ev.content.parts:
                if p.text: print(f"  [event:{ev.author}] {p.text[:80]}")
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = ev.content.parts[0].text
    # 顺便返回 session 便于查看状态
    session = await ss.get_session(app_name=APP, user_id=USER, session_id=session_id)
    return final, session


print("✅ 运行环境就绪")


class BookReview(BaseModel):
    title: str = Field(description="书名")
    rating: int = Field(description="评分，1-5 的整数")
    keywords: list[str] = Field(description="3 个关键词")
    one_line: str = Field(description="一句话点评")


reviewer = Agent(
    name="reviewer",
    model=LiteLlm(model="deepseek/deepseek-chat"),
    instruction="你是书评编辑，按 schema 输出书评。",
    output_schema=BookReview,
    output_key="review",  # 可选：不写就只从事件里拿 JSON 字符串
)
ss = InMemorySessionService()


def main():
    from dotenv import load_dotenv
    import asyncio
    load_dotenv()
    text, _ = asyncio.run(run_once(reviewer, "赏析一下「大漠孤烟直，长河落日圆」。"))
    print(text)


if __name__ == '__main__':
    import sys

    sys.exit(main())
