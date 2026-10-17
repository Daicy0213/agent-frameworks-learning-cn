"""执行真实 ADK Runner，模型替身使事件与故障可重复。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from google.adk.agents import Agent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.base_events_summarizer import BaseEventsSummarizer
from google.adk.events import Event, EventActions
from google.adk.events.event_actions import EventCompaction
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field


def content(text: str, role="model") -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


@dataclass
class TextCollector:
    """只收指定 Agent 文本；最终聚合结果替换预览，不再次追加。"""

    author: str
    preview: str = ""
    final: str = ""
    partial_events: int = 0

    def accept(self, event: Event):
        if event.author != self.author or not event.content:
            return
        text = "".join(p.text or "" for p in event.content.parts or [] if not p.thought)
        if event.partial:
            self.preview += text
            self.partial_events += 1
        elif event.is_final_response():
            self.final = text

    @property
    def text(self):
        return self.final or self.preview


class DemoModel(BaseLlm):
    model: str = "offline-runtime"
    repeat_tool: bool = False
    calls: int = 0
    requests: list[str] = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        self.requests.append("\n".join(p.text or "" for c in llm_request.contents
                                       for p in c.parts or []))
        if self.repeat_tool:
            yield LlmResponse(content=types.Content(role="model", parts=[
                types.Part(function_call=types.FunctionCall(name="ping", args={}))]))
        else:
            if stream:
                for chunk in ["订单", "已签收"]:
                    yield LlmResponse(content=content(chunk), partial=True)
            yield LlmResponse(content=content("订单已签收"), partial=False)


class FixedSummary(BaseEventsSummarizer):
    """用已知事实验证压缩接线；实际摘要质量必须另用真实模型评估。"""

    async def maybe_summarize_events(self, *, events):
        if not events:
            return None
        return Event(author="user", invocation_id=Event.new_id(), actions=EventActions(
            compaction=EventCompaction(start_timestamp=events[0].timestamp,
                end_timestamp=events[-1].timestamp,
                compacted_content=content("摘要：订单 A100，用户偏好中文。"))))


async def run_once(runner, session_id, text, config=None):
    return [event async for event in runner.run_async(user_id="student",
        session_id=session_id, new_message=content(text, "user"), run_config=config)]


async def verify():
    sessions = InMemorySessionService()
    await sessions.create_session(app_name="runtime", user_id="student", session_id="stream")
    agent = Agent(name="answer", model=DemoModel())
    runner = Runner(agent=agent, app_name="runtime", session_service=sessions)
    events = await run_once(runner, "stream", "查询订单", RunConfig(streaming_mode=StreamingMode.SSE))
    collector = TextCollector("answer")
    for event in events:
        collector.accept(event)
    assert collector.preview == collector.final == collector.text == "订单已签收"
    assert collector.partial_events == 2
    naive = "".join(p.text or "" for e in events if e.content for p in e.content.parts or [])
    assert naive == "订单已签收订单已签收"  # 故意复现重复显示。
    collector.accept(Event(author="other", content=content("另一个 Agent 的输出")))
    assert collector.text == "订单已签收"
    print("PASS 流式：增量预览与最终结果分开处理，没有重复拼接")

    def ping() -> dict:
        """返回成功，用于演示持续工具循环。"""
        return {"ok": True}

    model = DemoModel(repeat_tool=True)
    looper = Agent(name="looper", model=model, tools=[ping])
    await sessions.create_session(app_name="runtime", user_id="student", session_id="budget")
    runner = Runner(agent=looper, app_name="runtime", session_service=sessions)
    # 本实验主动触发预算错误；只收敛这段预期 SDK 日志，异常仍须匹配。
    sdk_logger = logging.getLogger("google_adk")
    previous_level = sdk_logger.level
    sdk_logger.setLevel(logging.CRITICAL)
    try:
        await run_once(runner, "budget", "继续调用", RunConfig(max_llm_calls=2))
    except LlmCallsLimitExceededError:
        assert model.calls == 2
    else:
        raise AssertionError("预算应该中止无限工具循环")
    finally:
        sdk_logger.setLevel(previous_level)
    print("PASS 预算：两次模型调用后停止，不能把循环成功误当业务成功")

    model = DemoModel()
    app = App(name="compact", root_agent=Agent(name="answer", model=model),
        events_compaction_config=EventsCompactionConfig(compaction_interval=2,
            overlap_size=0, summarizer=FixedSummary()))
    await sessions.create_session(app_name="compact", user_id="student", session_id="history")
    runner = Runner(app=app, session_service=sessions)
    for text in ["订单是 A100，偏好中文", "继续查询", "请复述已知信息", "再确认一次"]:
        await run_once(runner, "history", text)
    session = await sessions.get_session(app_name="compact", user_id="student", session_id="history")
    assert any(event.actions.compaction for event in session.events)
    assert any("摘要：订单 A100" in request for request in model.requests)
    print("PASS 压缩：摘要事件存在，后续模型请求实际收到摘要；业务账本仍由工具读取")


if __name__ == "__main__":
    asyncio.run(verify())
