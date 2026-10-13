"""练习 1（基础）：给最小骨架加一个参数。

题目：让 `hello` 工作流接收 {"topic": ..., "audience": ...}，
在 `hello_entry` 里解包后传给 `normalize_request`，最后返回一个包含两个字段的字典。

验收：
- 断言根输出里同时含有主题和读者；
- 打印一次运行中所有事件的 node_info.path 与 node_info.output_for。
"""

from __future__ import annotations

import json

from google.adk import Context, Workflow
from google.adk.workflow import node

from _common import input_text, run, start


@node
def normalize_request(node_input: str) -> dict:
    """清洗入口参数。node_input 是上一步传来的字符串（入口是 Content，已用 input_text 归一）。"""
    request = json.loads(node_input) if isinstance(node_input, str) else node_input
    topic = str(request["topic"]).strip().removeprefix("主题：")
    audience = str(request["audience"]).strip()
    if not topic or not audience:
        raise ValueError("topic 和 audience 都不能是空白")
    return {"topic": topic, "audience": audience}


@node(rerun_on_resume=True)
async def hello_entry(ctx: Context, node_input):
    # 注意这里：入口拿到的是 types.Content，所以先 input_text 再往下传。
    # 这正是第 7 章反复强调的"返回类型不要混为一谈"。
    request = await ctx.run_node(normalize_request, input_text(node_input))
    return {
        "greeting": f"写给{request['audience']}：{request['topic']}",
        **request,
    }


hello = Workflow(name="hello", edges=[("START", hello_entry)])


async def main() -> None:
    result, events, *_ = await start(
        hello, {"topic": "  主题：动态工作流  ", "audience": "初学者"}
    )

    # --- 验收 1：根输出里同时含有主题和读者 ---
    assert result["topic"] == "动态工作流", result
    assert result["audience"] == "初学者", result
    assert result["greeting"] == "写给初学者：动态工作流", result

    print("根输出：", json.dumps(result, ensure_ascii=False))

    # --- 验收 2：打印所有事件的路径与归属 ---
    print("\n事件归属（path → output_for → output）：")
    for event in events:
        if event.node_info and event.output is not None:
            print(
                f"  {event.node_info.path}  →  {event.node_info.output_for}"
                f"  →  {event.output}"
            )

    # 关键观察：判断"谁是根输出"要看 output_for，而不是看 path。
    #   - normalize_request 的 output_for 只有它自己：['hello@1/hello_entry@1/normalize_request@1']
    #   - hello_entry 的 output_for 多出一条 'hello@1' —— 没有 "/"，那就是根 Workflow
    # 所以规则是：**output_for 里出现不带 "/" 的路径，这个事件才承载整条流程的结果。**
    # 注意 path 是"从根开始的完整位置"，所以它是 hello@1/hello_entry@1，而不是光秃秃的 hello_entry。
    root_events = [
        event
        for event in events
        if event.node_info
        and event.output is not None
        and any("/" not in path for path in event.node_info.output_for or [])
    ]
    assert len(root_events) == 1, [e.node_info.path for e in root_events]
    assert "hello@1" in root_events[0].node_info.output_for, root_events[0].node_info.output_for
    assert root_events[0].output == result, (root_events[0].output, result)

    print("\n根输出的提供者：", root_events[0].node_info.path)
    print("它的 output_for：", root_events[0].node_info.output_for)
    print("→ 其中的 'hello@1' 没有 '/'，所以它是根 Workflow")

    print("\n✅ 练习 1 通过：根输出归属正确，子节点事件没有冒充整条流程的结果")


if __name__ == "__main__":
    run(main, need_api_key=False)
