"""练习：实现可替换检索器，再运行独立验收。不要删除租户/日期边界。"""
from .retrieval import Hit, LexicalIndex, Scope


class ExerciseRetriever:
    def __init__(self) -> None:
        self.baseline = LexicalIndex.build()

    def search(self, query: str, scope: Scope, *, k: int = 3) -> list[Hit]:
        # TODO：先实现一个可解释的查询扩展，再考虑向量检索。
        # 保持基线支持的查询、拒答、租户和日期过滤；不要把标准答案写入返回值。
        raise NotImplementedError("请完成检索适配器")
