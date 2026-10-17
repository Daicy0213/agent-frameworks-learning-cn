"""官方 CLI 的报告状态才是质量证据；不运行 Docker 或调用模型。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "official_eval_example/check_result.py"
spec = importlib.util.spec_from_file_location("course_eval_report", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def report(status: int) -> dict:
    return {"eval_case_results": [{"eval_id": "case-1", "final_eval_status": status,
             "overall_eval_metric_results": [
                 {"metric_name": "response_match_score", "score": 1.0},
                 {"metric_name": "tool_trajectory_avg_score", "score": 0.0 if status == 2 else 1.0}]}]}


@pytest.mark.parametrize("status,expected_exit", [(1, 0), (2, 1), (3, 1)])
def test_report_status_controls_ci_exit(tmp_path, status, expected_exit):
    path = tmp_path / "run.evalset_result.json"
    path.write_text(json.dumps(report(status)), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True)
    assert result.returncode == expected_exit


def test_correct_answer_cannot_hide_failed_trajectory():
    result = module.summarize_report(report(2))
    assert result["cases"][0]["metrics"]["response_match_score"] == 1
    assert result["cases"][0]["metrics"]["tool_trajectory_avg_score"] == 0
    assert result["passed"] is False


def test_empty_report_is_not_a_pass(tmp_path):
    with pytest.raises(ValueError, match="没有案例"):
        module.summarize_report({"eval_case_results": []})
    path = tmp_path / "empty.json"
    path.write_text('{"eval_case_results": []}', encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True)
    assert result.returncode == 2


def test_non_object_report_is_not_a_pass(tmp_path):
    with pytest.raises(ValueError, match="JSON 对象"):
        module.summarize_report([])
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True)
    assert result.returncode == 2
