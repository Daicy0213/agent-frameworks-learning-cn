"""第 4 章练习 2：购物车的变化怎样进入 ADK State delta。

运行：uv run python google-adk/practice/c4_2.py
不调用模型；使用真实 ToolContext、State、SessionService 和事件提交。
"""

from __future__ import annotations

import asyncio
from copy import deepcopy

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService, Session
from google.adk.sessions.state import State
from google.adk.tools import ToolContext

STOCK = {"苹果": 5, "牛奶": 3, "面包": 2}
PRICE = {"苹果": 5.0, "牛奶": 8.5, "面包": 6.0}


def _cart(tool_context: ToolContext) -> dict[str, int]:
    # cart 的值只有整数，浅复制足够；若值还有嵌套容器，需要复制将要修改的层。
    return dict(tool_context.state.get("cart", {}))


def _total(cart: dict[str, int]) -> float:
    return round(sum(PRICE[name] * qty for name, qty in cart.items()), 2)


def add_item(name: str, qty: int, tool_context: ToolContext) -> dict:
    """把正整数数量的商品加入购物车，库存不足时保持状态不变。"""
    if name not in STOCK:
        return {"ok": False, "error": "ITEM_NOT_FOUND", "item": name}
    if type(qty) is not int or qty <= 0:
        return {"ok": False, "error": "INVALID_QTY", "qty": qty}
    cart = _cart(tool_context)
    new_qty = cart.get(name, 0) + qty
    if new_qty > STOCK[name]:
        return {
            "ok": False, "error": "OUT_OF_STOCK", "item": name,
            "available": STOCK[name], "requested": new_qty,
        }
    cart[name] = new_qty
    tool_context.state["cart"] = cart  # 顶层赋值会记录 state_delta。
    return {"ok": True, "item": name, "qty": new_qty, "total": _total(cart)}


def remove_item(name: str, qty: int, tool_context: ToolContext) -> dict:
    """移除商品；数量归零时从购物车删除该条目。"""
    cart = _cart(tool_context)
    if name not in cart:
        return {"ok": False, "error": "NOT_IN_CART", "item": name}
    if type(qty) is not int or qty <= 0:
        return {"ok": False, "error": "INVALID_QTY", "qty": qty}
    left = cart[name] - qty
    if left > 0:
        cart[name] = left
    else:
        cart.pop(name)
    tool_context.state["cart"] = cart
    return {"ok": True, "item": name, "qty": max(left, 0), "total": _total(cart)}


def view_cart(tool_context: ToolContext) -> dict:
    """只读操作不应创建 State delta。"""
    cart = _cart(tool_context)
    return {"ok": True, "cart": cart, "total": _total(cart)}


def make_context(service: InMemorySessionService, session: Session) -> ToolContext:
    """只为离线实验组装真实上下文；正常运行时由 Runner 提供。"""
    return ToolContext(
        InvocationContext(
            invocation_id="cart-experiment", session_service=service,
            session=session, agent=None,
        )
    )


async def main() -> None:
    service = InMemorySessionService()
    key = {"app_name": "cart", "user_id": "alice", "session_id": "shopping"}
    await service.create_session(**key, state={"cart": {"苹果": 1}})

    # 反例：本地 cart 看似变了，State 却没有捕捉到嵌套字典的原地修改。
    session = await service.get_session(**key)
    assert session is not None
    broken = make_context(service, session.model_copy(deep=True))
    assert isinstance(broken.state, State)
    broken.state["cart"]["苹果"] = 4
    assert broken.state["cart"] == {"苹果": 4}
    assert broken.actions.state_delta == {}
    await service.append_event(session, Event(author="cart_tool", actions=broken.actions))
    saved = await service.get_session(**key)
    assert saved is not None and saved.state["cart"] == {"苹果": 1}

    # 正例：复制、修改、顶层重新赋值，再随事件提交。
    context = make_context(service, saved)
    previous_cart = context.state["cart"]
    assert add_item("苹果", 2, context)["qty"] == 3
    assert previous_cart == {"苹果": 1}, "不应原地修改旧容器"
    assert context.actions.state_delta == {"cart": {"苹果": 3}}
    before_commit = await service.get_session(**key)
    assert before_commit is not None and before_commit.state["cart"] == {"苹果": 1}
    await service.append_event(saved, Event(author="cart_tool", actions=context.actions))
    committed = await service.get_session(**key)
    assert committed is not None and committed.state["cart"] == {"苹果": 3}
    assert committed.events[-1].actions.state_delta == {"cart": {"苹果": 3}}

    context = make_context(service, committed)
    assert add_item("牛奶", 2, context)["total"] == 32.0
    unchanged = deepcopy(context.state.to_dict())
    delta_before = deepcopy(context.actions.state_delta)
    for name, qty, error in [
        ("牛奶", 2, "OUT_OF_STOCK"), ("西瓜", 1, "ITEM_NOT_FOUND"),
        ("苹果", 0, "INVALID_QTY"), ("苹果", True, "INVALID_QTY"),
    ]:
        assert add_item(name, qty, context)["error"] == error
        assert context.state.to_dict() == unchanged
        assert context.actions.state_delta == delta_before
    assert remove_item("苹果", 1, context)["qty"] == 2
    assert remove_item("苹果", 2, context)["qty"] == 0
    await service.append_event(committed, Event(author="cart_tool", actions=context.actions))
    reloaded = await service.get_session(**key)
    assert reloaded is not None and reloaded.state["cart"] == {"牛奶": 2}

    other = await service.create_session(
        app_name="cart", user_id="alice", session_id="another"
    )
    readonly = make_context(service, other)
    assert view_cart(readonly)["cart"] == {}
    assert readonly.actions.state_delta == {}
    print("通过：嵌套原地修改没有 delta；复制并赋值后，事件提交与读回一致。")


if __name__ == "__main__":
    asyncio.run(main())
