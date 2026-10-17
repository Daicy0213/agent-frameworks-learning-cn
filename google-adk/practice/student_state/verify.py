"""独立验收：测试输入、预期状态和断言不由学生实现提供。"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from copy import deepcopy
from pathlib import Path

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext


def load_solution(path: Path):
    spec = importlib.util.spec_from_file_location("student_state_answer", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载作业：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def verify(add_item) -> None:
    service = InMemorySessionService()
    key = {"app_name": "state_exam", "user_id": "reader", "session_id": "one"}
    await service.create_session(**key, state={"cart": {"苹果": 1}})

    async def context():
        session = await service.get_session(**key)
        assert session is not None
        ctx = ToolContext(InvocationContext(
            session_service=service, session=session,
            invocation_id="independent-state-check", agent=None,
        ))
        return session, ctx

    for name, qty, expected_cart, total in [
        ("苹果", 2, {"苹果": 3}, 15.0),
        ("牛奶", 2, {"苹果": 3, "牛奶": 2}, 32.0),
    ]:
        session, ctx = await context()
        old_cart = ctx.state["cart"]
        old_value = deepcopy(old_cart)
        result = add_item(name, qty, ctx)
        assert result["ok"] is True
        assert result["item"] == name and result["qty"] == expected_cart[name]
        assert result["total"] == total
        assert old_cart == old_value, "原地修改了旧购物车，请先复制容器"
        assert ctx.actions.state_delta == {"cart": expected_cart}, "没有正确记录 delta"
        before = await service.get_session(**key)
        assert before is not None and before.state["cart"] == old_value
        await service.append_event(session, Event(author="tool", actions=ctx.actions))
        saved = await service.get_session(**key)
        assert saved is not None and saved.state["cart"] == expected_cart
        assert saved.events[-1].actions.state_delta == {"cart": expected_cart}

    for name, qty, error in [
        ("苹果", 3, "OUT_OF_STOCK"), ("西瓜", 1, "ITEM_NOT_FOUND"),
        ("牛奶", 0, "INVALID_QTY"), ("牛奶", -1, "INVALID_QTY"),
        ("牛奶", True, "INVALID_QTY"), ("牛奶", 1.5, "INVALID_QTY"),
    ]:
        _, ctx = await context()
        before = deepcopy(ctx.state.to_dict())
        result = add_item(name, qty, ctx)
        assert result["ok"] is False and result["error"] == error
        assert ctx.state.to_dict() == before, "失败请求改变了状态"
        assert ctx.actions.state_delta == {}, "失败请求留下了待提交 delta"

    other = await service.create_session(
        app_name="state_exam", user_id="reader", session_id="two"
    )
    other_ctx = ToolContext(InvocationContext(
        session_service=service, session=other,
        invocation_id="another-session", agent=None,
    ))
    assert add_item("面包", 1, other_ctx)["total"] == 6.0
    await service.append_event(other, Event(author="tool", actions=other_ctx.actions))
    first = await service.get_session(**key)
    assert first is not None and first.state["cart"] == {"苹果": 3, "牛奶": 2}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", action="store_true", help="只验证现有参考答案")
    args = parser.parse_args()
    path = Path(__file__).with_name("solution.py")
    if args.reference:
        path = Path(__file__).resolve().parents[1] / "c4_2.py"
    asyncio.run(verify(load_solution(path).add_item))
    print("通过：业务规则、容器复制、真实 delta、提交读回和会话隔离。")


if __name__ == "__main__":
    main()
