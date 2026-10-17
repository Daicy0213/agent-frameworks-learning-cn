"""练习：把身份/审批判断写在工具服务边界，不能从 Skill 文本推导。"""
from .business import Principal


def authorize_exchange(principal: Principal, order_tenant: str, order_id: str) -> bool:
    """换货也要求订单同租户、approver 角色和服务器订单审批记录。"""
    raise NotImplementedError("请实现换货授权规则")
