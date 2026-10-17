"""学生作业：只完成 add_item，不修改验收器。"""

from google.adk.tools import ToolContext

STOCK = {"苹果": 5, "牛奶": 3, "面包": 2}
PRICE = {"苹果": 5.0, "牛奶": 8.5, "面包": 6.0}


def add_item(name: str, qty: int, tool_context: ToolContext) -> dict:
    """向 cart 加商品，返回结果；失败时不改变 State 或 delta。

    成功：{"ok": True, "item": name, "qty": 累计数量, "total": 总价}
    失败：{"ok": False, "error": 错误代码}
    错误代码：ITEM_NOT_FOUND、INVALID_QTY、OUT_OF_STOCK。
    qty 必须是正整数，bool 不是有效数量。
    """
    # TODO 1：检查商品和数量，拒绝非法输入。
    # TODO 2：读取已有购物车，计算累计数量，检查库存。
    # TODO 3：更新购物车，让真实 ADK State 生成可提交的 delta。
    # TODO 4：返回累计数量及整个购物车总价。
    raise NotImplementedError("请先完成 add_item，再运行 verify.py")
