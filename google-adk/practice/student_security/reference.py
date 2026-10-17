"""第 12 章练习的参考实现，完成自己的版本后再阅读。"""


def approve_request(principal: dict, request: dict, approval: dict, now: int) -> bool:
    if principal.get("role") != "agent":
        return False
    amount = request.get("amount_cents")
    if type(amount) is not int or not 0 < amount <= 10000:
        return False
    fields = {"tenant_id": principal.get("tenant_id"), "user_id": principal.get("user_id"),
              "order_id": request.get("order_id"), "amount_cents": amount}
    if any(value is None or approval.get(key) != value for key, value in fields.items()):
        return False
    return approval.get("expires_at", 0) > now and approval.get("used_key") is None
