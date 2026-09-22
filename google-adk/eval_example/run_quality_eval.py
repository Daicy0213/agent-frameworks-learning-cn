"""运行工程化质量评估并生成 JSON/Markdown 报告。

ADK 内置 ``adk eval`` 适合检查工具轨迹和参考回答相似度；本脚本复用同一
份 evalset，补上任务关键字、格式、安全、延迟、token 与估算成本等聚合门禁。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.evaluation.final_response_match_v1 import _calculate_rouge_1_scores
from google.genai import types

from .agent import MODEL_NAME, root_agent
from .tools import reset_demo_state


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = PROJECT_DIR / "eval_sets" / "after_sales.evalset.json"
DEFAULT_GATES = PROJECT_DIR / "quality_gates.json"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_dataset(dataset: dict[str, Any], min_cases: int = 20) -> list[str]:
    """检查教学数据集的结构、规模和最小覆盖面。"""

    errors: list[str] = []
    cases = dataset.get("eval_cases", [])
    if len(cases) < min_cases:
        errors.append(f"案例数为 {len(cases)}，少于要求的 {min_cases}。")

    ids = [case.get("eval_id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("eval_id 存在重复。")

    required_categories = {
        "normal",
        "edge",
        "tool_failure",
        "safety",
        "high_risk",
        "multi_turn",
    }
    categories = {case.get("test_spec", {}).get("category") for case in cases}
    missing_categories = sorted(required_categories - categories)
    if missing_categories:
        errors.append(f"缺少类别：{', '.join(missing_categories)}。")

    for case in cases:
        case_id = case.get("eval_id", "<unknown>")
        conversation = case.get("conversation") or []
        turn_specs = case.get("test_spec", {}).get("turns") or []
        if not conversation:
            errors.append(f"{case_id}: conversation 为空。")
        if len(conversation) != len(turn_specs):
            errors.append(f"{case_id}: conversation 与 test_spec.turns 数量不一致。")
        for index, invocation in enumerate(conversation, start=1):
            try:
                invocation["user_content"]["parts"][0]["text"]
                invocation["final_response"]["parts"][0]["text"]
                invocation["intermediate_data"]["tool_uses"]
            except (KeyError, IndexError, TypeError):
                errors.append(f"{case_id} 第 {index} 轮缺少 ADK 必需字段。")
    return errors


def _tool_calls_from_event(event: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        call = getattr(part, "function_call", None)
        if call:
            calls.append({"name": call.name, "args": dict(call.args or {})})
    return calls


def _token_usage_from_event(event: Any) -> tuple[int, int]:
    usage = getattr(event, "usage_metadata", None)
    if usage is None:
        return 0, 0
    input_tokens = int(
        getattr(usage, "prompt_token_count", None)
        or getattr(usage, "input_token_count", None)
        or 0
    )
    output_tokens = int(
        getattr(usage, "candidates_token_count", None)
        or getattr(usage, "output_token_count", None)
        or 0
    )
    return input_tokens, output_tokens


def _content_text(content: Any) -> str:
    return "".join(
        part.text or "" for part in (getattr(content, "parts", None) or [])
    )


def _expected_calls(invocation: dict[str, Any]) -> list[dict[str, Any]]:
    return invocation.get("intermediate_data", {}).get("tool_uses", [])


def _canonical(value: Any) -> str:
    """用稳定 JSON 比较工具名和参数，避免字典键顺序影响结果。"""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_assertion_text(value: str) -> str:
    """忽略大小写与空白差异，避免“7 天/7天”造成伪失败。"""

    return re.sub(r"\s+", "", value).casefold()


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
    return ordered[index]


async def _run_turn(
    runner: Runner,
    user_id: str,
    session_id: str,
    query: str,
) -> dict[str, Any]:
    message = types.Content(role="user", parts=[types.Part(text=query)])
    actual_calls: list[dict[str, Any]] = []
    final_text = ""
    input_tokens = 0
    output_tokens = 0
    started = time.perf_counter()

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        actual_calls.extend(_tool_calls_from_event(event))
        turn_input, turn_output = _token_usage_from_event(event)
        input_tokens += turn_input
        output_tokens += turn_output
        if event.is_final_response() and event.content:
            final_text = _content_text(event.content)

    return {
        "response": final_text,
        "actual_tool_uses": actual_calls,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


async def evaluate(
    dataset: dict[str, Any],
    gates: dict[str, Any],
    selected_case: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """逐案例回放对话，并计算确定性的工程断言。"""

    cases = dataset["eval_cases"]
    if selected_case:
        cases = [case for case in cases if case["eval_id"] == selected_case]
        if not cases:
            raise ValueError(f"找不到案例：{selected_case}")
    if limit is not None:
        cases = cases[:limit]

    reset_demo_state()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="eval_example",
        session_service=session_service,
    )

    results: list[dict[str, Any]] = []
    for case_index, case in enumerate(cases, start=1):
        user_id = "quality-eval"
        session_id = f"eval-{case_index}-{case['eval_id']}"
        await session_service.create_session(
            app_name="eval_example",
            user_id=user_id,
            session_id=session_id,
        )
        turn_results = []
        for invocation, assertions in zip(
            case["conversation"], case["test_spec"]["turns"], strict=True
        ):
            query = invocation["user_content"]["parts"][0]["text"]
            turn = await _run_turn(runner, user_id, session_id, query)
            expected_calls = _expected_calls(invocation)
            reference = invocation["final_response"]["parts"][0]["text"]
            response = turn["response"]
            required = assertions.get("required_keywords", [])
            forbidden = assertions.get("forbidden_keywords", [])
            markers = assertions.get("required_markers", [])
            normalized_response = _normalize_assertion_text(response)
            turn["query"] = query
            turn["expected_tool_uses"] = expected_calls
            turn["tool_selection_pass"] = _canonical(
                turn["actual_tool_uses"]
            ) == _canonical(expected_calls)
            # 与 ADK response_match_score 使用同一个 Unicode-aware ROUGE-1 实现。
            turn["response_match_score"] = _calculate_rouge_1_scores(
                response, reference
            ).fmeasure
            turn["task_success_pass"] = all(
                _normalize_assertion_text(word) in normalized_response
                for word in required
            ) and all(
                _normalize_assertion_text(word) not in normalized_response
                for word in forbidden
            )
            turn["format_pass"] = all(marker in response for marker in markers) and len(
                response
            ) <= 220
            turn_results.append(turn)

        case_pass = all(
            turn["tool_selection_pass"]
            and turn["task_success_pass"]
            and turn["format_pass"]
            for turn in turn_results
        )
        results.append(
            {
                "eval_id": case["eval_id"],
                "category": case["test_spec"]["category"],
                "passed": case_pass,
                "turns": turn_results,
            }
        )
        status = "PASS" if case_pass else "FAIL"
        print(f"[{case_index:02d}/{len(cases):02d}] {status} {case['eval_id']}")

    turns = [turn for result in results for turn in result["turns"]]
    case_count = len(results)
    task_rate = statistics.fmean(turn["task_success_pass"] for turn in turns)
    tool_rate = statistics.fmean(turn["tool_selection_pass"] for turn in turns)
    format_rate = statistics.fmean(turn["format_pass"] for turn in turns)
    response_match_score = statistics.fmean(
        turn["response_match_score"] for turn in turns
    )
    safety_cases = [result for result in results if result["category"] == "safety"]
    safety_rate = (
        statistics.fmean(result["passed"] for result in safety_cases)
        if safety_cases
        else 1.0
    )
    input_tokens = sum(turn["input_tokens"] for turn in turns)
    output_tokens = sum(turn["output_tokens"] for turn in turns)
    input_price = float(
        os.getenv(
            "DEEPSEEK_INPUT_USD_PER_MILLION",
            gates["deepseek_input_usd_per_million_tokens"],
        )
    )
    output_price = float(
        os.getenv(
            "DEEPSEEK_OUTPUT_USD_PER_MILLION",
            gates["deepseek_output_usd_per_million_tokens"],
        )
    )
    estimated_cost = input_tokens / 1_000_000 * input_price + output_tokens / 1_000_000 * output_price

    metrics = {
        "dataset_case_count": case_count,
        "turn_count": len(turns),
        "case_pass_rate": statistics.fmean(result["passed"] for result in results),
        "task_success_rate": task_rate,
        "tool_selection_accuracy": tool_rate,
        "response_match_score": response_match_score,
        "format_compliance_rate": format_rate,
        "safety_case_pass_rate": safety_rate,
        "p95_latency_ms": round(_percentile_95([turn["latency_ms"] for turn in turns]), 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_total_cost_usd": round(estimated_cost, 6),
    }
    gate_results = {
        "dataset_min_cases": case_count >= gates["dataset_min_cases"],
        "task_success_rate_min": task_rate >= gates["task_success_rate_min"],
        "tool_selection_accuracy_min": tool_rate >= gates["tool_selection_accuracy_min"],
        "response_match_score_min": response_match_score
        >= gates["response_match_score_min"],
        "format_compliance_rate_min": format_rate >= gates["format_compliance_rate_min"],
        "safety_case_pass_rate_min": safety_rate >= gates["safety_case_pass_rate_min"],
        "p95_latency_ms_max": metrics["p95_latency_ms"] <= gates["p95_latency_ms_max"],
        "estimated_total_cost_usd_max": estimated_cost
        <= gates["estimated_total_cost_usd_max"],
    }
    return {
        "schema_version": 1,
        "created_at_unix": time.time(),
        "model": MODEL_NAME,
        "dataset_id": dataset["eval_set_id"],
        "metrics": metrics,
        "gates": gate_results,
        "passed": all(gate_results.values()),
        "cases": results,
    }


def compare_baseline(
    report: dict[str, Any], baseline: dict[str, Any], max_regression: float
) -> dict[str, bool]:
    """检查核心比例是否比基线下降超过允许值。"""

    keys = (
        "task_success_rate",
        "tool_selection_accuracy",
        "format_compliance_rate",
        "safety_case_pass_rate",
        "response_match_score",
    )
    return {
        key: report["metrics"][key] >= baseline["metrics"][key] - max_regression
        for key in keys
    }


def _write_reports(report: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "latest.json"
    md_path = report_dir / "latest.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    metrics = report["metrics"]
    failed_cases = [case["eval_id"] for case in report["cases"] if not case["passed"]]
    gate_lines = [
        f"| {name} | {'通过' if passed else '失败'} |"
        for name, passed in report["gates"].items()
    ]
    markdown = f"""# 售后 Agent 评估报告

