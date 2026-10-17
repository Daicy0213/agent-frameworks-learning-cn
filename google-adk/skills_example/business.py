"""业务授权位于 Python 服务边界；Skill 只描述如何使用工具。"""
from __future__ import annotations

from dataclasses import dataclass, field

from rag_example.retrieval import LexicalIndex, Retriever, Scope


@dataclass(frozen=True)
class Principal:
    """由应用认证层提供；演示中的构造参数不代表生产身份认证。"""
    tenant_id: str = "shop-a"
    role: str = "viewer"
    approved_orders: frozenset[str] = frozenset()


@dataclass
class RefundDesk:
    principal: Principal = field(default_factory=Principal)
    retriever: Retriever = field(default_factory=LexicalIndex.build)
    receipts: dict[str, dict] = field(default_factory=dict)

    def lookup_refund_policy(self, query: str) -> dict:
        """检索当前调用者租户的有效售后政策；只读，不批准退款。"""
        scope = Scope(self.principal.tenant_id, "2026-10-01")
        hits = self.retriever.search(query, scope, k=3)
        if any(not hit.chunk.visible(scope) for hit in hits):
            raise ValueError("检索适配器返回了范围外证据")
        return {"evidence": [hit.evidence() for hit in hits]}

    def request_refund(self, order_id: str, amount: int) -> dict:
        """按服务器身份、订单归属、审批记录核验，创建内存受理记录；不转账。"""
        orders = {"A-100": {"tenant_id": "shop-a", "amount": 120}}
        order = orders.get(order_id)
        if order is None or order["tenant_id"] != self.principal.tenant_id:
            return {"status": "denied", "reason": "order_not_accessible"}
        if self.principal.role != "approver" or order_id not in self.principal.approved_orders:
            return {"status": "denied", "reason": "server_approval_required"}
        if amount <= 0 or amount != order["amount"]:
            return {"status": "denied", "reason": "amount_mismatch"}
        key = f"{self.principal.tenant_id}:{order_id}"
        if key not in self.receipts:
            self.receipts[key] = {
                "status": "accepted", "receipt_id": f"demo-{order_id}",
                "order_id": order_id, "amount": amount,
                "notice": "仅创建内存受理记录，未发生资金转移",
            }
        return dict(self.receipts[key])
