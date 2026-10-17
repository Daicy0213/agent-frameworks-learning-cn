"""售后业务边界：身份来自宿主，审批和幂等由数据库复核。

金额统一用分；SQLite 适用于这个单机教学实验，不替代支付渠道的幂等协议。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str


ALICE = Principal("alice", "shop-a", "agent")
VIEWER = Principal("alice", "shop-a", "viewer")
BOB = Principal("bob", "shop-b", "agent")
MANAGER = Principal("manager", "shop-a", "manager")


def rejected(code: str) -> dict:
    return {"ok": False, "error": code}


class RefundStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY, tenant_id TEXT, owner_id TEXT,
                    amount_cents INTEGER, delivered_days INTEGER
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY, tenant_id TEXT, user_id TEXT,
                    approved_by TEXT, approved_at REAL,
                    order_id TEXT, amount_cents INTEGER, expires_at REAL,
                    used_key TEXT
                );
                CREATE TABLE IF NOT EXISTS refunds (
                    tenant_id TEXT, request_key TEXT, fingerprint TEXT,
                    refund_id TEXT, order_id TEXT, amount_cents INTEGER,
                    PRIMARY KEY (tenant_id, request_key)
                );
            """)
            # 兼容旧版本创建的数据库：补上审批人与审批时间。
            columns = {row[1] for row in db.execute("PRAGMA table_info(approvals)")}
            if "approved_by" not in columns:
                db.execute("ALTER TABLE approvals ADD COLUMN approved_by TEXT")
            if "approved_at" not in columns:
                db.execute("ALTER TABLE approvals ADD COLUMN approved_at REAL")
            db.executemany(
                "INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?)",
                [("A100", "shop-a", "alice", 10000, 3),
                 ("B200", "shop-b", "bob", 10000, 2),
                 ("A300", "shop-a", "alice", 10000, 40)],
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def query_order(self, principal: Principal, order_id: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM orders WHERE order_id=? AND tenant_id=? AND owner_id=?",
                (order_id, principal.tenant_id, principal.user_id),
            ).fetchone()
        if principal.role not in {"viewer", "agent"} or row is None:
            return rejected("ORDER_NOT_ACCESSIBLE")
        return {"ok": True, **dict(row), "eligible": row["delivered_days"] <= 7}

    def issue_approval(
        self, manager: Principal, recipient: Principal, order_id: str,
        amount_cents: int, *, lifetime: int = 300,
    ) -> str:
        """仅由受信任的人工审批入口调用；不注册为 Agent 工具。"""
        order = self.query_order(recipient, order_id)
        if (manager.role != "manager" or manager.tenant_id != recipient.tenant_id
                or not order["ok"] or not order["eligible"]
                or type(amount_cents) is not int
                or not 0 < amount_cents <= order["amount_cents"]):
            raise ValueError("审批身份、订单或金额无效")
        approval_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO approvals (approval_id, tenant_id, user_id,"
                " approved_by, approved_at, order_id, amount_cents,"
                " expires_at, used_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (approval_id, recipient.tenant_id, recipient.user_id,
                 manager.user_id, time.time(), order_id, amount_cents,
                 time.time() + lifetime),
            )
        return approval_id

    def refund(
        self, principal: Principal, order_id: str, amount_cents: int,
        approval_id: str, request_key: str,
    ) -> dict:
        """每次执行都复核身份，不能通过绕过 callback 绕过授权。"""
        if principal.role != "agent":
            return rejected("ROLE_DENIED")
        if type(amount_cents) is not int or not 0 < amount_cents <= 10000:
            return rejected("INVALID_AMOUNT")
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 100:
            return rejected("INVALID_KEY")
        order = self.query_order(principal, order_id)
        if not order["ok"]:
            return order
        if not order["eligible"]:
            return rejected("NOT_ELIGIBLE")
        payload = [principal.user_id, order_id, amount_cents, approval_id]
        fingerprint = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
        with self.connect() as db:
            # 检查、消费审批、写账本在同一个事务，防止并发重复退款。
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM refunds WHERE tenant_id=? AND request_key=?",
                (principal.tenant_id, request_key),
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    return rejected("IDEMPOTENCY_CONFLICT")
                return {"ok": True, "duplicate": True,
                        "refund_id": previous["refund_id"],
                        "amount_cents": previous["amount_cents"]}
            approval = db.execute(
                "SELECT * FROM approvals WHERE approval_id=?", (approval_id,),
            ).fetchone()
            if (not approval or approval["tenant_id"] != principal.tenant_id
                    or approval["user_id"] != principal.user_id
                    or approval["order_id"] != order_id
                    or approval["amount_cents"] != amount_cents
                    or approval["expires_at"] <= time.time()
                    or approval["used_key"] is not None):
                return rejected("APPROVAL_INVALID")
            total = db.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM refunds WHERE order_id=?",
                (order_id,),
            ).fetchone()[0]
            if total + amount_cents > order["amount_cents"]:
                return rejected("REFUND_EXCEEDS_PAID")
            refund_id = "refund-" + uuid.uuid4().hex
            db.execute("INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?)",
                       (principal.tenant_id, request_key, fingerprint, refund_id,
                        order_id, amount_cents))
            db.execute("UPDATE approvals SET used_key=? WHERE approval_id=?",
                       (request_key, approval_id))
        return {"ok": True, "duplicate": False, "refund_id": refund_id,
                "amount_cents": amount_cents}

    def ledger(self) -> list[dict]:
        """宿主验收接口，没有暴露给 Agent 或 HTTP 用户。"""
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM refunds")]
