"""把回答与演示退款账本对照；文本正确不等于操作正确。"""

from typing import Any


def check_refund_effects(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    expected_created: list[dict[str, Any]],
) -> bool:
    """只允许声明的新增记录；原记录不得被删除或覆盖。"""
    if any(after.get(key) != value for key, value in before.items()):
        return False
    created = {key: value for key, value in after.items() if key not in before}
    expected = {item["idempotency_key"]: item for item in expected_created}
    if set(created) != set(expected):
        return False
    return all(
        all(created[key].get(field) == value
            for field, value in spec.items() if field != "idempotency_key")
        for key, spec in expected.items()
    )
