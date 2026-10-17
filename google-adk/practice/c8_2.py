"""练习 2（基础）：读懂 `output_for` 与根输出。

题目：单独跑一次第 2 节的小工作流，逐条打印每个事件的
node_info.path、node_info.output_for 和 output。

验收：用自己的话解释两件事——
① 为什么子节点也会产生"最终事件"，所以不能只用 is_final_response() 取流程结果；
② output_for 里"不含 /"的路径为什么指向根 Workflow。

本文件把"用自己的话解释"落成了断言 + 打印，答案在文末注释里。
"""

from __future__ import annotations

from google.adk import Context, Workflow
from google.adk.workflow import node

from _common import input_text, run, start


@node
def normalize_topic(node_input: str) -> str:
    return node_input.strip().removeprefix("主题：")


@node(rerun_on_resume=True)
async def hello_entry(ctx: Context, node_input):
    topic = await ctx.run_node(normalize_topic, input_text(node_input))
    return f"学习主题：{topic}"


hello = Workflow(name="hello", edges=[("START", hello_entry)])


async def main() -> None:
    result, events, *_ = await start(hello, "  主题：动态工作流  ")
    assert result == "学习主题：动态工作流", result

    print("完整事件流：\n")
    rows = []
    for event in events:
        if not event.node_info:
            continue
        rows.append(
            {
                "path": event.node_info.path,
                "output_for": event.node_info.output_for,
                "output": event.output,
                "is_final_response": event.is_final_response(),
            }
        )
        print(
            f"  path={event.node_info.path!r}\n"
            f"    output_for       = {event.node_info.output_for}\n"
            f"    output           = {event.output!r}\n"
            f"    is_final_response= {event.is_final_response()}"
        )

    # --- 验收 ①：不止一个事件自称"最终响应" ---
    finals = [r for r in rows if r["is_final_response"]]
    assert len(finals) >= 2, f"预期多个事件都是最终响应，实际 {finals}"
    print(f"\n共有 {len(finals)} 个事件 is_final_response() 为 True —— 所以它不能用来取流程结果")

    # --- 验收 ②：看 output_for 里有没有"不含 /"的路径 ---
    # 注意：path 是从根开始的**完整位置**，所以根输出的提供者 path 是
    # "hello@1/hello_entry@1"，而不是光秃秃的 "hello_entry"。
    # 真正用来判断"这是根"的，是 output_for 里那条不带 "/" 的 "hello@1"。
    root_rows = [r for r in rows if any("/" not in p for p in r["output_for"] or [])]
    child_rows = [r for r in rows if not any("/" not in p for p in r["output_for"] or [])]
    assert len(root_rows) == 1, root_rows
    assert "hello@1" in root_rows[0]["output_for"], root_rows
    assert root_rows[0]["output"] == result, (root_rows[0]["output"], result)
    assert child_rows, "子节点也应该产生输出事件"
    assert all("/" in p for r in child_rows for p in r["output_for"]), child_rows

    print("根输出的提供者：", root_rows[0]["path"])
    print("  output_for =", root_rows[0]["output_for"], "→ 其中 hello@1 没有 '/'")
    print("子节点归属：", [(r["path"], r["output_for"]) for r in child_rows])
    print("\n✅ 练习 2 通过")


if __name__ == "__main__":
    run(main, need_api_key=False)

# ---------------------------------------------------------------------------
# 参考答案（先自己写，再看这里）
#
# ① 为什么子节点也会产生"最终事件"？
#    因为 `is_final_response()` 问的是"这一轮里，*这个 Agent* 是不是给出了最终答复"，
#    而不是"整条流程结束了没有"。normalize_topic 和 hello_entry 都是独立节点，
#    各自都会"说完自己的话"，于是各自都有一个最终事件。
#    要拿整条流程的结果，必须看归属：output_for 指回根 Workflow 的那条才是。
#
# ② 为什么"不含 /"的路径指向根 Workflow？
#    output_for 是一个"这个输出算谁的"的清单，用路径表示层级，层级之间用 "/" 分隔。
#    根 Workflow 就在最顶层，它的路径里没有上级，自然也没有 "/"。
#    实测下来（本文件跑出来的真实结果）：
#      normalize_topic 的 output_for = ['hello@1/hello_entry@1/normalize_topic@1']
#      hello_entry     的 output_for = ['hello@1/hello_entry@1', 'hello@1']
#    第二条多出来的 'hello@1' 就是根 —— 而 'hello@1' 恰好等于工作流的名字加上调用序号。
#    所以判断规则很简单：**output_for 里没有 "/" 的那条，就是根。**
#
#    顺带记住 path 和 output_for 的分工：
#      path       回答"这个事件发生在哪儿"（从根开始的完整位置）
#      output_for 回答"这份输出算是谁的"（可能同时属于多个层级）
# ---------------------------------------------------------------------------
