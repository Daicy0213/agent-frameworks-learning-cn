"""输入护栏、退款策略执行点和结构化观测回调。"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .tools import validate_refund_request


logger = logging.getLogger("eval_example")

_MAX_INPUT_CHARS = 1200
_SECRET_PATTERNS = (
    re.compile(r"(?:api[ _-]?key|密钥|银行卡密码).{0,12}(?:给我|告诉我|是什么|导出)", re.I),
    re.compile(r"(?:给我|告诉我|导出).{0,12}(?:api[ _-]?key|密钥|银行卡密码)", re.I),
)
_INJECTION_PATTERNS = (
    re.compile(r"忽略.{0,12}(?:之前|以上|所有).{0,12}(?:指令|规则)", re.I),
    re.compile(r"(?:输出|泄露|展示).{0,12}(?:系统提示词|system prompt|开发者消息)", re.I),
)


def _latest_user_text(llm_request: LlmRequest) -> str:
    """只取最新用户消息，避免多轮会话里的旧文本反复触发护栏。"""

    for content in reversed(llm_request.contents or []):
        if content.role == "user" and content.parts:
            return "".join(part.text or "" for part in content.parts)
    return ""


def _short_circuit(message: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    text=f"处理结果：{message}\n下一步：请改述为正常的订单或售后问题。"
                )
            ],
        )
    )


def input_safety_guard(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """在模型调用前拦截超长输入、提示注入和密钥索取。"""

    del callback_context
    text = _latest_user_text(llm_request)
    reason = None
    if len(text) > _MAX_INPUT_CHARS:
        reason = "输入过长，已停止处理。"
    elif any(pattern.search(text) for pattern in _INJECTION_PATTERNS):
        reason = "请求包含越权指令，已按安全策略拒绝。"
    elif any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        reason = "不能提供或处理密钥、密码等敏感凭据。"

    if reason:
        logger.warning(
            json.dumps(
                {
                    "event": "input_blocked",
                    "reason": reason,
                    "input_chars": len(text),
                    # 不记录原文，避免日志成为敏感数据的第二落点。
                },
                ensure_ascii=False,
            )
        )
        return _short_circuit(reason)
    return None


def refund_policy_guard(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    """退款工具的策略执行点；返回字典会跳过真实工具。"""

    del tool_context
    if tool.name != "create_refund_request":
        return None

    error = validate_refund_request(args)
    if error:
        return error
    amount = float(args["amount"])

    logger.info(
        json.dumps(
            {
                "event": "refund_authorized",
                "tool": tool.name,
                "order_id": args["order_id"],
                "amount": amount,
                "idempotency_key": args["idempotency_key"],
            },
            ensure_ascii=False,
        )
    )
    return None


def before_model_observer(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """记录最小必要的模型调用元数据，不记录消息正文。"""

    callback_context.state["eval:model_started_at"] = time.perf_counter()
    logger.info(
        json.dumps(
            {
                "event": "model_start",
                "agent": callback_context.agent_name,
                "message_count": len(llm_request.contents or []),
            },
            ensure_ascii=False,
        )
    )
    return None


def after_model_observer(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> None:
    """记录模型耗时和是否出错，供本地日志或 OTel 采集器消费。"""

    started = callback_context.state.get("eval:model_started_at")
    duration_ms = (time.perf_counter() - started) * 1000 if started else None
    logger.info(
        json.dumps(
            {
                "event": "model_end",
                "agent": callback_context.agent_name,
                "duration_ms": round(duration_ms, 2) if duration_ms else None,
                "has_error": bool(llm_response.error_code),
            },
            ensure_ascii=False,
        )
    )
    return None
