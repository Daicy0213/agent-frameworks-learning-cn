"""Notebook 主线离线实验：不读密钥、不调用远程模型。"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted(ROOT.glob("0*.ipynb"))
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem[:2])
def test_notebook_code_compiles(path):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), f"{path}:cell{index}", "exec",
                    ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


@pytest.mark.parametrize("path", NOTEBOOKS[1:], ids=lambda p: p.stem[:2])
def test_offline_mainline_runs_without_deep_reading(path, monkeypatch):
    monkeypatch.chdir(ROOT.parent)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    notebook = json.loads(path.read_text(encoding="utf-8"))

    async def execute():
        namespace = {"__name__": "__main__"}
        count = 0
        for index, cell in enumerate(notebook["cells"]):
            if "offline" not in cell.get("metadata", {}).get("tags", []):
                continue
            count += 1
            code = compile("".join(cell["source"]), f"{path}:cell{index}", "exec",
                           ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            result = eval(code, namespace)
            if result is not None:
                await result
        assert count, f"{path.name} 没有离线主线实验"

    asyncio.run(execute())


def load_practice(name):
    sys.path.insert(0, str(ROOT / "practice"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "practice" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_triage_requires_real_json_contract():
    from pydantic import ValidationError

    lesson = load_practice("c3_2")
    good = {"user_level": "VIP", "issue_type": "login", "priority": "high",
            "reply_language": "中文", "next_action": "核验身份"}
    assert lesson.TriageResult.model_validate(good).priority == "high"
    with pytest.raises(ValidationError):
        lesson.TriageResult.model_validate({**good, "priority": "highish"})
    with pytest.raises(ValidationError):
        lesson.TriageResult.model_validate_json('{"text": "priority high next_action"}')


def test_action_item_fields_and_source_facts_are_separate():
    from pydantic import ValidationError

    lesson = load_practice("c3_3")
    items = [
        {"owner": "小王", "task": "改版方案", "due_date": "2026-10-19", "priority": "normal", "risk": "none"},
        {"owner": "小李", "task": "灰度清单", "due_date": "2026-10-21", "priority": "normal", "risk": "测试环境不稳定"},
        {"owner": "老张", "task": "法务文案", "due_date": "2026-10-23", "priority": "high", "risk": "none"},
    ]
    valid = lesson.ActionItems.model_validate({"items": items})
    assert lesson.business_check(valid) == []
    for value in [{"due_date": "tomorrow"}, {"priority": "urgent"}]:
        with pytest.raises(ValidationError):
            lesson.ActionItem.model_validate({**items[0], **value})
    wrong_fact = lesson.ActionItems.model_validate(
        {"items": [{**items[0], "due_date": "2026-10-14"}, *items[1:]]}
    )
    assert lesson.business_check(wrong_fact)
