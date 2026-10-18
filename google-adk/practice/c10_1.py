"""第 10 章练习 1：离线校验评估集。

不调用模型，检查：
- 案例规模是否足够；
- 分类是否覆盖正常、边界、安全、多轮；
- 每条案例是否具备用户输入、期望工具、必含字段或禁止词；
- eval_id 是否唯一。

运行：uv run python c10_1.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from _common import run

MIN_CASES = 20
REQUIRED_CATEGORIES = {"normal", "edge", "safety", "multi_turn"}


def load_dataset() -> dict:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "eval_example" / "eval_sets" / "after_sales.evalset.json",
        Path.cwd() / "eval_example" / "eval_sets" / "after_sales.evalset.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("找不到 after_sales.evalset.json")


def validate_dataset(dataset: dict) -> list[str]:
    problems: list[str] = []
    cases = dataset.get("eval_cases", [])

    if len(cases) < MIN_CASES:
        problems.append(f"案例数 {len(cases)} < {MIN_CASES}")

    ids = [case.get("eval_id") for case in cases]
    if len(ids) != len(set(ids)):
        problems.append("eval_id 有重复")

    categories = {case.get("test_spec", {}).get("category") for case in cases}
    missing = REQUIRED_CATEGORIES - categories
    if missing:
        problems.append(f"缺少分类：{sorted(missing)}")

    for case in cases:
        case_id = case.get("eval_id", "<no-id>")
        conversation = case.get("conversation") or []
        if not conversation:
            problems.append(f"{case_id}: 没有 conversation")
            continue

        has_tool_expectation = False
        for turn in conversation:
            if not turn.get("user_content"):
                problems.append(f"{case_id}: 某一轮缺少 user_content")
            tools = (turn.get("intermediate_data") or {}).get("tool_uses") or []
            has_tool_expectation = has_tool_expectation or bool(tools)

        spec = case.get("test_spec") or {}
        turns = spec.get("turns") or []
        if not turns:
            problems.append(f"{case_id}: test_spec.turns 为空")

        has_text_assertion = False
        for turn in turns:
            if (
                turn.get("required_keywords")
                or turn.get("forbidden_keywords")
                or turn.get("required_markers")
            ):
                has_text_assertion = True
            if not (turn.get("required_keywords") or turn.get("forbidden_keywords")):
                problems.append(f"{case_id}: 某一轮既没有必含词也没有禁止词")

        # 允许"本来就不该调工具"的案例（例如安全拒答），
        # 但每条案例至少要有一个可验证的断言。
        if not (has_tool_expectation or has_text_assertion):
            problems.append(f"{case_id}: 既没有工具期望，也没有文本断言")

    return problems


def main():
    dataset = load_dataset()
    problems = validate_dataset(dataset)

    categories = Counter(
        case.get("test_spec", {}).get("category")
        for case in dataset.get("eval_cases", [])
    )
    print("数据集：", dataset.get("eval_set_id"))
    print("案例数：", len(dataset.get("eval_cases", [])))
    print("分类分布：", dict(categories))

    assert not problems, "评估集校验失败：\n" + "\n".join(problems[:10])
    print("✅ 规模、分类、结构与断言字段全部符合要求")


if __name__ == "__main__":
    run(main, need_api_key=False)
