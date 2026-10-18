"""练习 5（工程）：用数据证明并发上限。

题目：批量 20 项，max_parallel_workers=3，记录峰值并发、总耗时和返回顺序；
再把上限改成 1 和 20 各跑一次。

验收：
- 三次运行的峰值分别不超过 3 / 1 / 20；
- 结果顺序始终等于输入顺序；
- 用三次的数据说明"批次上限不等于服务配额"。

本练习不调用模型：工作负载用 asyncio.sleep 模拟 I/O 等待，
这样才能把注意力放在"并发到底有没有发生"上，而不是模型抖动上。
"""

from __future__ import annotations

import asyncio
import json
import time

from google.adk import Context, Workflow
from google.adk.workflow import node

from _common import input_text, run, start

ITEM_COUNT = 20
SLEEP_SECONDS = 0.05

# 用一个可变字典记录"当前有几个在跑"和"历史峰值"
concurrency = {"active": 0, "peak": 0}


@node
async def inspect_topic(node_input: str) -> dict:
    concurrency["active"] += 1
    concurrency["peak"] = max(concurrency["peak"], concurrency["active"])
    try:
        # 模拟一次 I/O 等待。换成 CPU 密集的循环，这里的并发就不会发生了
        # —— 因为 asyncio 是单线程协作式调度，只让"等"的时间重叠。
        await asyncio.sleep(SLEEP_SECONDS)
        return {"topic": node_input, "characters": len(node_input)}
    finally:
        concurrency["active"] -= 1


async def run_batch(limit: int, topics: list[str]) -> dict:
    """用给定的并发上限跑一批，返回峰值、耗时和返回顺序。"""
    worker = node(inspect_topic, parallel_worker=True, max_parallel_workers=limit)

    @node(rerun_on_resume=True)
    async def batch_entry(ctx: Context, node_input):
        return await ctx.run_node(worker, json.loads(input_text(node_input)))

    batch = Workflow(name=f"batch_{limit}", edges=[("START", batch_entry)])

    concurrency.update(active=0, peak=0)
    started = time.perf_counter()
    result, *_ = await start(batch, topics)
    elapsed = time.perf_counter() - started

    return {
        "limit": limit,
        "peak": concurrency["peak"],
        "elapsed": elapsed,
        "order": [item["topic"] for item in result],
    }


async def main() -> None:
    topics = [f"主题{i:02d}" for i in range(ITEM_COUNT)]
    serial_estimate = ITEM_COUNT * SLEEP_SECONDS

    print(f"{ITEM_COUNT} 项，每项等待 {SLEEP_SECONDS}s（纯串行约需 {serial_estimate:.2f}s）\n")
    print(f"{'上限':<6}{'实测峰值':<10}{'耗时(s)':<10}{'顺序正确'}")
    print("-" * 40)

    runs = []
    for limit in (1, 3, 20):
        info = await run_batch(limit, topics)
        runs.append(info)
        order_ok = info["order"] == topics

        print(
            f"{limit:<6}{info['peak']:<10}{info['elapsed']:<10.2f}{order_ok}"
        )

        # --- 验收①：峰值不超过上限 ---
        assert info["peak"] <= limit, f"上限 {limit} 被突破：峰值 {info['peak']}"
        # --- 验收②：返回顺序始终等于输入顺序 ---
        assert order_ok, f"上限 {limit} 时顺序被打乱：{info['order']}"

    by_limit = {r["limit"]: r for r in runs}

    # 上限为 1 时，峰值必须是 1 —— 这是"串行"的对照组
    assert by_limit[1]["peak"] == 1, by_limit[1]
    # 上限为 3 时，并发确实发生了（峰值 2 或 3 都算发生）
    assert by_limit[3]["peak"] >= 2, by_limit[3]
    # 上限为 20 时，全部 20 项可以同时在跑
    assert by_limit[20]["peak"] == ITEM_COUNT, by_limit[20]

    print("\n✅ 练习 5 通过：峰值从未超过上限，返回顺序始终等于输入顺序")
    print(f"""
三点结论：

1. **上限是真的在起作用。** 上限为 1 时峰值恰好是 1，耗时接近纯串行的
   {serial_estimate:.2f}s；上限放宽后耗时明显下降 —— 这才叫"并发确实发生了"。

2. **只看耗时是不够的。** 耗时短可能只是机器快、或者等待时间短。
   真正能证明"并发发生过、且没超上限"的，是**在节点内部记录同时在跑的数量**。

3. **批次上限 ≠ 服务配额。** max_parallel_workers 只约束这一个批次的节点并发。
   如果流程里有多个批次、或者同一服务上跑着多个任务，请求会叠加。
   生产环境要在这个上限之外，再做一层**全局的**限流。
""")


if __name__ == "__main__":
    run(main, need_api_key=False)
