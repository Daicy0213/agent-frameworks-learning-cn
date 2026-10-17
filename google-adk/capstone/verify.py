"""真实 HTTP + ADK Runner + SQLite 跨进程验收，默认零模型费用。"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from .store import ALICE, BOB, MANAGER, VIEWER, RefundStore

ROOT = Path(__file__).resolve().parents[1]


def local_get(url, **kwargs):
    return httpx.get(url, trust_env=False, **kwargs)


def local_post(url, **kwargs):
    return httpx.post(url, trust_env=False, **kwargs)


def verify_business(directory: Path):
    store = RefundStore(directory / "unit.sqlite")
    approval = store.issue_approval(MANAGER, ALICE, "A100", 3000)
    args = ("A100", 3000, approval, "key-1")
    assert store.refund(VIEWER, *args)["error"] == "ROLE_DENIED"
    assert store.refund(BOB, *args)["error"] == "ORDER_NOT_ACCESSIBLE"
    assert store.refund(ALICE, "A100", 3000, "FORGED", "k")["error"] == "APPROVAL_INVALID"
    expired = store.issue_approval(MANAGER, ALICE, "A100", 1000, lifetime=-1)
    assert store.refund(ALICE, "A100", 1000, expired, "k")["error"] == "APPROVAL_INVALID"
    assert store.refund(ALICE, "A100", True, approval, "k")["error"] == "INVALID_AMOUNT"
    assert store.ledger() == []
    first = store.refund(ALICE, *args)
    assert first["ok"] and not first["duplicate"]
    again = RefundStore(directory / "unit.sqlite").refund(ALICE, *args)
    assert again["duplicate"] and again["refund_id"] == first["refund_id"]
    assert store.refund(ALICE, "A100", 2000, approval, "key-1")["error"] == "IDEMPOTENCY_CONFLICT"
    assert store.refund(ALICE, "A100", 3000, approval, "key-2")["error"] == "APPROVAL_INVALID"
    assert len(store.ledger()) == 1 and store.ledger()[0]["amount_cents"] == 3000
    print("PASS 业务边界：身份、租户、伪造/过期审批、幂等冲突、账本")


@contextmanager
def server(directory: Path, backend: str):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (directory / "server.log").open("w+", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "capstone.server", "--data-dir", str(directory),
             "--port", str(port), "--backend", backend,
             *(["--business-only"] if backend == "deepseek" else [])], cwd=ROOT,
            stdout=log, stderr=log)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(120):
                if proc.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read()[-5000:])
                try:
                    response = local_get(base + "/health", timeout=1)
                    if response.is_success:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            else:
                raise TimeoutError("本地服务未就绪")
            yield base, response.json()["pid"]
        finally:
            if os.name == "nt" and proc.poll() is None:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def send(base, scenario, token="demo-alice", session="refund-demo"):
    response = local_post(base + "/run", headers={"Authorization": "Bearer " + token},
        json={"session_id": session, "message": json.dumps(scenario)}, timeout=120)
    response.raise_for_status()
    return response.json()


def verify_http(directory: Path, backend="offline"):
    store = RefundStore(directory / "business.sqlite")
    approval = store.issue_approval(MANAGER, ALICE, "A100", 3000)
    scenario = {"order_id": "A100", "amount_cents": 3000,
                "approval_id": approval, "request_key": "http-1"}
    headers = {"Authorization": "Bearer demo-alice"}
    with server(directory, backend) as (base, pid_a):
        assert local_post(base + "/run", json={"session_id": "x", "message": "x"}).status_code == 401
        first = send(base, scenario)
        expected = (["query_order", "create_refund"] if backend == "deepseek" else
                    ["list_skills", "load_skill", "load_skill_resource", "lookup_refund_policy", "request_refund"])
        assert first["calls"] == expected, first
        if backend == "offline":
            evidence = first["tool_results"][-2]["evidence"]
            assert evidence and all(e["tenant_id"] == ALICE.tenant_id for e in evidence)
            assert all(e["chunk_id"] and e["version"] for e in evidence)
        assert first["tool_results"][-1]["ok"] and not first["tool_results"][-1]["duplicate"], first
        assert first["final"]
        before_state = local_get(base + "/sessions/refund-demo", headers=headers).json()
        before = before_state["event_count"]
        before_fingerprint = before_state["event_fingerprint"]
        assert before >= 5
    with server(directory, backend) as (base, pid_b):
        assert pid_b != pid_a
        restored = local_get(base + "/sessions/refund-demo", headers=headers)
        assert restored.json()["event_count"] == before
        assert restored.json()["event_fingerprint"] == before_fingerprint
        assert local_get(base + "/sessions/refund-demo",
                        headers={"Authorization": "Bearer demo-bob"}).status_code == 404
        repeated = send(base, scenario)
        assert repeated["tool_results"][-1]["duplicate"], repeated
        assert repeated["tool_results"][-1]["refund_id"] == first["tool_results"][-1]["refund_id"]
        if backend == "offline":
            forbidden = send(base, scenario, "demo-viewer", "viewer")
            assert forbidden["tool_results"][-1]["error"] == "ROLE_DENIED"
            forged = send(base, {**scenario, "approval_id": "FORGED", "request_key": "x"})
            assert forged["tool_results"][-1]["error"] == "APPROVAL_INVALID"
            conflict = send(base, {**scenario, "amount_cents": 2000})
            assert conflict["tool_results"][-1]["error"] == "IDEMPOTENCY_CONFLICT"
    assert len(store.ledger()) == 1 and store.ledger()[0]["amount_cents"] == 3000
    calls = first["model_requests"] + repeated["model_requests"]
    print(f"PASS HTTP/Runner：进程 {pid_a} → {pid_b}，历史恢复，重复请求仅一笔退款；正常/重试共 {calls} 次模型请求")
    return {"backend": backend, "different_processes": pid_a != pid_b,
            "history_events_restored": before, "ledger_rows": len(store.ledger()),
            "amount_cents": store.ledger()[0]["amount_cents"],
            "normal_and_retry_model_requests": calls, "tool_path": first["calls"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["offline", "deepseek"], default="offline")
    parser.add_argument("--with-server", action="store_true", help="兼容旧命令；现在默认包含服务验收")
    parser.add_argument("--report-path", type=Path, help="可选：保存不含凭据的紧凑验收报告")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="adk-capstone-") as tmp:
        directory = Path(tmp)
        verify_business(directory)
        report = verify_http(directory, args.backend)

    if args.report_path:
        args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS Capstone：{args.backend}，临时服务和数据库均已清理")


if __name__ == "__main__":
    main()
