"""独立练习验收；示范 verify 不会替你完成练习。"""
from .business import Principal
from .exercise import authorize_exchange


def main() -> None:
    approved = Principal("shop-a", "approver", frozenset({"A-100"}))
    assert authorize_exchange(approved, "shop-a", "A-100")
    assert not authorize_exchange(approved, "shop-b", "A-100")
    assert not authorize_exchange(approved, "shop-a", "A-999")
    assert not authorize_exchange(Principal(), "shop-a", "A-100")
    assert not authorize_exchange(Principal(role="approver"), "shop-a", "A-100")
    print("业务授权练习通过；接着添加 exchange-triage Skill 并收集真实 Runner 轨迹。")


if __name__ == "__main__":
    main()
