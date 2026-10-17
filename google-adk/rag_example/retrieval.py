"""标准库实现的字符二元组/英文词词法检索；不是语义向量检索。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Protocol


CORPUS = Path(__file__).with_name("corpus")
INDEX_VERSION = "paragraph-bigram-v1"


def terms(text: str) -> set[str]:
    """中文连续片段取二元组，英文/数字按词；不做同义词扩展。"""
    result = set(re.findall(r"[a-z0-9]+", text.lower()))
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        result.update(span[i:i + 2] for i in range(len(span) - 1))
    return result


@dataclass(frozen=True)
class Scope:
    """由应用鉴权层提供；不能让模型通过工具参数修改。"""

    tenant_id: str
    as_of: str

    def __post_init__(self) -> None:
        if date.fromisoformat(self.as_of).isoformat() != self.as_of:
            raise ValueError("as_of 必须使用 YYYY-MM-DD 格式")
        if not self.tenant_id:
            raise ValueError("tenant_id 不能为空")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    version: str
    tenant_id: str
    title: str
    source: str
    paragraph: int
    valid_from: str
    valid_until: str | None
    text: str

    def visible(self, scope: Scope) -> bool:
        return (
            self.tenant_id == scope.tenant_id
            and self.valid_from <= scope.as_of
            and (self.valid_until is None or scope.as_of < self.valid_until)
        )


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float

    def evidence(self) -> dict:
        return {**asdict(self.chunk), "score": round(self.score, 4)}


class Retriever(Protocol):
    """替换为 BM25/向量/混合检索时保留此接口及权限过滤语义。"""

    def search(self, query: str, scope: Scope, *, k: int = 3) -> list[Hit]: ...


class LexicalIndex:
    def __init__(self, chunks: list[Chunk], corpus_digest: str):
        self.chunks = chunks
        self.corpus_digest = corpus_digest
        self.postings: dict[str, set[int]] = defaultdict(set)
        for position, chunk in enumerate(chunks):
            for term in terms(chunk.text):
                self.postings[term].add(position)

    @classmethod
    def build(cls, corpus: Path = CORPUS) -> LexicalIndex:
        corpus = corpus.resolve()
        manifest_bytes = (corpus / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        digest = hashlib.sha256(manifest_bytes)
        chunks, ids = [], set()
        for doc in manifest["documents"]:
            path = (corpus / doc["file"]).resolve()
            if not path.is_relative_to(corpus):
                raise ValueError("语料文件必须位于 corpus 目录内")
            date.fromisoformat(doc["valid_from"])
            if doc["valid_until"]:
                date.fromisoformat(doc["valid_until"])
                if doc["valid_until"] <= doc["valid_from"]:
                    raise ValueError("政策有效期必须为非空区间")
            raw = path.read_bytes()
            digest.update(raw)
            paragraphs = [
                p.strip() for p in re.split(r"\n\s*\n", raw.decode("utf-8"))
                if p.strip() and not p.lstrip().startswith("#")
            ]
            for number, paragraph in enumerate(paragraphs, 1):
                chunk_id = (
                    f"{doc['tenant_id']}/{doc['document_id']}"
                    f"@{doc['version']}#p{number}"
                )
                if chunk_id in ids:
                    raise ValueError(f"重复 chunk_id：{chunk_id}")
                ids.add(chunk_id)
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    document_id=doc["document_id"],
                    version=doc["version"],
                    tenant_id=doc["tenant_id"],
                    title=doc["title"],
                    source=doc["file"],
                    paragraph=number,
                    valid_from=doc["valid_from"],
                    valid_until=doc["valid_until"],
                    text=paragraph,
                ))
        return cls(chunks, digest.hexdigest())

    def save(self, path: Path) -> None:
        payload = {
            "index_version": INDEX_VERSION,
            "corpus_digest": self.corpus_digest,
            "chunks": [asdict(c) for c in self.chunks],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, *, expected_digest: str) -> LexicalIndex:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["index_version"] != INDEX_VERSION:
            raise ValueError("分块/分词版本变化，需要重建索引")
        if payload["corpus_digest"] != expected_digest:
            raise ValueError("语料快照变化，需要重建索引")
        return cls([Chunk(**c) for c in payload["chunks"]], expected_digest)

    def search(self, query: str, scope: Scope, *, k: int = 3) -> list[Hit]:
        if not 1 <= k <= 10:
            raise ValueError("k 必须为 1～10")
        query_terms = terms(query)
        visible = {i for i, c in enumerate(self.chunks) if c.visible(scope)}
        scores: Counter[int] = Counter()
        for term in query_terms:
            matches = self.postings.get(term, set()) & visible
            weight = math.log((1 + len(visible)) / (1 + len(matches))) + 1
            for position in matches:
                scores[position] += weight
        # 零词法重合就拒绝召回；分数只用于排序，不是置信概率。
        hits = [Hit(self.chunks[i], score) for i, score in scores.items() if score > 0]
        return sorted(hits, key=lambda h: (-h.score, h.chunk.chunk_id))[:k]
