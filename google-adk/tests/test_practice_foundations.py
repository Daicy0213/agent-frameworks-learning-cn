"""基础练习的离线验收：不使用模型、不要求 API key。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PRACTICE = Path(__file__).resolve().parents[1] / "practice"


def run_script(path: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("DEEPSEEK_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(PRACTICE / path), *args],
        cwd=PRACTICE, env=env, text=True, encoding="utf-8",
        capture_output=True, timeout=60,
    )


@pytest.mark.parametrize("script", ["c1_3.py", "c4_2.py", "c9_5.py"])
def test_reference_experiments(script: str) -> None:
    result = run_script(script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "通过：" in result.stdout


@pytest.mark.parametrize("exercise", ["student_state", "student_recovery"])
def test_independent_checks_accept_reference(exercise: str) -> None:
    result = run_script(f"{exercise}/verify.py", "--reference")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("exercise", ["student_state", "student_recovery"])
def test_student_skeleton_is_not_reported_as_complete(exercise: str) -> None:
    # 仅对尚未填写的仓库初始骨架检查失败提示；学生完成后应由独立验收判定。
    source = (PRACTICE / exercise / "solution.py").read_text(encoding="utf-8")
    if "raise NotImplementedError(" not in source:
        pytest.skip("学生已填写作业，不再要求它失败")
    result = run_script(f"{exercise}/verify.py")
    assert result.returncode != 0
    assert "NotImplementedError" in result.stderr
