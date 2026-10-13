"""
3. 验证会话隔离（进阶）

创建两个用户、至少三个 `session_id`，让它们分别记住不同的颜色或项目代号，再交叉提问。
写出自动化断言，证明：
  - 同一个 Session 能延续上下文；
  - 不同 Session 之间不会串话。

最后补充说明 `user_id` 与 `session_id` 各自承担什么职责（见文件末尾注释）。

运行：
    cd google-adk/practice
    uv run python c1_3.py
"""

import asyncio

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "session_isolation"
ALICE = "alice"
BOB = "bob"

deepseek_model = LiteLlm(model="deepseek/deepseek-chat")

assistant = Agent(
    name="memo_assistant",
    model=deepseek_model,
    instruction=(
        "你是一个短时代号记录助手。用户告诉你一个代号时，你只需回复「已记录」。"
        "用户询问代号时，只回答代号本身，不要解释、不要联想、不要编造。"
        "如果用户在本轮对话里没有告诉过你任何代号，就回答「没有记录」。"
    ),
    description="只在当前会话内记住一个代号",
)

session_service = InMemorySessionService()
runner = Runner(session_service=session_service, agent=assistant, app_name=APP_NAME)


async def say(user_id: str, session_id: str, text: str) -> str:
    """在指定 (user_id, session_id) 里说一句，返回 Agent 的最终回复文本。"""
    try:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
    except Exception:
        pass  # 已存在就复用，这正是「同一 Session 延续上下文」的前提

    message = types.Content(role="user", parts=[types.Part(text=text)])
    final_text = ""
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text += event.content.parts[0].text or ""
    return final_text.strip()


async def main() -> None:
    # 三个会话：alice 两个，bob 一个。代号刻意做得互不相似，避免误判。
    await say(ALICE, "alice_work", "记住：我负责的项目代号是 ZEBRA-7。")
    await say(ALICE, "alice_personal", "记住：我个人的代号是 FALCON-3。")
    await say(BOB, "bob_work", "记住：我负责的项目代号是 OTTER-9。")

    print("三个会话已分别写下代号，开始交叉提问：\n")

    # --- 验收 ①：同一个 Session 能延续上下文 ---
    a1 = await say(ALICE, "alice_work", "我负责的项目代号是什么？")
    a2 = await say(ALICE, "alice_personal", "我个人的代号是什么？")
    b1 = await say(BOB, "bob_work", "我负责的项目代号是什么？")
    print(f"alice/alice_work     -> {a1}")
    print(f"alice/alice_personal -> {a2}")
    print(f"bob/bob_work         -> {b1}")

    assert "ZEBRA-7" in a1.upper(), f"alice_work 应该记住 ZEBRA-7，实际：{a1}"
    assert "FALCON-3" in a2.upper(), f"alice_personal 应该记住 FALCON-3，实际：{a2}"
    assert "OTTER-9" in b1.upper(), f"bob_work 应该记住 OTTER-9，实际：{b1}"
    print("\n① 同一 Session 能延续上下文 ✅")

    # --- 验收 ②：不同 Session 之间不串话 ---
    # 关键点：alice 的两个会话属于同一个 user_id，内容依然必须互不可见。
    assert "FALCON-3" not in a1.upper(), f"alice_work 不该看到另一个会话的代号：{a1}"
    assert "ZEBRA-7" not in a2.upper(), f"alice_personal 不该看到另一个会话的代号：{a2}"
    assert "ZEBRA-7" not in b1.upper(), f"bob 不该看到 alice 的代号：{b1}"
    assert "OTTER-9" not in a1.upper(), f"alice 不该看到 bob 的代号：{a1}"
    print("② 不同 Session 之间不串话（包括同一个 user_id 下的两个会话）✅")

    # --- 验收 ③：全新 Session 是「空白」的 ---
    fresh = await say(ALICE, "alice_brand_new", "我负责的项目代号是什么？")
    print(f"alice/alice_brand_new -> {fresh}")
    assert "ZEBRA-7" not in fresh.upper(), f"全新会话不该继承任何代号：{fresh}"
    print("③ 全新 Session 没有任何历史上下文 ✅")

    print("\n✅ 练习 3 通过：会话隔离成立，且隔离边界是 session_id 而不是 user_id")


if __name__ == "__main__":
    asyncio.run(main())

# ---------------------------------------------------------------------------
# 参考答案（先自己写，再看这里）
#
# **user_id 和 session_id 分别管什么？**
#
#   user_id —— 「这是谁」。
#     它标识一个终端用户，把属于同一个人的多个会话归到一起。
#     它的作用是**跨会话**的：State 的 `user:` 前缀、Memory 的长期记忆，
#     都以 user_id 为作用域。所以 alice 的两个会话共享用户级数据，
#     但**不共享会话级数据** —— 这正是上面验收 ② 成立的原因。
#
#   session_id —— 「这是哪一次对话」。
#     它标识一次具体的会话，是对话历史的边界，也是会话级 State 的容器。
#
# 一句话记法：
#   user_id 决定「你的长期资料给谁看」，session_id 决定「这次聊的天算哪一轮」。
#
# **为什么这不是「模型记住了」？**
#   模型本身是无状态的 —— 每次请求都要把需要的历史重新发过去。
#   SessionService 的职责就是替你保存并回放这段历史。
#   所以隔不隔离，取决于服务按什么键取历史，而不是模型有多聪明。
# ---------------------------------------------------------------------------
