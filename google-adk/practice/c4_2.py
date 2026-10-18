"""第 4 章练习 2：用 ToolContext 管理购物车。

本文件不调用模型：直接调用工具函数，并用一个最小的假上下文验证状态行为。
这样断言是确定性的，失败时一定是逻辑问题，不是模型抖动。

运行：uv run python c4_2.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeToolContext:
    """只实现工具真正用到的接口：state。"""

    state: dict


STOCK = {"苹果": 5, "牛奶": 3, "面包": 2}
PRICE = {"苹果": 5.0, "牛奶": 8.5, "面包": 6.0}


def _cart(tool_context) -> dict:
    return tool_context.state.setdefault("cart", {})


def _total(cart: dict) -> float:
    return round(sum(PRICE[name] * qty for name, qty in cart.items()), 2)


def add_item(name: str, qty: int, tool_context: FakeToolContext) -> dict:
    """把商品加入购物车。

    Args:
        name: 商品名，例如 苹果。
        qty: 数量，必须大于 0。
    """
    if name not in STOCK:
        return {"ok": False, "error": "ITEM_NOT_FOUND", "item": name}
    if qty <= 0:
        return {"ok": False, "error": "INVALID_QTY", "qty": qty}

    cart = _cart(tool_context)
    new_qty = cart.get(name, 0) + qty
    if new_qty > STOCK[name]:
        return {
            "ok": False,
            "error": "OUT_OF_STOCK",
            "item": name,
            "available": STOCK[name],
            "requested": new_qty,
        }

    cart[name] = new_qty
    return {"ok": True, "item": name, "qty": new_qty, "total": _total(cart)}


def remove_item(name: str, qty: int, tool_context: FakeToolContext) -> dict:
    """从购物车移除商品。

    Args:
        name: 商品名。
        qty: 移除数量，必须大于 0。
    """
    cart = _cart(tool_context)
    if name not in cart:
        return {"ok": False, "error": "NOT_IN_CART", "item": name}
    if qty <= 0:
        return {"ok": False, "error": "INVALID_QTY", "qty": qty}

    left = cart[name] - qty
    if left > 0:
        cart[name] = left
    else:
        cart.pop(name)
    return {"ok": True, "item": name, "qty": max(left, 0), "total": _total(cart)}


def view_cart(tool_context: FakeToolContext) -> dict:
    """查看购物车与总价。"""
    cart = _cart(tool_context)
    return {"ok": True, "cart": dict(cart), "total": _total(cart)}


def main():
    ctx_a = FakeToolContext(state={})

    assert add_item("苹果", 2, ctx_a)["ok"] is True
    assert add_item("苹果", 1, ctx_a)["qty"] == 3, "数量应累加"
    assert add_item("牛奶", 2, ctx_a)["total"] == 3 * 5.0 + 2 * 8.5

    out_of_stock = add_item("牛奶", 2, ctx_a)
    assert out_of_stock["error"] == "OUT_OF_STOCK", "库存不足必须拒绝"

    assert add_item("西瓜", 1, ctx_a)["error"] == "ITEM_NOT_FOUND"
    assert add_item("苹果", 0, ctx_a)["error"] == "INVALID_QTY"

    assert remove_item("苹果", 1, ctx_a)["qty"] == 2
    assert remove_item("苹果", 2, ctx_a)["qty"] == 0
    assert "苹果" not in view_cart(ctx_a)["cart"], "数量归零后应移除"

    # 会话隔离：另一个上下文看不到 A 的购物车
    ctx_b = FakeToolContext(state={})
    assert view_cart(ctx_b)["cart"] == {}
    assert view_cart(ctx_a)["cart"] == {"牛奶": 2}

    print("✅ 累加、库存、非法输入、移除和会话隔离全部通过")


if __name__ == "__main__":
    main()
