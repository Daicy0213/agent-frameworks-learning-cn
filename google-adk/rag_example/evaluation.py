"""检索与生成检查分开计算；离线生成指标不代表真实模型质量。"""
from __future__ import annotations
import json
from pathlib import Path
from .agent import answer_question
from .retrieval import Scope


def load_cases() -> list[dict]:
    return json.loads(Path(__file__).with_name("eval_cases.json").read_text(encoding="utf-8"))


def evaluate_retrieval(index, cases: list[dict], *, k: int = 3) -> dict:
    rows = []
    for case in cases:
        expected = set(case["relevant_ids"])
        hits = index.search(case["query"], Scope(case["tenant_id"], case["as_of"]), k=k)
        found = [h.chunk.chunk_id for h in hits]
        ranks = [i + 1 for i, cid in enumerate(found) if cid in expected]
        rows.append({
            "id": case["id"], "expected": sorted(expected), "retrieved": found,
            "recall": len(expected.intersection(found)) / len(expected) if expected else None,
            "precision": len(expected.intersection(found)) / len(found) if found else None,
            "reciprocal_rank": 1 / min(ranks) if ranks else 0,
            "correct_empty": not found if not expected else None,
        })
    answerable = [r for r in rows if r["recall"] is not None]
    unanswerable = [r for r in rows if r["correct_empty"] is not None]
    return {
        "k": k,
        "recall_at_k": sum(r["recall"] for r in answerable) / len(answerable),
        "mrr": sum(r["reciprocal_rank"] for r in answerable) / len(answerable),
        "empty_query_accuracy": sum(r["correct_empty"] for r in unanswerable) / len(unanswerable),
        "rows": rows,
    }


async def evaluate_generation(index, cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        result = await answer_question(
            case["query"], scope=Scope(case["tenant_id"], case["as_of"]), retriever=index,
        )
        answer = result["answer"]
        cited = {c["chunk_id"] for c in answer["citations"]}
        expected = set(case["relevant_ids"])
        correct = (
            bool(cited & expected) if expected
            else answer["status"] == "insufficient_evidence"
        )
        rows.append({"id": case["id"], "correct_source_or_abstention": correct,
                     "status": answer["status"], "cited": sorted(cited)})
    return {
        "backend": "offline-extractive",
        "source_or_abstention_accuracy": (
            sum(r["correct_source_or_abstention"] for r in rows) / len(rows)
        ),
        "meaning": "真实 Runner 的引用选择与拒答协议；不评估真实 LLM 理解或改写能力",
        "rows": rows,
    }
