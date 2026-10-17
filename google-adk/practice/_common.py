"""练习参考实现的共用工具。

`deepseek` / `input_text` / `collect` / `start` 与 07、08 两章 Notebook 保持一致；
`require_google_adk` 与 `run` 供各章练习复用，避免每个文件重复样板代码。
"""

from __future__ import annotations

import asyncio
import importlib.metadata as metadata
import inspect
import json
import os
from uuid import uuid4

# 使用随 LiteLLM 安装的本地成本表；模型请求仍然发往真实 DeepSeek API。
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP, USER = "adk_practice", "student"


def require_env() -> None:
    """需要真实调用模型时的前置检查：缺少密钥或版本不符就直接报错。

    这是有意"不静默跳过"的：第 7、8 章的结论都建立在真实模型行为上，
    悄悄换成本地假数据会让验证失去意义。
    """
    require_google_adk()
    assert os.getenv("DEEPSEEK_API_KEY"), "请先配置 DEEPSEEK_API_KEY 再运行本练习。"


def require_google_adk() -> None:
    """只要框架版本正确即可，不涉及模型调用。"""
    version = metadata.version("google-adk")
    assert version == "2.6.3", f"请从项目根目录执行 uv sync（当前 google-adk {version}）。"


def deepseek(max_tokens: int = 768) -> LiteLlm:
    """与第 7、8 章一致的接入方式：JSON Output + 本地 Pydantic 校验。"""
    return LiteLlm(
        model="deepseek/deepseek-chat",
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )


def input_text(value) -> str:
    """把 Runner 入口的 Content 归一成字符串。"""
    if isinstance(value, types.Content):
        return "".join(part.text or "" for part in value.parts or [])
    if isinstance(value, str):
        return value
    raise TypeError(f"入口需要 Content 或 str，实际是 {type(value).__name__}")


async def collect(runner, session_id, message, *, invocation_id=None):
    """跑一轮，并从 Event 流里取出根输出（output_for 中不含 "/" 的那条）。"""
    output, events = None, []
    async for event in runner.run_async(
        user_id=USER,
        session_id=session_id,
        new_message=message,
        invocation_id=invocation_id,
    ):
        events.append(event)
        if event.node_info and event.output is not None:
            if any("/" not in path for path in event.node_info.output_for or []):
                output = event.output
    return output, events


async def start(workflow, payload, *, session_service=None, artifact_service=None):
    """新建会话并跑一次工作流，返回 (根输出, 事件列表, runner, session_id)。"""
    service = session_service or InMemorySessionService()
    session_id = uuid4().hex
    await service.create_session(app_name=APP, user_id=USER, session_id=session_id)
    runner = Runner(
        agent=workflow,
        app_name=APP,
        session_service=service,
        artifact_service=artifact_service,
    )
    text = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False)
    )
    message = types.Content(role="user", parts=[types.Part(text=text)])
    output, events = await collect(runner, session_id, message)
    return output, events, runner, session_id


def run(main_fn, *, need_api_key: bool = True) -> None:
    """统一入口：先检查环境，再跑主函数。

    不调用模型的练习传 need_api_key=False，这样无需 DEEPSEEK_API_KEY 也能跑通。
    主函数可以是 async 的，也可以是普通同步函数。
    """
    if need_api_key:
        require_env()
    else:
        require_google_adk()
    result = main_fn()
    if inspect.isawaitable(result):
        asyncio.run(result)
