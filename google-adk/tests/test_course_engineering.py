"""工程章节的离线主线与导航契约；真实模型质量单独评估。"""
from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted(ROOT.glob("1*.ipynb"))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda path: path.stem[:2])
def test_engineering_code_compiles(path):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), f"{path}:cell{index}", "exec",
                    ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda path: path.stem[:2])
def test_engineering_offline_mainline(path, monkeypatch):
    monkeypatch.chdir(ROOT.parent)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.syspath_prepend(str(ROOT))
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
        assert count > 0, f"{path.name} 必须有无需密钥的主线入口"

    asyncio.run(execute())


def test_local_markdown_links_exist():
    paths = [ROOT.parent / "README.md", *ROOT.rglob("README.md"),
             *ROOT.glob("附录*.md"), *ROOT.glob("*.ipynb")]
    problems = []
    for path in paths:
        if any(part in {".adk", ".ipynb_checkpoints", "runs", "reports", "__pycache__"}
               for part in path.parts):
            continue
        if path.suffix == ".ipynb":
            notebook = json.loads(path.read_text(encoding="utf-8"))
            text = "\n".join("".join(c["source"]) for c in notebook["cells"]
                             if c["cell_type"] == "markdown")
        else:
            text = path.read_text(encoding="utf-8-sig")
        for link in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text):
            if ":" in link or link.startswith("#"):
                continue
            target = unquote(link.split("#", 1)[0])
            if target and not (path.parent / target).exists():
                problems.append(f"{path.relative_to(ROOT.parent)} -> {target}")
    assert not problems, "失效的本地链接：\n" + "\n".join(problems)


def test_callback_experiment_detects_a_missing_guard(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "practice"))
    import c7_2

    asyncio.run(c7_2.main())
    # 若删除 callback，工具本体仍拒绝，但教学验收必须发现短路没有发生。
    monkeypatch.setattr(c7_2, "policy_for", lambda principal: lambda **kwargs: None)
    with pytest.raises(AssertionError, match="callback"):
        asyncio.run(c7_2.main())


def test_id_number_redaction_includes_check_digit(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "practice"))
    from c12_1 import redact

    for suffix in ("4", "X", "x"):
        number = "11010119900101123" + suffix
        masked = redact("身份证 " + number)
        assert number not in masked and "19900101" not in masked
