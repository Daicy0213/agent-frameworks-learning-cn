"""第 6 章练习 1：状态作用域实验。

不调用模型，直接用 InMemorySessionService 验证四种前缀的可见范围。
结论应与笔记中的表格一致：

    无前缀  → 仅当前会话
    user:   → 同一用户跨会话
    app:    → 该应用下所有用户
    temp:   → 仅当前轮，不落盘

运行：uv run python c6_1.py
"""

import asyncio

from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService
from google.genai import types

from _common import APP, run

USER_A = "alice"
USER_B = "bob"


async def get_state(service, user_id, session_id):
    session = await service.get_session(
        app_name=APP, user_id=user_id, session_id=session_id
    )
    assert session is not None
    return dict(session.state)


async def main():
    service = InMemorySessionService()

    await service.create_session(
        app_name=APP,
        user_id=USER_A,
        session_id="a1",
        state={
            "plain": "仅本会话",
            "user:theme": "蓝色",
            "app:version": "v1",
            "temp:scratch": "本轮临时值",
        },
    )
    a1 = await get_state(service, USER_A, "a1")

    assert a1["plain"] == "仅本会话"
    assert a1["user:theme"] == "蓝色"
    assert a1["app:version"] == "v1"
    assert "temp:scratch" not in a1, "temp: 不应写入持久状态"

    # 同一用户的第二个会话
    await service.create_session(app_name=APP, user_id=USER_A, session_id="a2")
    a2 = await get_state(service, USER_A, "a2")
    assert "plain" not in a2, "无前缀状态不应跨会话"
    assert a2["user:theme"] == "蓝色", "user: 应跨会话"
    assert a2["app:version"] == "v1", "app: 应跨会话"

    # 另一个用户
    await service.create_session(app_name=APP, user_id=USER_B, session_id="b1")
    b1 = await get_state(service, USER_B, "b1")
    assert b1["app:version"] == "v1", "app: 对所有用户可见"
    assert "user:theme" not in b1, "user: 不应泄漏给其他用户"

    # 运行中写入状态：通过事件的 state_delta
    session_a1 = await service.get_session(
        app_name=APP, user_id=USER_A, session_id="a1"
    )
    await service.append_event(
        session_a1,
        Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text="更新偏好")]),
            actions=EventActions(
                state_delta={"user:theme": "绿色", "plain": "第二次写入"}
            ),
        ),
    )
    a1_after = await get_state(service, USER_A, "a1")
    assert a1_after["user:theme"] == "绿色"
    assert a1_after["plain"] == "第二次写入"

    # 新会话能看到更新后的 user:，但仍看不到 plain
    await service.create_session(app_name=APP, user_id=USER_A, session_id="a3")
    a3 = await get_state(service, USER_A, "a3")
    assert a3["user:theme"] == "绿色"
    assert "plain" not in a3

    print("✅ 四种作用域的可见范围全部符合预期")


if __name__ == "__main__":
    run(main, need_api_key=False)
