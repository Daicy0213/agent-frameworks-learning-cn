# 练习、学生骨架与独立验收

**先补学生骨架，再运行独立验收，最后对照参考实现。** 直接运行答案能确认环境，不能证明你会独立解决同类问题。

## 学生题

| 学生题 | 先修 | 验收重点 |
|---|---|---|
| [State 提交](student_state/README.md) | 第 03、04 章 | 真实 ToolContext、嵌套复制与顶层赋值、delta、提交前后、会话隔离 |
| [恢复后去重](student_recovery/README.md) | 第 09 章 | 不同 PID 的竞争、重投与异内容冲突、版本和回执 |
| [服务端权限](student_security/README.md) | 第 12 章 | 可信身份、角色与租户、资源归属；业务输入不能伪造身份 |

**以下命令从仓库根目录执行。** 先运行 `uv sync`。离线题不需要 `.env` 或密钥：

```bash
uv run python google-adk/practice/student_state/verify.py
uv run python google-adk/practice/student_recovery/verify.py
uv run python google-adk/practice/student_security/verify.py
```

未填写 TODO 时失败是预期行为。只修改各题 `solution.py`，不要改验收器。三题均可加 `--reference` 检查参考答案，这不会替你填入实现。

第 13、14 章另有扩展题：修改 `rag_example/exercise.py` 或 `skills_example/exercise.py` 后运行：

```bash
uv run --directory google-adk --project .. python -m rag_example.check_exercise
uv run --directory google-adk --project .. python -m skills_example.check_exercise
```

RAG 题改善基线漏召回，Skills 题补齐业务授权。它们与示范用 `verify` 分开，空骨架应失败。

## 参考实现

`c<章号>_<题号>.py` 对应当前章节。第 05 章重编后保留 `c5_4.py` 供旧接口迁移阅读。

| 文件 | 模型需求 | 关键验收 |
|---|---|---|
| `c1_1.py`、`c1_2.py` | DeepSeek | 真实模型接入与事件观察 |
| `c1_3.py` | 离线 | 用实际事件历史证明 app / user / session 隔离 |
| `c1_4.py` | DeepSeek；`--check` 离线 | 环境诊断与可解释错误 |
| `c3_2.py` | DeepSeek | 三类分诊输入、JSON / Pydantic 字段、VIP 与缺值规则 |
| `c3_3.py` | DeepSeek | JSON mode、日期与枚举、负责人和截止日期的事实一致性 |
| `c4_2.py` | 离线 | 真实 ToolContext / State；嵌套原地修改反例、事件提交正例 |
| `c4_3.py` | DeepSeek | 取数工具与 AgentTool 的职责 |
| `c5_4.py` | DeepSeek | 旧嵌套客服；声明式主线见 `graph_example/` |
| `c6_1.py`、`c6_2.py` | 离线 | 状态作用域、跨会话偏好与删除边界 |
| `c7_1.py` | 离线 | 输入护栏规则与反例 |
| `c7_2.py` | 离线 | 真实 Runner / 工具路径，可信身份、权限与幂等 |
| `c8_1.py`、`c8_2.py`、`c8_5.py` | 离线 | 编排、根输出归属、受限并发 |
| `c8_3.py`、`c8_4.py` | DeepSeek | 真实写作与修改路径 |
| `c9_1.py` 至 `c9_5.py` | 离线 | 人工确认、审批摘要、重试、故障策略、独立进程去重 |
| `c10_1.py` | 离线 | 评估集契约与报告 |
| `c11_1.py` | 默认离线；`--backend deepseek` 在线 | 真实本地 HTTP、`/run_sse` 文本增量与收尾 |
| `c12_1.py` | 离线 | 输入规则与日志脱敏 |
| `c12_2.py` | 离线 | 共用 Capstone 业务存储，验证审批、权限与幂等 |

普通脚本可从根目录运行，Python 自动加入脚本目录用于导入，不需要先切到 `practice/`：

```bash
uv run python google-adk/practice/c1_3.py
uv run python google-adk/practice/c4_2.py
uv run python google-adk/practice/c9_5.py
uv run python google-adk/practice/c11_1.py
uv run python google-adk/practice/c1_4.py --check
```

在线练习在根目录 `.env` 配置密钥后显式注入：

```bash
uv run --env-file .env python google-adk/practice/c3_2.py
uv run --env-file .env python google-adk/practice/c3_3.py
uv run --env-file .env python google-adk/practice/c11_1.py --backend deepseek
```

`_common.py` 提供共享模型与运行函数。“启动 Runner”“启动 HTTP 服务”均不等于调用远程模型。

## 通过之后再问什么

1. **证据在哪里？** 区分内存值、State delta、提交后数据、模型回复和业务账本。
2. **反例能失败吗？** 删掉必要校验后，至少一个验收应失败，否则可能没测到目标机制。
3. **换输入还成立吗？** 增加未见过的输入，不仅复制示例中的订单号、字符串或输出。
4. **还有什么没验证？** 离线模型证明调用协议，不能证明真实模型始终选对工具、理解材料或正确引用。

基础回归：

```bash
uv run python -m pytest google-adk/tests/test_course_foundations.py google-adk/tests/test_practice_foundations.py -q
```

回归检查参考程序和 Notebook 离线实验，并确认未实现的 TODO 会明确失败。学生答案仍需通过自己的验收器。第 09 章真实 ADK 跨进程恢复见 [workflow_example](../workflow_example/README.md)；恢复学生题聚焦外部写入去重，不实现 checkpoint 本身。
