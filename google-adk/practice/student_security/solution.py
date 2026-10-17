"""完成审批匹配函数。纯函数不写账本；实际工具仍须在事务内复核。"""


def approve_request(principal: dict, request: dict, approval: dict, now: int) -> bool:
    """只有角色、租户、用户、订单、金额、有效期全部匹配才返回 True。"""
    raise NotImplementedError("TODO：先阅读 README 中的契约，再实现审批匹配")
