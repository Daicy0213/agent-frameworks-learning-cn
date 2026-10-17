"""第 11 章练习 2：消费 /run_sse 的 文本增量流式响应。

脚本会自己启动一个临时 api_server，建会话、发流式请求、统计 partial 事件，
最后关闭服务。默认使用离线模型；--backend deepseek 需要 DEEPSEEK_API_KEY。

运行：uv run --env-file .env python c11_1.py
"""

from __future__ import annotations

import argparse
import os
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from _common import run
from google.adk.events import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_example.verify import TextCollector


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(base_url: str, proc: subprocess.Popen) -> None:
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError(f"api_server 提前退出，退出码 {proc.returncode}")
        try:
            httpx.get(base_url + "/list-apps", timeout=1.0, trust_env=False)
            return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError("api_server 在 30 秒内没有就绪")


def main():
    app_name = "agent_demo" if args.backend == "deepseek" else "runtime_example"
    adk = shutil.which("adk")
    if not adk:
        raise RuntimeError("找不到 adk 命令，请用 uv run 执行本脚本")

    agents_dir = Path(__file__).resolve().parents[1]
    port = free_port()
    proc = subprocess.Popen(
        [
            adk,
            "api_server",
            str(agents_dir),
            "--session_service_uri",
            "memory://",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"
    try:
        wait_ready(base_url, proc)

        httpx.post(
            f"{base_url}/apps/{app_name}/users/student/sessions",
            json={"session_id": "sse_demo"},
            timeout=10.0,
            trust_env=False,
        ).raise_for_status()

        events = 0
        partials = 0
        collector = TextCollector("study_buddy" if args.backend == "deepseek" else "answer")

        with httpx.stream(
            "POST",
            f"{base_url}/run_sse",
            json={
                "app_name": app_name,
                "user_id": "student",
                "session_id": "sse_demo",
                "streaming": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "用一句话介绍 ADK"}],
                },
            },
            timeout=120.0,
            trust_env=False,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                events += 1
                payload = json.loads(line[len("data:") :].strip())
                if payload.get("partial"):
                    partials += 1
                collector.accept(Event.model_validate(payload))

        print(f"事件数：{events}，partial 事件：{partials}")
        print(f"拼接文本：{collector.text[:100]}")

        assert events > 1, "只收到一个事件，可能没有开启流式"
        assert partials >= 1, "没有 partial 文本事件"
        assert collector.text.strip(), "没有收到文本"
        print("✅ /run_sse 返回了 文本增量流式响应")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["offline", "deepseek"], default="offline")
    args = parser.parse_args()
    run(main, need_api_key=args.backend == "deepseek")
