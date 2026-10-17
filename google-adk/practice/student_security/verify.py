"""独立验收；默认导入学生实现，--reference 检查参考答案。"""
import argparse
import importlib


def verify(check):
    principal = {"role": "agent", "tenant_id": "shop-a", "user_id": "alice"}
    request = {"order_id": "A100", "amount_cents": 3000}
    approval = {"tenant_id": "shop-a", "user_id": "alice", "order_id": "A100",
                "amount_cents": 3000, "expires_at": 100, "used_key": None}
    assert check(principal, request, approval, 99) is True
    assert check(principal, request, {}, 99) is False
    assert check({**principal, "role": "viewer"}, request, approval, 99) is False
    assert check({**principal, "tenant_id": "shop-b"}, request, approval, 99) is False
    assert check({**principal, "user_id": "bob"}, request, approval, 99) is False
    assert check(principal, {**request, "amount_cents": 2000}, approval, 99) is False
    assert check(principal, {**request, "order_id": "B200"}, approval, 99) is False
    assert check(principal, {**request, "amount_cents": True}, approval, 99) is False
    assert check(principal, request, approval, 100) is False
    assert check(principal, request, {**approval, "used_key": "old"}, 99) is False
    print("PASS 10 项审批契约；副作用与事务另由 Capstone 验收")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", action="store_true")
    args = parser.parse_args()
    verify(importlib.import_module("reference" if args.reference else "solution").approve_request)
