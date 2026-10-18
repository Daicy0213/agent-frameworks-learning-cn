"""Capstone 验收器。

默认只跑离线阶段（不调用模型、不启动服务）：

    uv run python -m capstone.verify

加上 --with-server 后额外验证本地 HTTP 服务（会调用一次 DeepSeek）：

    uv run --env-file ../.env python -m capstone.verify --with-server
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]          # google-adk/
PRACTICE = ROOT / "practice"


def run_script(name: str) -> tuple[bool, str]:
    path = PRACTICE / name
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=PRACTICE,
        capture_output=True,
        text=True,
        timeout=120,
    )
    tail = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, tail[-1] if tail else ""


def stage_offline() -> list[tuple[str, bool, str]]:
    checks = [
        ("工具：购物车状态", "c4_2.py"),
        ("工具：输入护栏", "c7_1.py"),
        ("工具：高风险策略", "c7_2.py"),
        ("会话：状态作用域", "c6_1.py"),
        ("会话：跨会话偏好", "c6_2.py"),
        ("评估：数据集校验", "c10_1.py"),
        ("安全：护栏与脱敏", "c12_1.py"),
        ("安全：最小权限", "c12_2.py"),
    ]
    return [(label, *run_script(script)) for label, script in checks]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stage_server() -> tuple[str, bool, str]:
    adk = shutil.which("adk")
    if not adk:
        return ("服务：HTTP 调用", False, "找不到 adk 命令")

    port = free_port()
    proc = subprocess.Popen(
        [adk, "api_server", str(ROOT), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            if proc.poll() is not None:
                return ("服务：HTTP 调用", False, "服务提前退出")
            try:
                httpx.get(base + "/", timeout=1.0)
                break
            except Exception:
                time.sleep(0.5)

        httpx.post(
            f"{base}/apps/agent_demo/users/student/sessions",
            json={"session_id": "capstone"},
            timeout=10.0,
        ).raise_for_status()

        response = httpx.post(
            f"{base}/run",
            json={
                "app_name": "agent_demo",
                "user_id": "student",
                "session_id": "capstone",
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "用一句话介绍你自己"}],
                },
            },
            timeout=120.0,
        )
        response.raise_for_status()
        events = response.json()
        ok = bool(events) and any(
            part.get("text")
            for event in events
            for part in (event.get("content") or {}).get("parts", [])
        )
        return ("服务：HTTP 调用", ok, f"{len(events)} 个事件")
    except Exception as exc:  # noqa: BLE001 - 验收器需要把失败原因报出来
        return ("服务：HTTP 调用", False, f"{type(exc).__name__}: {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capstone 验收器")
    parser.add_argument(
        "--with-server",
        action="store_true",
        help="额外启动 api_server 验证 HTTP 调用（会调用模型）",
    )
    args = parser.parse_args()

    results = stage_offline()
    if args.with_server:
        results.append(stage_server())

    print("\nCapstone 验收结果")
    print("=" * 56)
    failed = 0
    for label, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {label:<18} {detail}")
        failed += 0 if ok else 1

    print("=" * 56)
    print(f"{len(results) - failed}/{len(results)} 通过")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
