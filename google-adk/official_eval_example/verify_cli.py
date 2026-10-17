"""离线调用真正的 adk eval，完成通过→故障→修复→选案例回归。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

# 作为脚本执行，避免导入包时提前构造 Agent。
from check_result import summarize_report

HERE = Path(__file__).resolve().parent


def run_one(label: str, *, backend: str, bug: bool, selected: str | None, output: Path) -> dict:
    selector = "official_eval_example/three_cases.evalset.json"
    if selected:
        selector += ":" + selected
    suffix = [selector, "--config_file_path", "official_eval_example/evaluation_config.json",
              "--print_detailed_results"]
    with TemporaryDirectory(prefix="adk-official-eval-") as folder:
        temporary = Path(folder).resolve()
        if backend == "docker":
            history = temporary / "history"
            history.mkdir()
            command = ["docker", "run", "--rm", "--network", "none", "--name",
                       "adk-course-eval-" + uuid4().hex[:8],
                       "--mount", f"type=bind,source={history},target=/course/google-adk/official_eval_example/.adk",
                       "-e", "ADK_EVAL_BACKEND=offline",
                       "-e", "ADK_EVAL_INJECT_BUG=" + ("skip_tool" if bug else ""),
                       "adk-course-eval:2.6.3", *suffix]
            cwd = HERE.parents[1]
        else:
            project = temporary / "official_eval_example"
            shutil.copytree(HERE, project, ignore=shutil.ignore_patterns(".adk", "reports", "__pycache__"))
            env_dir = HERE.parents[1] / ".venv-eval"
            adk = env_dir / ("Scripts/adk.exe" if os.name == "nt" else "bin/adk")
            command = [str(adk), "eval", "official_eval_example", *suffix]
            history = project / ".adk"
            cwd = temporary
        env = os.environ.copy()
        env["ADK_EVAL_BACKEND"] = "offline"
        env["ADK_EVAL_INJECT_BUG"] = "skip_tool" if bug else ""
        env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=180)
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"官方 CLI 未完成，查看 {output / (label + '.log')}")
        reports = list(history.rglob("*.evalset_result.json"))
        if len(reports) != 1:
            raise RuntimeError(f"预期本次生成一份官方报告，实际 {len(reports)}")
        data = json.loads(reports[0].read_text(encoding="utf-8"))
        shutil.copyfile(reports[0], output / f"{label}.evalset_result.json")
        summary = summarize_report(data)
        summary["cli_exit_code"] = result.returncode
        summary["run"] = label
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["docker", "local"], default="docker")
    parser.add_argument("--report-dir", type=Path, default=HERE / "reports")
    args = parser.parse_args()
    runs = []
    for label, bug, case, expected_count in [
        ("green", False, None, 3), ("broken", True, "order_found", 1),
        ("repaired", False, None, 3), ("selected", False, "order_missing", 1),
    ]:
        summary = run_one(label, backend=args.backend, bug=bug, selected=case, output=args.report_dir)
        if summary["passed"] == bug or len(summary["cases"]) != expected_count:
            raise AssertionError(f"{label} 不符合预测：{summary}")
        if bug:
            metrics = summary["cases"][0]["metrics"]
            assert metrics["tool_trajectory_avg_score"] == 0
            assert metrics["response_match_score"] == 1
        runs.append(summary)
        print(json.dumps(summary, ensure_ascii=False))
    (args.report_dir / "verification.json").write_text(
        json.dumps({"backend": args.backend, "model_api_calls": 0, "runs": runs},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
