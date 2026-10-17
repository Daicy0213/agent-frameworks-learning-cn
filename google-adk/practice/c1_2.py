"""
2. 观察而不是只看答案（基础）

为一次运行编写事件观察器，逐条打印事件作者、是否为最终响应以及事件携带的内容类型，
最后只汇总最终文本。

目标是能从输出中解释 `Runner`、`Event` 与 Agent 回复之间的关系，
而不是简单调用后打印结果。

运行：
    cd google-adk/practice
    uv run python c1_2.py
"""

import asyncio

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "event_observer"
USER_ID = "student_01"
SESSION_ID = "s1"

deepseek_model = LiteLlm(model="deepseek/deepseek-chat")

greeter = Agent(
    name="greeter",
    model=deepseek_model,
    instruction="你是简洁的助手，回答控制在两句话以内。",
    description="用于观察事件流的最小 Agent",
)

session_service = InMemorySessionService()
runner = Runner(session_service=session_service, agent=greeter, app_name=APP_NAME)


def part_kinds(content) -> list[str]:
    """看一条事件到底带了什么：文本？函数调用？函数返回？"""
    if content is None or not content.parts:
        return []
    kinds = []
    for part in content.parts:
        if part.text is not None:
            kinds.append("text")
        elif part.function_call is not None:
            kinds.append("function_call")
        elif part.function_response is not None:
            kinds.append("function_response")
        else:
            kinds.append(type(part).__name__)
    return kinds


def preview_of(event) -> str:
    if event.content and event.content.parts and event.content.parts[0].text:
        return event.content.parts[0].text.replace("\n", " ")[:34]
    return ""


async def observe(query: str, session_id: str = SESSION_ID):
    """跑一轮，把每个事件原样打印出来，最后只汇总最终文本。"""
    try:
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    except Exception:
        pass  # 会话已存在时复用

    message = types.Content(role="user", parts=[types.Part(text=query)])

    events = []
    print(f"用户 >>> {query}\n")
    print(f"{'#':<4}{'author':<14}{'final?':<9}{'内容类型':<20}文本预览")
    print("-" * 92)

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        events.append(event)
        kinds = part_kinds(event.content)
        print(
            f"{len(events):<4}{str(event.author):<14}"
            f"{str(event.is_final_response()):<9}{','.join(kinds) or '-':<20}{preview_of(event)}"
        )

    # 只汇总最终文本。这里用 is_final_response() 是刻意的 ——
    # 第 8 章会告诉你它在 Workflow 里不够用（子节点也会产生「最终事件」）。
    final_text = ""
    for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            final_text += event.content.parts[0].text or ""

    print(f"\nAgent >>> {final_text}")
    return final_text, events


async def main() -> None:
    final_text, events = await observe("用一句话说明什么是 AI Agent。")

    print("\n" + "=" * 92)
    print("从上面的输出里，应该能读出三件事")
    print("=" * 92)

    # ① 每个事件都有作者 —— 事件回答的是「谁产出了这一条」
    authors = [event.author for event in events]
    assert all(authors), f"每个事件都应该有 author：{authors}"
    print(f"① 事件作者：{authors}")
    print("   → Event 记录的是「谁产出了这一条」，而不是一个孤立的文本块。")

    # ② 只有一条事件是「最终响应」
    finals = [e for e in events if e.is_final_response()]
    assert len(finals) == 1, f"这一轮应该恰好一个最终响应，实际 {len(finals)} 个"
    print(f"② {len(events)} 个事件里，is_final_response() 为 True 的只有 {len(finals)} 个")
    print("   → 要回复用户，应该挑这一条，而不是「最后一条」或「每一条」。")

    # ③ 汇总出来的最终文本 == 最终事件里的文本
    assert final_text, "应该拿到非空的最终文本"
    finish_parts = finals[0].content.parts if finals[0].content else []
    finish_text = "".join(part.text or "" for part in finish_parts)
    assert final_text == finish_text, (final_text, finish_text)
    print("③ 汇总的最终文本与最终事件里的文本完全一致")
    print("   → Runner 负责「跑」，Event 负责「记录」，你的代码只负责「挑出要的那条」。")

    print("\n✅ 练习 2 通过：能从事件流解释 Runner / Event / Agent 回复之间的关系")


if __name__ == "__main__":
    asyncio.run(main())
