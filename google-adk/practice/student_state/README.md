# 学生题：购物车看似变了，为什么重新读取后又没了？

先修：第 3 章的 State 最小模型、第 4 章的 ToolContext。

只修改 `solution.py` 的 `add_item`。商品、库存、价格和返回协议已给定；
你要使购物车的变化进入真实 ADK `State` 的 delta，随后由验收器提交事件。
本题不调用模型，也不需要密钥。

从仓库根目录运行：

```bash
uv run python google-adk/practice/student_state/verify.py
```

初始骨架会以 `NotImplementedError` 失败，这是等待你实现的作业，不是环境故障。
不要修改 `verify.py`，它会独立检查以下结果：

1. 苹果数量从 1 加到 3，再加入两瓶牛奶，总价是 32 元。
2. 原购物车容器保持不变，`state_delta` 包含完整的新购物车。
3. 提交事件前服务中的状态未变，提交后重新读取才得到新值。
4. 库存不足、未知商品、非法数量都不修改状态；另一个会话不受影响。

分层提示：先观察 `type(tool_context.state)`；再比较嵌套字典原地修改与
`state["cart"] = 新字典`；最后问自己是否在验证失败之前已经改变了旧容器。

完成后再读参考实现 [`../c4_2.py`](../c4_2.py)。可单独检查参考答案：

```bash
uv run python google-adk/practice/student_state/verify.py --reference
```

这个选项不会替你填写作业。提交后请用自己的话解释：本地值改变、delta 产生、
事件提交、重新读取分别说明了什么；四者为什么不能相互替代。
