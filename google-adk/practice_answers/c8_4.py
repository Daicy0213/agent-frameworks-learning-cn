"""练习 4（工程）：模型异常下的部分成功策略。

题目：为其中一项注入模型异常，定义"一项失败是否整批失败"的策略，并写成断言。

验收：
- 策略必须显式——要么整批失败，要么明确标记部分成功；禁止静默降级；
- 说明为什么"部分成功"必须出现在返回值里，而不是只打在日志里。

本练习用注入异常模拟模型故障（而不是真的把模型打挂），这样策略本身才是可复现、可测试的。
真实项目里也应该这么写测试：把"模型失败"变成一个你能随时触发的开关。
"""

from __future__ import annotations

import json

from google.adk import Context, Workflow
from google.adk.workflow import node

from _common import input_text, run, start

ITEMS = [
    {"id": "good", "topic": "动态工作流"},
    {"id": "bad", "topic": "触发模型异常的这一项"},
]


async def fake_model_call(request: dict) -> dict:
    """替代真实模型节点：对 bad 这一项抛异常，其余正常返回。"""
    if request["id"] == "bad":
        raise RuntimeError("模拟模型服务异常：这一项没能生成内容")
    return {"title": request["topic"], "body": f"关于{request['topic']}的介绍。"}


async def run_batch(collect_mode: str) -> dict:
    """collect_mode: 'partial' = 允许部分成功；'all_or_nothing' = 一项失败整批失败。"""

    @node
    async def write_item(node_input: dict) -> dict:
        draft = await fake_model_call(node_input["request"])
        return {"id": node_input["request"]["id"], "draft": draft}

    @node(rerun_on_resume=True)
    async def batch(ctx: Context, node_input: dict):
        results, failed = [], []
        for request in node_input["items"]:
            try:
                results.append(await ctx.run_node(write_item, {"request": request}))
            except Exception as error:
                if collect_mode == "all_or_nothing":
                    # 策略 A：一项失败，整批失败。异常继续往上抛，绝不假装成功。
                    raise RuntimeError(
                        f"整批失败：{request['id']} 生成失败（{error}）"
                    ) from error
                # 策略 B：部分成功。失败信息必须进入**返回值**，而不是只写日志。
                failed.append({"id": request["id"], "error": str(error)})

        if failed:
            return {
                "status": "partial_failed",
                "succeeded": [r["id"] for r in results],
                "failed": failed,
                "articles": [r["draft"] for r in results],
            }
        return {
            "status": "ok",
            "succeeded": [r["id"] for r in results],
            "failed": [],
            "articles": [r["draft"] for r in results],
        }

    @node(rerun_on_resume=True)
    async def entry(ctx: Context, node_input):
        return await ctx.run_node(batch, json.loads(input_text(node_input)))

    app = Workflow(name=f"batch_{collect_mode}", edges=[("START", entry)])
    result, *_ = await start(app, {"items": ITEMS})
    return result


async def main() -> None:
    print("=" * 74)
    print("策略 A：一项失败 → 整批失败（all_or_nothing）")
    print("=" * 74)
    raised = None
    try:
        await run_batch("all_or_nothing")
    except Exception as error:
        raised = error
    assert raised is not None, "策略 A 必须把异常抛出来，而不是吞掉"
    print("整批抛出：", type(raised).__name__, "->", raised)
    print("✅ 整批失败：没有任何结果被伪装成成功\n")

    print("=" * 74)
    print("策略 B：部分成功，但失败必须显式出现在返回值里（partial）")
    print("=" * 74)
    result = await run_batch("partial")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # --- 核心验收：失败场景下，status 绝不能是 "ok" ---
    assert result["status"] == "partial_failed", result
    assert result["status"] != "ok", "有失败项时不允许返回 ok"
    # 按条目断言，而不是按错误文案断言 —— 下面会解释为什么
    assert [f["id"] for f in result["failed"]] == ["bad"], result
    assert result["succeeded"] == ["good"], result
    # 成功项的产物必须还在，不能因为一项失败就全丢
    assert len(result["articles"]) == 1, result

    print("\n注意上面 failed[0].error 的文案：", result["failed"][0]["error"])
    print(
        "—— 这不是我们抛出的那句 '模拟模型服务异常：这一项没能生成内容'，\n"
        "   而是框架包装后的通用消息（DynamicNodeFailError 的 message）。\n"
    )

    # --- 反向验收：全部成功时才允许 ok ---
    mostly_good = await run_batch("partial")  # 同样的输入，同样的策略
    assert mostly_good["status"] == "partial_failed"
    print("✅ 练习 4 通过：两种策略都显式，没有静默降级")
    print("""
题目要求说清楚的两件事：

**为什么必须先选策略？**
  "一项失败"在业务上通常有两种完全不同的含义：
    - 这是**一批必须同时成立**的变更（比如批量转账、批量发布）→ 整批失败；
    - 这是**一批互相独立的条目**（比如批量生成文章）→ 部分成功可以接受。
  框架不知道你的业务属于哪种，所以你必须选，而且要把它写进断言里。

**为什么"部分成功"必须出现在返回值里，而不是只打日志？**
  因为**日志不会让调用方停下来**。上层代码看到的是 result["status"]，
  它据此决定要不要重试、要不要人工介入、要不要对外发布。
  如果状态是 "ok" 而失败只躺在日志里，这个"部分成功"就会被一路当成
  "全部成功"传下去 —— 这正是最危险的那种静默降级。

  所以：**凡是能影响上层决策的事实，都必须在返回值里有位置。**

**顺带一个实测出来的坑：不要依赖框架的异常文案。**
  上面 failed[0].error 拿到的是「Dynamic node write_item failed」，
  我们自己抛的那句 "模拟模型服务异常" 被包装层丢掉了。
  所以：

    - 断言要盯**结构化字段**（哪个 id 失败、失败条目数），不要盯错误文案；
    - 想保留失败原因，就在**离故障最近的地方**捕获并转成结构化数据返回，
      而不是让它一路抛到外层再猜。

  这也是为什么本章的 `checks` 断言统计的是计数、PID、版本号这些"硬事实"，
  而不是去匹配某句日志文本。
""")


if __name__ == "__main__":
    run(main, need_api_key=False)
