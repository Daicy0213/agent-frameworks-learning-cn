"""第 6 章练习 2：跨会话用户偏好。

不调用模型，直接验证 user: 状态在会话之间的可见性，以及"忘记"的实现边界。

重要结论：
  ADK 的 state_delta 没有"删除键"的语义；写 None 只会留下一个 None 值。
  真正的删除发生在存储层（删除行/淘汰策略），业务层可以用墓碑值表达"已忘记"。

运行：uv run python c6_2.py
"""

import asyncio

from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService
from google.genai import types

from _common import APP, run

USER_A = "alice"
USER_B = "bob"
DELETED = "<deleted>"


async def remember(service, user_id, session_id, values: dict):
    session = await service.get_session(
        app_name=APP, user_id=user_id, session_id=session_id
    )
    assert session is not None
    await service.append_event(
        session,
        Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text="更新偏好")]),
            actions=EventActions(state_delta=values),
        ),
    )


async def state_of(service, user_id, session_id):
    session = await service.get_session(
        app_name=APP, user_id=user_id, session_id=session_id
    )
    assert session is not None
    return dict(session.state)


def preferences(state: dict) -> dict:
    return {
        key: value
        for key, value in state.items()
        if key.startswith("user:pref_") and value != DELETED
    }


async def main():
    service = InMemorySessionService()
    await service.create_session(app_name=APP, user_id=USER_A, session_id="a1")

    await remember(
        service,
        USER_A,
        "a1",
        {"user:pref_diet": "素食", "user:pref_allergy": "花生"},
    )

    # 全新会话仍能看到
    await service.create_session(app_name=APP, user_id=USER_A, session_id="a2")
    a2 = await state_of(service, USER_A, "a2")
    assert preferences(a2) == {"user:pref_diet": "素食", "user:pref_allergy": "花生"}

    # 另一个用户看不到
    await service.create_session(app_name=APP, user_id=USER_B, session_id="b1")
    b1 = await state_of(service, USER_B, "b1")
    assert preferences(b1) == {}, "用户偏好不能跨用户泄漏"

    # "忘记"：业务层用墓碑值表达
    await remember(service, USER_A, "a2", {"user:pref_diet": DELETED})
    await service.create_session(app_name=APP, user_id=USER_A, session_id="a3")
    a3 = await state_of(service, USER_A, "a3")
    assert preferences(a3) == {"user:pref_allergy": "花生"}
    assert a3["user:pref_diet"] == DELETED, "墓碑值仍在存储里，真正删除要靠存储层"

    print("✅ 跨会话偏好、用户隔离与墓碑式忘记均符合预期")
    print("   过期/真删除属于 SessionService 的存储策略，不是 State 前缀能解决的。")


if __name__ == "__main__":
    run(main, need_api_key=False)
