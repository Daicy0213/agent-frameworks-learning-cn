"""练习 3（进阶）：把 State 传值改成显式传值。

题目：第 5 章的写作流水线用的是 output_key + instruction 里的 {key} 插值。
把它改写成本章的 ctx.run_node() 返回值传值版本。

验收：
- 列出改造后"哪些数据不再需要进 State"；
- 说明还有哪一类数据仍然必须留在 State；
- 改造后流水线的模型调用次数不得增加。

改造前的写法（第 5 章，SequentialAgent）：
    SequentialAgent(sub_agents=[outliner, writer])
    每个 Agent 用 output_key 把结果写进 State，下一个 Agent 的 instruction 里写 {key}。
    → 所有中间结果都被塞进 Session State，只因为"传参只能走 State"。

改造后：中间结果走函数返回值，只有**跨步骤共享、且指令需要插值**的东西才留在 State。
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
    """只记录调用了哪个 Agent，不修改结果。"""
    model_responses.append(callback_context.agent_name)
    return None


outliner = Agent(
    name="outliner",
    model=deepseek(),
    mode="single_turn",
    instruction=(
        "根据输入 topic 列出三个写作要点。只输出 JSON："
        '{"points": ["要点1", "要点2", "要点3"]}。'
    ),
    after_model_callback=record_response,
)

writer = Agent(
    name="writer",
    # 这里演示"仍然必须留在 State"的那一类数据：
    # instruction 里的 {polish_style} 由 Session State 插值而来。
    instruction=(
        "根据 topic 和已经给出的写作要点，写一段中文短文。"
        "语气要求：{polish_style}。"
        '只输出 JSON：{"title": "标题", "body": "正文"}。'
    ),
    model=deepseek(),
    mode="single_turn",
    after_model_callback=record_response,
)


class Outline(BaseModel):
    points: list[str] = Field(min_length=3, max_length=3)


class Draft(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


@node(rerun_on_resume=True)
async def writing_pipeline(ctx: Context, node_input: dict) -> dict:
    # 这一类数据仍然要进 State：instruction 插值需要它。
    # 写在这里（而不是塞进每一步的参数里），是因为它属于"整条流程的共享配置"。
    ctx.state["polish_style"] = node_input["polish_style"]

    # ① 显式传值：上一步的返回值直接当下一步的输入，完全不经过 State
    outline = Outline.model_validate_json(
        await ctx.run_node(outliner, f"主题：{node_input['topic']}")
    )
    draft = Draft.model_validate_json(
        await ctx.run_node(
            writer, f"主题：{node_input['topic']}\n写作要点：{outline.points}"
        )
    )
    return {"outline": outline.model_dump(), "draft": draft.model_dump()}


@node(rerun_on_resume=True)
async def pipeline_entry(ctx: Context, node_input):
    # 入口拿到的是 types.Content，先归一成字符串再解析
    return await ctx.run_node(writing_pipeline, json.loads(input_text(node_input)))


pipeline = Workflow(name="pipeline", edges=[("START", pipeline_entry)])


async def main() -> None:
    calls_before = len(model_responses)
    result, events, runner, session_id = await start(
        pipeline,
        {
            "topic": "程序员为什么需要学习写作",
            "polish_style": "简洁、面向初学者",
        },
    )
    pipeline_calls = len(model_responses) - calls_before

    # --- 验收③：模型调用次数没有增加（改造前也是 2 次） ---
    assert pipeline_calls == 2, f"流水线应该只调用 2 次模型，实际 {pipeline_calls} 次"
    assert model_responses[calls_before:] == ["outliner", "writer"]
    assert len(result["outline"]["points"]) == 3, result

    session = await runner.session_service.get_session(
        app_name="adk_practice", user_id="student", session_id=session_id
    )
    state_keys = sorted(session.state)
    print("流水线模型调用次数：", pipeline_calls)
    print("最终 State 的键：", state_keys)
    print("生成的文章：", json.dumps(result["draft"], ensure_ascii=False))

    # --- 验收①：中间结果不再进 State ---
    # 改造前，outline / draft 这些中间结果会以 output_key 的形式留在 State 里。
    # 改造后它们只是局部变量和函数参数，State 里不该再出现同名键。
    for leaked in ("outline", "draft", "points"):
        assert leaked not in state_keys, f"{leaked!r} 不应该再进 State：{state_keys}"

    # --- 验收②：polish_style 仍然必须留在 State，因为它被 instruction 插值 ---
    assert "polish_style" in state_keys, state_keys

    print("\n✅ 练习 3 通过：中间结果不再经过 State，模型调用次数没有增加")
    print("""
小结（题目要求的"哪些不再需要 / 哪些仍然必须"）：

不再需要进 State：
  - 纯中间结果：大纲、初稿、评分……它们只有一个消费者，就是下一步；
  - 只要"上一步的返回值"能直接当"下一步的参数"，就没有理由绕道 State。

仍然必须留在 State：
  - 需要被 instruction 插值（{key}）读取的值，例如上面的 polish_style；
  - 需要被工具或回调读取/写入的共享数据；
  - 需要跨步骤保留、且不由单一路径传递的流程状态
    （例如第 9 章按条目分开的 article:<id> 摘要）。

一句话：**State 是给"多个消费者"用的；只有一个消费者的数据，用返回值就够。**
""")


if __name__ == "__main__":
    run(main)
