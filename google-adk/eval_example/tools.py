"""售后 Agent 使用的确定性演示工具。

这里故意不用真实数据库或支付网关：评估集需要可重复，教学代码也不应该
因为一次模型误判就真的退款。生产环境中应把这些函数替换为受鉴权的服务调用。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


# 固定时钟让“签收后几天”的判断在任何日期运行都得到相同结果。
_ORDERS: dict[str, dict[str, Any]] = {
    "A1001": {
        "order_id": "A1001",
        "status": "已签收",
        "item": "机械键盘",
        "amount": 299.0,
        "days_since_delivery": 2,
    },
    "A1002": {
        "order_id": "A1002",
        "status": "运输中",
        "item": "USB-C 扩展坞",
        "amount": 89.0,
        "days_since_delivery": None,
    },
    "A1003": {
        "order_id": "A1003",
        "status": "已签收",
        "item": "显示器支架",
        "amount": 199.0,
        "days_since_delivery": 15,
    },
    "A1004": {
        "order_id": "A1004",
        "status": "已取消",
        "item": "无线鼠标",
        "amount": 129.0,
        "days_since_delivery": None,
    },
}

_POLICIES = {
    "退货": "已签收商品支持 7 天无理由退货；定制品、影响二次销售的商品除外。",
    "退款时效": "退款审核通过后，原支付渠道通常在 1 至 5 个工作日到账。",
    "物流": "运输中订单可查询物流；超过 72 小时无更新可转人工客服核查。",
    "发票": "电子发票可在订单完成后申请，抬头一经开具不可直接修改。",
}

# 模拟支付系统中的幂等记录。只有安全回调放行后，工具本体才会写入。
_REFUND_REQUESTS: dict[str, dict[str, Any]] = {}


def reset_demo_state() -> None:
    """清空演示退款记录，供测试和重复评估使用。"""

    _REFUND_REQUESTS.clear()


def get_refund_requests() -> dict[str, dict[str, Any]]:
    """返回退款记录副本，避免测试代码意外修改内部状态。"""

    return deepcopy(_REFUND_REQUESTS)


def query_order(order_id: str) -> dict[str, Any]:
    """查询一个订单的当前状态。

    Args:
        order_id: 完整订单号，例如 A1001。
    """

    normalized = order_id.strip().upper()
    if normalized == "A1005":
        # 专门用于演示“依赖服务失败”如何进入评估与观测。
        return {
            "ok": False,
            "error_code": "ORDER_SERVICE_UNAVAILABLE",
            "message": "订单服务暂时不可用，请稍后重试或转人工客服。",
        }
    order = _ORDERS.get(normalized)
    if not order:
        return {
            "ok": False,
            "error_code": "ORDER_NOT_FOUND",
            "message": "未找到该订单，请核对完整订单号。",
        }
    return {"ok": True, "order": deepcopy(order)}


def search_after_sales_policy(topic: str) -> dict[str, Any]:
    """按主题查询售后政策。

    Args:
        topic: 仅可使用“退货”“退款时效”“物流”或“发票”。
    """

    policy = _POLICIES.get(topic.strip())
    if policy is None:
        return {
            "ok": False,
            "error_code": "POLICY_NOT_FOUND",
            "available_topics": sorted(_POLICIES),
            "message": "没有找到对应政策，建议转人工客服确认。",
        }
    return {"ok": True, "topic": topic.strip(), "policy": policy}


def assess_refund_eligibility(order_id: str, reason: str) -> dict[str, Any]:
    """判断订单是否满足演示退款规则，但不会真正发起退款。

    Args:
        order_id: 完整订单号，例如 A1001。
        reason: 用户原始退款原因，不要改写。
    """

    result = query_order(order_id)
    if not result["ok"]:
        return result
    order = result["order"]
    if order["status"] != "已签收":
        return {
            "ok": True,
            "eligible": False,
            "reason": "订单尚未签收或已取消，不能按已签收退货流程退款。",
            "order_id": order["order_id"],
        }
    if order["days_since_delivery"] > 7:
        return {
            "ok": True,
            "eligible": False,
            "reason": "已超过 7 天无理由退货期，需转人工判断质量问题。",
            "order_id": order["order_id"],
        }
    return {
        "ok": True,
        "eligible": True,
        "order_id": order["order_id"],
        "user_reason": reason,
        "max_refund_amount": order["amount"],
        "next_step": "取得审批码和幂等键后才可提交退款。",
    }


def create_refund_request(
    order_id: str,
    amount: float,
    reason: str,
    approval_code: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """创建退款申请；调用前必须经过 ``refund_policy_guard``。

    Args:
        order_id: 完整订单号。
        amount: 退款金额，不能超过可退金额。
        reason: 用户原始退款原因。
        approval_code: 审批系统给出的演示审批码。
        idempotency_key: 调用方生成的唯一幂等键。
    """

    # 工具本体仍实现幂等，体现“回调做策略、服务做最终一致性”的双层防护。
    if idempotency_key in _REFUND_REQUESTS:
        return {
            "ok": True,
            "duplicate": True,
            "request": deepcopy(_REFUND_REQUESTS[idempotency_key]),
        }

    request = {
        "refund_request_id": f"RF-{len(_REFUND_REQUESTS) + 1:04d}",
        "order_id": order_id.strip().upper(),
        "amount": float(amount),
        "reason": reason,
        "status": "待审核",
    }
    _REFUND_REQUESTS[idempotency_key] = request
    return {"ok": True, "duplicate": False, "request": deepcopy(request)}
