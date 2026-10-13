"""练习 2（进阶）：让审批摘要失效。

题目：允许人工编辑候选稿正文后重新计算摘要，然后用旧摘要提交审批。

验收：
- 断言 validate_approval 抛错；
- 说明这个摘要防住了什么（回复绑错稿件）、没防住什么（回复不是本人发的）。

本练习是纯函数级的：摘要校验与模型、框架都无关，先把这段逻辑想清楚，
放进流程里才不会出错。
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from _common import run


class Approval(BaseModel):
    approved: bool = Field(strict=True)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def candidate_digest(articles: list[dict]) -> str:
    """对候选稿做规范化摘要：键排序、无多余空格，保证同一内容得到同一摘要。"""
    encoded = json.dumps(
        articles, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_approval(response: dict, digest: str) -> bool:
    """校验审批回复：格式合法，且摘要与当前候选稿一致。"""
    decision = Approval.model_validate(response)
    if decision.digest != digest:
        raise ValueError("审批摘要与当前候选稿不一致")
    return decision.approved


def make_articles() -> list[dict]:
    return [
        {
            "id": "a",
            "draft": {"title": "工作流介绍", "body": "候选稿正文，等待人工审核。"},
        }
    ]


async def main() -> None:
    articles = make_articles()
    digest = candidate_digest(articles)
    print("原始候选稿摘要：", digest[:16], "...")

    # --- 基线：摘要一致时应当被接受 ---
    assert validate_approval({"approved": True, "digest": digest}, digest) is True
    print("基线：摘要一致 → 接受 ✅")

    # --- 场景 1：人工编辑了正文，但审批回复仍带旧摘要 ---
    edited = make_articles()
    edited[0]["draft"]["body"] = "人工修改后的正文，内容已经变了。"
    new_digest = candidate_digest(edited)
    assert new_digest != digest, "内容变了，摘要必须跟着变"

    try:
        validate_approval({"approved": True, "digest": digest}, new_digest)
    except ValueError as error:
        print(f"编辑后仍用旧摘要 → 被拒绝 ✅ （{error}）")
    else:
        raise AssertionError("旧摘要必须被拒绝！")

    # --- 场景 2：用新摘要重新提交，应当被接受 ---
    assert validate_approval({"approved": True, "digest": new_digest}, new_digest) is True
    print("用新摘要重新提交 → 接受 ✅")

    # --- 场景 3：格式不合法（摘要不是 64 位十六进制）也要挡住 ---
    for bad in ({"approved": True, "digest": "0" * 63}, {"approved": True, "digest": "ZZ" * 32}):
        try:
            validate_approval(bad, digest)
        except ValueError:
            pass
        else:
            raise AssertionError(f"非法摘要必须被拒绝：{bad}")

    # --- 场景 4：approved 必须是真布尔值，字符串 "true" 不算 ---
    try:
        Approval.model_validate({"approved": "true", "digest": digest})
    except ValueError:
        print("approved 传字符串 \"true\" → 被拒绝 ✅ （strict=True 生效）")
    else:
        raise AssertionError("strict 模式下字符串不应通过")

    # --- 场景 5：摘要必须"内容敏感" ---
    reordered = [dict(articles[0])]
    reordered[0]["draft"] = dict(articles[0]["draft"], title="改了标题")
    assert candidate_digest(reordered) != digest, "标题变了摘要也必须变"

    print("\n✅ 练习 2 通过：摘要能精确绑定候选稿内容")
    print("""
题目要求说清楚的两件事：

**这个摘要防住了什么？**
  防"回复绑错稿件"。人工确认和归档之间可能隔着恢复、重启、甚至另一个任务，
  如果审批回复里只有一个 approved=True，就没人知道它批准的是哪一版内容。
  带上摘要之后，"批准 A 稿"的回复无法被用来归档 B 稿 —— 上面场景 1 就是这个保护。

**这个摘要没防住什么？**
  没防"回复不是本人发的"。摘要是**内容完整性**校验，不是**身份认证**。
  任何能构造出 {"approved": true, "digest": ...} 的人或程序都能通过校验。
  真实系统里还需要：审批人身份、权限、时间戳、审计日志，甚至双人复核。
  —— 这也是第 8 章正文里那句"摘要不替代用户身份认证"的含义。
""")


if __name__ == "__main__":
    run(main, need_api_key=False)
