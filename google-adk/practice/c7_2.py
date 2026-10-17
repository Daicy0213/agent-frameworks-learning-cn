"""第 7 章练习 2：可信身份驱动 callback，工具本体再次校验。"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from capstone.agent import build_agent
from capstone.store import ALICE, MANAGER, VIEWER, RefundStore


def policy_for(principal):
    """身份绑定在宿主闭包中，不从模型的 args 中获取。"""
    def before_tool(tool, args, tool_context):
        if tool.name == "create_refund" and principal.role != "agent":
            return {"ok": False, "error": "ROLE_DENIED"}
        return None
    return before_tool


async def main():
    with tempfile.TemporaryDirectory() as directory:
        store = RefundStore(Path(directory) / "refunds.sqlite")
        approval = store.issue_approval(MANAGER, ALICE, "A100", 3000)
        scenario = dict(order_id="A100", amount_cents=3000, approval_id=approval, request_key="k")
        original_refund = store.refund
        business_calls = []
        def tracked_refund(*args, **kwargs):
            business_calls.append((args, kwargs))
            return original_refund(*args, **kwargs)
        store.refund = tracked_refund
        agent = build_agent(store, VIEWER)
        agent.before_tool_callback = policy_for(VIEWER)
        sessions = InMemorySessionService()
        await sessions.create_session(app_name="policy", user_id="student", session_id="s")
        runner = Runner(agent=agent, app_name="policy", session_service=sessions)
        events = [event async for event in runner.run_async(user_id="student", session_id="s",
            new_message=types.Content(role="user", parts=[types.Part(text=json.dumps(scenario))]))]
        results = [r.response for event in events for r in event.get_function_responses()]
        assert results[-1]["error"] == "ROLE_DENIED" and store.ledger() == []
        assert business_calls == [], "callback 拒绝时不能进入工具本体"
        # 即使绕过 callback，工具的业务边界仍拒绝相同身份。
        assert store.refund(VIEWER, **scenario)["error"] == "ROLE_DENIED"
        assert store.refund(ALICE, **scenario)["ok"]
        assert store.refund(ALICE, **scenario)["duplicate"]
        assert len(store.ledger()) == 1
    print("PASS 真实 Runner 短路、工具本体复核、授权后幂等")


if __name__ == "__main__":
    asyncio.run(main())
