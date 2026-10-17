"""练习 4（进阶）：修订预算的三条路径。

题目：扩展第 8 章第 4 节的检查，覆盖三条路径——一次通过、修改一次后通过、预算耗尽。

验收：
- 三条路径都断言 stop_reason 与 revisions 的具体取值；
- 预算耗尽必须返回失败，不得把最后一稿标为成功；
- 哪条路径调用了模型、调用了几次，也要断言出来。

设计要点：把"业务规则检查"（纯函数、确定性）和"模型修改"（有抖动）分开。
这样三条路径里只有真正需要修改的那条才会花钱。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from google.adk import Context, Workflow
from google.adk.agents import Agent
from google.adk.workflow import node

from _common import deepseek, input_text, run, start

model_responses: list[str] = []


def record_response(callback_context, llm_response):
    model_responses.append(callback_context.agent_name)
    return None


polisher = Agent(
    name="polisher",
    model=deepseek(),
    mode="single_turn",
    instruction=(
        "按 findings 修复 draft，只改被指出的问题，不要破坏已经合格的部分。"
        "标题不能为空，正文 60～120 个字符，必须包含“例如”。"
        '只输出 JSON：{"title": "标题", "body": "正文"}。'
    ),
    after_model_callback=record_response,
)


class Draft(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


class WritingRequest(BaseModel):
    topic: str = Field(min_length=1)
    required_terms: list[str] = Field(default_factory=list)


@node
def review_article(node_input: dict) -> dict:
    """纯业务规则检查：确定性、不花钱、不抛异常。"""
    request = WritingRequest.model_validate(node_input["request"])
    draft = Draft.model_validate(node_input["draft"])
    findings = []
    if not draft.title.strip():
        findings.append("标题不能为空白")
    if not 60 <= len(draft.body) <= 120:
        findings.append(f"正文 {len(draft.body)} 字，要求 60～120 字")
    for term in dict.fromkeys(["例如", *request.required_terms]):
        if term not in draft.body:
            findings.append(f"正文必须包含：{term}")
    return {"passed": not findings, "findings": findings}


@node(rerun_on_resume=True)
async def refine_article(ctx: Context, node_input: dict) -> dict:
    request, draft = node_input["request"], node_input["draft"]
    budget = node_input["max_revisions"]
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("max_revisions 必须是非负整数")

    for revision in range(budget + 1):
        review = await ctx.run_node(
            review_article, {"request": request, "draft": draft}
        )
        if review["passed"] or revision == budget:
            return {
                "draft": draft,
                **review,
                "revisions": revision,
                "stop_reason": "passed" if review["passed"] else "revision_limit",
            }
        # 只有"不通过且还有预算"时才调用模型
        draft = Draft.model_validate_json(
            await ctx.run_node(
                polisher,
                {
                    "request": request,
                    "draft": draft,
                    "findings": review["findings"],
                },
            )
        ).model_dump()
    raise AssertionError("不可达：循环一定会在某次 return")


@node(rerun_on_resume=True)
async def refinement_entry(ctx: Context, node_input):
    return await ctx.run_node(refine_article, json.loads(input_text(node_input)))


refinement = Workflow(name="refinement", edges=[("START", refinement_entry)])

VALID_DRAFT = {
    "title": "程序员的写作练习",
    "body": (
        "写作可以帮助程序员梳理需求、说明设计理由并减少沟通误差。例如，"
        "在接口变更前写清输入、输出与兼容范围，团队就能及时发现遗漏，"
        "也方便后来维护的人理解当时的选择。"
    ),
}

CASES = [
    # (说明, draft, 预算, 期望 passed, 期望 stop_reason, 期望 revisions, 期望模型调用次数)
    ("一次通过", VALID_DRAFT, 0, True, "passed", 0, 0),
    ("预算耗尽", {"title": "初稿", "body": "太短"}, 0, False, "revision_limit", 0, 0),
    (
        "修改一次后通过",
        {**VALID_DRAFT, "body": VALID_DRAFT["body"].replace("例如", "比如")},
        1,
        True,
        "passed",
        1,
        1,
    ),
]


async def main() -> None:
    request = {"topic": "程序员为什么需要学习写作", "required_terms": ["例如"]}
    print(f"{'路径':<16}{'passed':<9}{'stop_reason':<16}{'revisions':<11}{'模型调用'}")
    print("-" * 62)

    for label, draft, budget, want_passed, want_reason, want_rev, want_calls in CASES:
        before = len(model_responses)
        result, *_ = await start(
            refinement,
            {"request": request, "draft": draft, "max_revisions": budget},
        )
        calls = len(model_responses) - before

        # 先打印再断言，失败时也能看到实际值
        print(
            f"{label:<16}{str(result['passed']):<9}{result['stop_reason']:<16}"
            f"{result['revisions']:<11}{calls}"
        )

        assert result["passed"] is want_passed, (label, result)
        assert result["stop_reason"] == want_reason, (label, result)
        assert result["revisions"] == want_rev, (label, result)
        assert calls == want_calls, f"{label}: 预期 {want_calls} 次模型调用，实际 {calls}"

    print("\n✅ 练习 4 通过：三条路径的 stop_reason / revisions / 模型调用次数都符合预期")
    print("""
两个容易写错的点：

1. **"预算耗尽"必须返回失败。** 很诱人的做法是"那就用最后一稿吧，反正也改过了"，
   然后把 passed 置为 True。这等于告诉调用方"任务成功了"，而实际上规则并没有通过。
   正确做法是如实返回 revision_limit，让上层决定要不要接受。

2. **初次检查不占预算。** max_revisions=1 表示"最多修改一次"，
   所以循环跑的是 budget+1 次（第 1 次是检查，不是修改）。
   如果把预算理解成"总检查次数"，边界就会差一。
""")


if __name__ == "__main__":
    run(main)
