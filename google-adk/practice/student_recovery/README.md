# 学生题：进程恢复后，又执行了一次归档

先修：第 9 章的恢复边界和幂等键，以及 Python 的 SQLite 基础。

场景：归档已提交，但上游尚未记录完成便退出。恢复时，同一个业务请求会再次送达。
请只完成 `solution.py` 的 `archive_once`，让重复请求读回已有结果，同时拒绝
“同一个幂等键、换一份正文”这样的冲突。全部使用本地 SQLite，不调用模型。

从仓库根目录运行：

```bash
uv run python google-adk/practice/student_recovery/verify.py
```

初始骨架会失败并显示 `NotImplementedError`。验收器独立建表并检查：

1. 两个不同 PID 的子进程在准备就绪后提交同一个新请求。
2. 只有一次实际写入，最终只有一个版本和一条业务回执。
3. 两个进程退出后，另一个进程再次投递仍读回同一版本。
4. 同键但正文、文件名或条目数不同，必须明确抛出 `ValueError`；已存数据不变。

分层提示：先明确什么组成“同一个请求”；再考虑两个进程都先查到“没有”会怎样；
最后把检查、正文写入和回执写入放进同一个事务，使用数据库的约束处理竞争。

完成后对照 [`../c9_5.py`](../c9_5.py)。可独立验证参考答案：

```bash
uv run python google-adk/practice/student_recovery/verify.py --reference
```

这是恢复之后的**外部副作用去重**练习，不是 ADK checkpoint 的实现。
真实 ADK 跨进程恢复见 [`../../workflow_example/README.md`](../../workflow_example/README.md)。
验收通过后还要回答：如果正文在对象存储、回执在数据库，本题的单库事务还成立吗？
你需要哪一方提供幂等接口，怎样发现和补偿“正文成功、回执失败”的情况？
