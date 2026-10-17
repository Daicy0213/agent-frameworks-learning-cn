"""第 1 章练习 3：直接检查会话历史，验证完整的会话隔离边界。

运行：uv run python google-adk/practice/c1_3.py
不调用模型、不需要密钥。模型是否复述某句话，不能证明存储是否隔离。
"""

import asyncio

from google.adk.events import Event
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types

APP_NAME = "session_isolation"


async def append_text(
    service: InMemorySessionService, session: Session, text: str
) -> None:
    """用公开的事件接口保存一条用户消息；异常直接交给调用方。"""
    await service.append_event(
        session,
        Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text=text)]),
        ),
    )


async def history(
    service: InMemorySessionService, app_name: str, user_id: str, session_id: str
) -> list[str]:
    """重新从服务读取，避免把本地变量误当成已保存的历史。"""
    session = await service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if session is None:
        raise LookupError(f"找不到会话：{app_name}/{user_id}/{session_id}")
    return [
        part.text
        for event in session.events
        if event.content
        for part in event.content.parts or []
        if part.text is not None
    ]


async def main() -> None:
    service = InMemorySessionService()
    # 有意复用 work：session_id 单独并不是全局的会话身份。
    cases = {
        (APP_NAME, "alice", "work"): "ZEBRA-7",
        (APP_NAME, "alice", "personal"): "FALCON-3",
        (APP_NAME, "bob", "work"): "OTTER-9",
        ("another_app", "alice", "work"): "PANDA-2",
    }
    for (app, user, sid), code in cases.items():
        session = await service.create_session(
            app_name=app, user_id=user, session_id=sid
        )
        await append_text(service, session, code)

    # 同 app/同 user 换 session、同 app/同 session 换 user、同 user/session 换 app。
    for key, code in cases.items():
        assert await history(service, *key) == [code], key

    current = await service.get_session(
        app_name=APP_NAME, user_id="alice", session_id="work"
    )
    assert current is not None
    await append_text(service, current, "第二条消息")
    assert await history(service, APP_NAME, "alice", "work") == [
        "ZEBRA-7", "第二条消息"
    ]
    for key, code in cases.items():
        if key != (APP_NAME, "alice", "work"):
            assert await history(service, *key) == [code]

    await service.create_session(
        app_name=APP_NAME, user_id="alice", session_id="fresh"
    )
    assert await history(service, APP_NAME, "alice", "fresh") == []
    assert await service.get_session(
        app_name=APP_NAME, user_id="unknown", session_id="work"
    ) is None
    print("通过：历史按 (app_name, user_id, session_id) 隔离，同一会话保留两条消息。")


if __name__ == "__main__":
    asyncio.run(main())

# app_name 选择应用，user_id 选择该应用中的用户，session_id 选择该用户的会话。
# user: State 可以跨同一用户的会话共享；那不是把这些会话的消息历史合并。
# 本题证明 SessionService 的存取边界。HTTP 层还必须验证调用者是否有权访问
# 这个 user_id；把 user_id 字符串传给服务，本身不构成身份认证。
