"""第 11 章练习 2：消费 /run_sse 的 token 级流式响应。

脚本会自己启动一个临时 api_server，建会话、发流式请求、统计 partial 事件，
最后关闭服务。需要 DEEPSEEK_API_KEY。

运行：uv run --env-file .env python c11_1.py
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from _common import run


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(base_url: str, proc: subprocess.Popen) -> None:
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError(f"api_server 提前退出，退出码 {proc.returncode}")
        try:
            httpx.get(base_url + "/", timeout=1.0)
            return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError("api_server 在 30 秒内没有就绪")


def main():
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
            f"{base_url}/apps/agent_demo/users/student/sessions",
            json={"session_id": "sse_demo"},
            timeout=10.0,
        ).raise_for_status()

        events = 0
        partials = 0
        text = ""

        with httpx.stream(
            "POST",
            f"{base_url}/run_sse",
            json={
                "app_name": "agent_demo",
                "user_id": "student",
                "session_id": "sse_demo",
                "streaming": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "用一句话介绍 ADK"}],
                },
            },
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                events += 1
                payload = json.loads(line[len("data:") :].strip())
                if payload.get("partial"):
                    partials += 1
                for part in payload.get("content", {}).get("parts", []):
                    text += part.get("text", "")

        print(f"事件数：{events}，partial 事件：{partials}")
        print(f"拼接文本：{text[:100]}")

        assert events > 1, "只收到一个事件，可能没有开启流式"
        assert partials > 1, "没有 token 级 partial 事件"
        assert text.strip(), "没有收到文本"
        print("✅ /run_sse 返回了 token 级流式响应")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    run(main)
