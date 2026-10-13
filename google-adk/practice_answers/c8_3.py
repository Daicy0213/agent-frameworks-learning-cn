"""练习 3（进阶）：数出框架的默认重试次数。

题目：写一个"每次必失败"的节点，只写 RetryConfig() 而不写 max_attempts，
统计 ctx.attempt_count。

验收：
- 打印实际尝试次数并解释为什么是这个数字；
- 再显式设 RetryConfig(max_attempts=2) 对比，说明差异从哪来；
- 顺带验证一条：完全不写 retry_config 时，它还会重试吗？

本练习不调用模型，也不写任何外部存储——只观察框架的重试行为。
"""

from __future__ import annotations

import json

from google.adk import Context, Workflow
from google.adk.workflow import RetryConfig, node

from _common import input_text, run, start


def make_app(name: str, retry_config, attempt_log: list[int]) -> Workflow:
    """构造一个"每次必失败"的工作流；retry_config 传 None 表示完全不写。

    注意 name 必须是合法的 Python 标识符（框架会用它拼节点路径与检查点身份），
    所以下面用 ASCII 名字，显示用中文标签。
    """

    async def failing_body(ctx: Context, node_input: dict) -> dict:
        attempt_log.append(ctx.attempt_count)
        raise ConnectionError(f"故障注入：{name} 每次必失败")

    # 关键：retry_config=None 时不传这个参数，模拟"完全不写"
    if retry_config is None:
        failing = node(failing_body)
    else:
        failing = node(failing_body, retry_config=retry_config)

    @node(rerun_on_resume=True)
    async def entry(ctx: Context, node_input):
        try:
            return await ctx.run_node(failing, json.loads(input_text(node_input)))
        except Exception as error:
            # 框架会把节点里的异常包一层 DynamicNodeFailError，真正的根因在 .error 上。
            # 所以判断"到底为什么失败"时必须先拆包——第 8 章处理超时用的也是同一招。
            root_cause = getattr(error, "error", error)
            return {
                "failed_with": type(error).__name__,
                "root_cause": type(root_cause).__name__,
                "attempts": list(attempt_log),
            }

    return Workflow(name=name, edges=[("START", entry)])


# 只为让实验跑得快，把等待压到 0.01 秒；默认是 1 秒起步、每次翻倍。
FAST = {"initial_delay": 0.01, "max_delay": 0.01, "jitter": 0}

SCENARIOS = [
    (
        "不写 retry_config",
        "no_retry_config",
        None,
        1,
        "框架根本不进重试分支：失败即失败",
    ),
    (
        "RetryConfig()（不写 max_attempts）",
        "retry_config_default_max",
        RetryConfig(exceptions=[ConnectionError], **FAST),
        5,
        "静默拿到 5 次预算——这是最容易记错的一格",
    ),
    (
        "RetryConfig(max_attempts=1)",
        "retry_max_attempts_1",
        RetryConfig(max_attempts=1, exceptions=[ConnectionError], **FAST),
        1,
        "显式声明不重试",
    ),
    (
        "RetryConfig(max_attempts=2)",
        "retry_max_attempts_2",
        RetryConfig(max_attempts=2, exceptions=[ConnectionError], **FAST),
        2,
        "包含第一次请求，所以只额外重试 1 次",
    ),
]


async def main() -> None:
    print(f"{'写法':<34}{'实际尝试':<10}{'期望':<7}{'attempt_count'}")
    print("-" * 78)

    for label, flow_name, cfg, expected, _note in SCENARIOS:
        log: list[int] = []
        app = make_app(flow_name, cfg, log)
        result, *_ = await start(app, {"key": "budget"})

        attempts = result["attempts"]
        print(f"{label:<34}{len(attempts):<10}{expected:<7}{attempts}")

        assert len(attempts) == expected, (
            f"{label}: 预期 {expected} 次尝试，实际 {len(attempts)} 次 -> {attempts}"
        )
        # attempt_count 从 1 开始，所以应该是 [1, 2, ..., expected]
        assert attempts == list(range(1, expected + 1)), attempts
        # 外层是框架包的 DynamicNodeFailError，根因才是我们抛的 ConnectionError
        assert result["failed_with"] == "DynamicNodeFailError", result
        assert result["root_cause"] == "ConnectionError", result

    print("\n✅ 练习 3 通过：四种写法的实际尝试次数与预期完全一致")
    print("""
为什么是这个数字？—— 看框架的判断逻辑就明白了：

    max_attempts = retry_config.max_attempts if retry_config.max_attempts is not None else 5
    if attempt_count >= max_attempts:
        return False        # 不再重试
    if not retry_config:
        return False        # 压根没配 retry_config，直接不重试

两行判断解释了全部四格：

  1. **不写 retry_config** → 命中第二个判断，直接放弃 → 1 次尝试。
     "默认重试 5 次"这个说法**只对写了 RetryConfig 的节点成立**。

  2. **写了 RetryConfig() 但没写 max_attempts** → 第一个判断取到默认值 5 →
     尝试 1、2、3、4、5 各一次，第 5 次之后 attempt_count(5) >= 5，停止。

  3. **max_attempts=1** → attempt_count(1) >= 1 立刻成立 → 只有 1 次。

  4. **max_attempts=2** → 2 次。注意它是**总次数**，不是"重试次数"。

顺带一个很实用的发现：**框架会把节点异常包一层 `DynamicNodeFailError`**，
真正的根因挂在 `.error` 上。所以想判断"到底为什么失败"，
要先 `getattr(error, "error", error)` 拆包——第 8 章处理节点超时用的正是这一招
（`isinstance(getattr(error, "error", error), NodeTimeoutError)`）。

工程上的结论只有一句：
**重试次数不要靠默认值，明确写出来。** 一个会写外部存储的节点，
"静默拿到 5 次预算"和"完全不重试"之间的差别，可能就是 5 倍的重复副作用。
""")


if __name__ == "__main__":
    run(main, need_api_key=False)
