"""读取官方 JSON 报告，把评估状态转换为 CI 退出码。"""

import argparse
import json
from pathlib import Path


def summarize_report(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("报告顶层必须是 JSON 对象")
    cases = data.get("eval_case_results", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("报告没有案例，不能视为通过")
    return {
        "passed": all(case["final_eval_status"] == 1 for case in cases),
        "cases": [{"eval_id": case["eval_id"], "status": case["final_eval_status"],
                   "metrics": {metric["metric_name"]: metric["score"]
                               for metric in case["overall_eval_metric_results"]}}
                  for case in cases],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        summary = summarize_report(json.loads(args.report.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"无法验证报告：{error}")
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
