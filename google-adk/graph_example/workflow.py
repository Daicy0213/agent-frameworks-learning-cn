"""用同一售后请求观察顺序、条件与汇合；不调用模型或外部服务。

从 google-adk 目录运行：python -m graph_example.workflow
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from google.adk import Context, Workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import JoinNode, node
from google.genai import types


@node
def read_request(node_input) -> dict:
    """Runner 接收 Content；业务节点接收解析后的字典。"""
    text = "".join(part.text or "" for part in node_input.parts or [])
    request = json.loads(text)
    amount = request.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError("amount 必须是正整数（单位：分）")
    return {"order_id": request["order_id"], "amount": amount}


@node
def summarize(node_input: dict) -> dict:
    return {**node_input, "summary": f"订单 {node_input['order_id']} 申请退款"}


@node
def choose_route(ctx: Context, node_input: dict) -> dict:
    ctx.route = "manual" if node_input["amount"] > 10000 else "automatic"
    return node_input


@node
def manual_review(node_input: dict) -> dict:
    return {**node_input, "status": "needs_review"}


@node
def automatic_review(node_input: dict) -> dict:
    # 只作业务分类，不执行真实退款。
    return {**node_input, "status": "eligible_for_next_check"}


@node
def check_order(node_input: dict) -> dict:
    return {"order_id": node_input["order_id"], "exists": node_input["order_id"] == "A100"}


@node
def check_amount(node_input: dict) -> dict:
    return {"amount": node_input["amount"], "within_limit": node_input["amount"] <= 10000}


@node
def combine_checks(node_input: dict) -> dict:
    # JoinNode 的输入按前驱节点名称组织，不靠完成先后猜测来源。
    order = node_input["check_order"]
    amount = node_input["check_amount"]
    return {
        "order_id": order["order_id"],
        "amount": amount["amount"],
        "passed": order["exists"] and amount["within_limit"],
        "sources": sorted(node_input),
    }


def build_sequence() -> Workflow:
    return Workflow(name="sequence", edges=[("START", read_request, summarize)])


def build_branch() -> Workflow:
    return Workflow(
        name="branch",
        edges=[("START", read_request, choose_route, {
            "manual": manual_review,
            "automatic": automatic_review,
        })],
    )


def build_fanout() -> Workflow:
    joined = JoinNode(name="both_checks")
    return Workflow(
        name="fanout",
        edges=[("START", read_request, (check_order, check_amount), joined, combine_checks)],
        max_concurrency=2,
    )


async def run_graph(workflow: Workflow, request: dict) -> tuple[dict, list]:
    service = InMemorySessionService()
    app, user, sid = "graph_lesson", "student", uuid4().hex
    await service.create_session(app_name=app, user_id=user, session_id=sid)
    runner = Runner(agent=workflow, app_name=app, session_service=service)
    message = types.Content(
        role="user", parts=[types.Part(text=json.dumps(request, ensure_ascii=False))]
    )
    output, events = None, []
    async for event in runner.run_async(user_id=user, session_id=sid, new_message=message):
        events.append(event)
        if event.node_info and event.output is not None:
            if any("/" not in path for path in event.node_info.output_for or []):
                output = event.output
    if not isinstance(output, dict):
        raise AssertionError(f"没有取得根工作流结果：{output!r}")
    return output, events


async def verify() -> None:
    small = {"order_id": "A100", "amount": 5000}
    result, _ = await run_graph(build_sequence(), small)
    assert result["summary"] == "订单 A100 申请退款"
    result, events = await run_graph(build_branch(), small)
    assert result["status"] == "eligible_for_next_check"
    paths = [event.node_info.path for event in events if event.node_info]
    assert not any("manual_review@" in path for path in paths)
    result, _ = await run_graph(build_branch(), {**small, "amount": 20000})
    assert result["status"] == "needs_review"
    for request, expected in [(small, True), ({**small, "order_id": "missing"}, False)]:
        result, _ = await run_graph(build_fanout(), request)
        assert result["passed"] is expected
        assert result["sources"] == ["check_amount", "check_order"]
    print("✅ 声明式顺序、条件两条路径、并行汇合与反例均通过（0 次模型调用）")


if __name__ == "__main__":
    asyncio.run(verify())