- 总体结论：{'通过' if report['passed'] else '失败'}
- 模型：`{report['model']}`
- 数据集：`{report['dataset_id']}`
- 案例/轮次：{metrics['dataset_case_count']} / {metrics['turn_count']}
- 任务成功率：{metrics['task_success_rate']:.2%}
- 工具选择准确率：{metrics['tool_selection_accuracy']:.2%}
- 回答相似度（ROUGE-1）：{metrics['response_match_score']:.2%}
- 格式合规率：{metrics['format_compliance_rate']:.2%}
- 安全用例通过率：{metrics['safety_case_pass_rate']:.2%}
- P95 延迟：{metrics['p95_latency_ms']:.2f} ms
- 估算总成本：${metrics['estimated_total_cost_usd']:.6f}

## 质量门禁

| 门禁 | 结果 |
|---|---|
{chr(10).join(gate_lines)}

## 失败案例

{', '.join(failed_cases) if failed_cases else '无'}
"""
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行售后 Agent 工程化质量评估")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--gates", type=Path, default=DEFAULT_GATES)
    parser.add_argument("--case", help="只运行指定 eval_id")
    parser.add_argument("--limit", type=int, help="只运行前 N 个案例，用于冒烟测试")
    parser.add_argument("--baseline", type=Path, help="与一个历史 latest.json 比较")
    parser.add_argument("--report-dir", type=Path, default=PROJECT_DIR / "reports")
    parser.add_argument(
        "--dry-run", action="store_true", help="只校验数据集，不调用模型"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = _read_json(args.dataset)
    gates = _read_json(args.gates)
    errors = validate_dataset(dataset, gates["dataset_min_cases"])
    if errors:
        print("数据集校验失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print(f"数据集校验通过：{len(dataset['eval_cases'])} 个案例。")
    if args.dry_run:
        return 0
    if not os.getenv("DEEPSEEK_API_KEY") and MODEL_NAME.startswith("deepseek/"):
        print("缺少 DEEPSEEK_API_KEY；请复制 .env.example 为仓库根目录 .env。", file=sys.stderr)
        return 2

    report = asyncio.run(evaluate(dataset, gates, args.case, args.limit))
    if args.baseline:
        baseline_results = compare_baseline(
            report,
            _read_json(args.baseline),
            gates["max_regression_from_baseline"],
        )
        report["baseline_gates"] = baseline_results
        report["passed"] = report["passed"] and all(baseline_results.values())

    json_path, md_path = _write_reports(report, args.report_dir)
    print(f"JSON 报告：{json_path}")
    print(f"Markdown 报告：{md_path}")
    print("总体结论：" + ("通过" if report["passed"] else "失败"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
