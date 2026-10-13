"""练习 1（基础）：两步人工确认。

题目：在 RequestInput 之前插入一个"预审"节点，只有预审通过才发起人工确认。

验收：
- 断言拒绝路径不产生任何 Artifact；
- 断言预审节点的执行计数在恢复之后仍然是 1（它是已完成子节点，应该走回放）。

本练习不调用模型：候选稿由本地节点生成，这样三条分支都可复现。
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from google.adk import Context, Workflow
from google.adk.artifacts import InMemoryArtifactService
from google.adk.events import RequestInput
from google.adk.workflow import node
from google.genai import types

from _common import APP, USER, collect, input_text, run, start


class ApprovalDecision(BaseModel):
    approved: bool = Field(strict=True)


class PrecheckVerdict(BaseModel):
    ok: bool = Field(strict=True)
    reason: str = ""


counts = Counter()


@node
def precheck_candidate(node_input: str) -> dict:
    """预审：只有规则能接受的候选稿才值得占用人工时间。"""
    counts["precheck"] += 1
    topic = node_input.strip()
    if not topic:
        return {"ok": False, "reason": "主题为空，直接退回，不打扰人工"}
    return {"ok": True, "reason": "规则初筛通过"}


@node
def prepare_candidate(node_input: dict) -> dict:
    counts["prepare"] += 1
    return {
        "title": node_input["topic"],
        "body": "候选稿已经生成，等待人工审核。",
    }


@node(rerun_on_resume=False)
def ask_approval(node_input: dict):
    return RequestInput(
        message="是否接受候选稿？",
        payload=node_input,
        response_schema=ApprovalDecision,
    )


@node
async def save_candidate(ctx: Context, node_input: dict) -> dict:
    counts["archive"] += 1
    version = await ctx.save_artifact(
        "candidate.md", types.Part.from_text(text=node_input["body"])
    )
    return {"status": "archived", "version": version}


@node(rerun_on_resume=True)
async def approval_workflow(ctx: Context, node_input):
    counts["parent"] += 1
    text = input_text(node_input)

    # 第一步：预审。不通过就直接结束，连人工确认都不发起。
    verdict = PrecheckVerdict.model_validate(
        await ctx.run_node(precheck_candidate, text)
    )
    if not verdict.ok:
        return {"status": "blocked_by_precheck", "reason": verdict.reason}

    # 第二步：生成候选稿
    draft = await ctx.run_node(prepare_candidate, {"topic": text})

    # 第三步：人工确认（会暂停）
    reply = await ctx.run_node(ask_approval, draft)
    if not ApprovalDecision.model_validate(reply).approved:
        return {"status": "rejected"}

    # 第四步：只有通过才归档
    return await ctx.run_node(save_candidate, draft)


approval_app = Workflow(name="approval_app", edges=[("START", approval_workflow)])


def pending_input(events):
    calls = [
        (event.invocation_id, part.function_call)
        for event in events
        for part in ((event.content.parts or []) if event.content else [])
        if part.function_call and part.function_call.name == "adk_request_input"
    ]
    if len(calls) != 1:
        raise ValueError(f"本练习需要恰好一个确认请求，实际是 {len(calls)}")
    return calls[0]


async def answer(runner, session_id, events, approved):
    invocation_id, call = pending_input(events)
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=call.id,
                    name=call.name,
                    response={"approved": approved},
                )
            )
        ],
    )
    return await collect(runner, session_id, message, invocation_id=invocation_id)


async def scenario(topic: str, decision: bool | None):
    """跑一条分支。decision=None 表示预期在预审就被拦下、根本不会暂停。"""
    counts.clear()
    artifacts = InMemoryArtifactService()
    paused, events, runner, session_id = await start(
        approval_app, topic, artifact_service=artifacts
    )

    if decision is None:
        # 预审拦截：流程直接给出结果，没有暂停，也就没有待处理请求
        assert paused is not None, "预审不通过时不应该暂停"
        assert paused["status"] == "blocked_by_precheck", paused
        assert counts["precheck"] == 1, counts
        assert counts["parent"] == 1, counts
        assert counts["prepare"] == 0, counts
        return paused, counts.copy(), None

    # 有预审通过 → 应该暂停在人工确认处
    assert paused is None, "等待人工确认时根输出应为 None"
    assert counts == {"parent": 1, "precheck": 1, "prepare": 1}, counts

    result, _ = await answer(runner, session_id, events, decision)

    saved = await artifacts.load_artifact(
        app_name=APP,
        user_id=USER,
        session_id=session_id,
        filename="candidate.md",
    )
    return result, counts.copy(), saved


async def main() -> None:
    print(f"{'分支':<18}{'status':<22}{'precheck':<10}{'prepare':<9}{'archive':<9}{'Artifact'}")
    print("-" * 78)

    # --- 分支 A：预审拦截 ---
    blocked, c_blocked, art_blocked = await scenario("   ", None)
    assert art_blocked is None
    print(f"{'预审拦截':<18}{blocked['status']:<22}{c_blocked['precheck']:<10}"
          f"{c_blocked['prepare']:<9}{c_blocked.get('archive', 0):<9}{'无'}")

    # --- 分支 B：预审通过，人工拒绝 ---
    rejected, c_rejected, art_rejected = await scenario("工作流介绍", False)
    assert rejected["status"] == "rejected", rejected
    assert art_rejected is None, "拒绝路径绝不能产生 Artifact"
    assert c_rejected["archive"] == 0, c_rejected
    print(f"{'人工拒绝':<18}{rejected['status']:<22}{c_rejected['precheck']:<10}"
          f"{c_rejected['prepare']:<9}{c_rejected['archive']:<9}{'无'}")

    # --- 分支 C：预审通过，人工接受 ---
    accepted, c_accepted, art_accepted = await scenario("工作流介绍", True)
    assert accepted["status"] == "archived", accepted
    assert art_accepted is not None and art_accepted.text, "接受路径必须产生 Artifact"
    print(f"{'人工接受':<18}{accepted['status']:<22}{c_accepted['precheck']:<10}"
          f"{c_accepted['prepare']:<9}{c_accepted['archive']:<9}{'1 个版本'}")

    # --- 最关键的验收：恢复后预审节点不重跑 ---
    # 父节点 parent 从 1 变成 2（重入了），但 precheck 和 prepare 都还是 1（回放）。
    assert c_rejected["parent"] == 2, c_rejected
    assert c_rejected["precheck"] == 1, c_rejected
    assert c_rejected["prepare"] == 1, c_rejected

    print("\n✅ 练习 1 通过：三条分支行为正确，恢复后预审节点没有重新执行")
    print(f"""
读计数：人工拒绝分支的最终计数是 {dict(c_rejected)}

  parent=2   → 恢复时父函数重新进入了一次（重入）
  precheck=1 → 预审节点没有重跑，用的是 checkpoint 里的旧结果（回放）
  prepare=1  → 候选稿也没有重新生成
  archive=0  → 拒绝路径根本没有走到归档

**把预审放在 RequestInput 之前**的实际价值：不合格的输入在花掉"人工时间"之前就被挡住了。
人工确认是很贵的资源，规则能拦的就不该让人来拦。
""")


if __name__ == "__main__":
    run(main, need_api_key=False)
