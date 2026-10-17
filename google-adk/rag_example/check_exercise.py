"""独立练习验收：与示范 verify 分开，空骨架应失败。"""
from .evaluation import evaluate_retrieval, load_cases
from .exercise import ExerciseRetriever
from .retrieval import Scope


def main() -> None:
    retriever = ExerciseRetriever()
    report = evaluate_retrieval(retriever, load_cases())
    assert report["recall_at_k"] == 1.0
    assert report["empty_query_accuracy"] == 1.0
    hits = retriever.search("买来用不了多久就坏了咋办", Scope("shop-a", "2026-10-01"))
    assert hits and hits[0].chunk.document_id == "warranty"
    assert all(hit.chunk.visible(Scope("shop-a", "2026-10-01")) for hit in hits)
    print("练习验收通过；仍需增加自己未用于调参的保留问题。")


if __name__ == "__main__":
    main()
