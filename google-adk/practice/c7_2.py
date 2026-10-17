"""第 7 章练习 2：高风险工具的策略执行点。

不调用模型：直接调用 before_tool 回调，验证拒绝时工具本体不会执行，
以及幂等键能让重复请求只产生一次副作用。

运行：uv run python c7_2.py
"""

from __future__ import annotations

from dataclasses import dataclass

from _common import run

MAX_REFUND = 1000
AGENT_AUTO_LIMIT = 200


@dataclass
class FakeTool:
    name: str = "create_refund_request"


EXECUTED: list[dict] = []
LEDGER: dict[str, dict] = {}


def refund_policy(tool, args: dict, tool_context):
    """before_tool 回调：返回 None 放行，返回 dict 短路。"""
    role = args.get("role")
    amount = args.get("amount")
    approval = args.get("approval_code")
    key = args.get("idempotency_key")

    if role not in {"agent", "manager"}:
        return {"ok": False, "error": "ROLE_DENIED", "detail": "缺少有效角色"}

    if not isinstance(amount, (int, float)) or amount <= 0:
        return {"ok": False, "error": "INVALID_AMOUNT", "amount": amount}

    if amount > MAX_REFUND:
        return {"ok": False, "error": "AMOUNT_EXCEEDED", "limit": MAX_REFUND}

    if role == "agent" and amount > AGENT_AUTO_LIMIT and not approval:
        return {"ok": False, "error": "APPROVAL_REQUIRED", "limit": AGENT_AUTO_LIMIT}

    if not key:
        return {"ok": False, "error": "IDEMPOTENCY_KEY_REQUIRED"}

    return None


def attempt(args: dict) -> dict | None:
    """模拟框架：先过策略，放行才执行工具本体。"""
    decision = refund_policy(FakeTool(), args, None)
    if decision is not None:
        return decision

    key = args["idempotency_key"]
    if key in LEDGER:
        return {"ok": True, "deduplicated": True, "request": LEDGER[key]}

    record = {"user_id": args["user_id"], "amount": args["amount"]}
    LEDGER[key] = record
    EXECUTED.append(record)
    return {"ok": True, "deduplicated": False, "request": record}


def base(**overrides) -> dict:
    args = {
        "user_id": "U1",
        "role": "agent",
        "amount": 100,
        "approval_code": None,
        "idempotency_key": "K1",
    }
    args.update(overrides)
    return args


def main():
    assert attempt(base(role="guest"))["error"] == "ROLE_DENIED"
    assert attempt(base(amount=0))["error"] == "INVALID_AMOUNT"
    assert attempt(base(amount=5000))["error"] == "AMOUNT_EXCEEDED"
    assert attempt(base(amount=300))["error"] == "APPROVAL_REQUIRED"
    assert attempt(base(idempotency_key=None))["error"] == "IDEMPOTENCY_KEY_REQUIRED"

    # 被拒绝的请求没有产生任何副作用
    assert EXECUTED == [], f"拒绝路径不应执行工具，实际执行了 {EXECUTED}"

    # 合法的大额退款：需要审批码
    result = attempt(base(amount=300, approval_code="APR-1"))
    assert result["ok"] and not result["deduplicated"]
    assert len(EXECUTED) == 1

    # 重复请求：同一个幂等键只执行一次
    again = attempt(base(amount=300, approval_code="APR-1"))
    assert again["ok"] and again["deduplicated"] is True
    assert len(EXECUTED) == 1, "重复请求不应产生第二条副作用"

    print("✅ 拒绝无副作用、审批门槛、幂等去重全部通过")


if __name__ == "__main__":
    run(main, need_api_key=False)
