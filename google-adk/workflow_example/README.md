# 第八章综合案例：可恢复的技术内容审核

本工程是第八章 Notebook 实际运行的源代码。它将真实 DeepSeek 写作、规则检查、有界并发、人工确认、SQLite 会话恢复和文件 Artifact 归档组合成同一流程。

## 文件职责

| 文件 | 职责 |
|---|---|
| `workflow.py` | 输入契约、模型节点、修改预算、审批摘要与业务编排 |
| `storage.py` | 独立业务 SQLite：调用次数、token 使用、归档回执和故障注入记录 |
| `run.py` | 启动独立进程、恢复 invocation、返回可检查的 JSON 报告 |
| `job.example.json` | 两项技术内容任务与已经核对的输入事实 |

`DatabaseSessionService` 保存执行事件；`FileArtifactService` 保存真实正文与版本；业务回执与 checkpoint 分开存储。两个工作节点最多同时运行，每项默认最多修改一次。

## 运行

在仓库根目录先执行 `uv sync`，配置 `.env` 中的 `DEEPSEEK_API_KEY`。随后进入 `google-adk` 目录：

```powershell
cd google-adk
uv run --project .. --env-file ../.env python -m workflow_example.run start --directory workflow_example/runs/demo --input workflow_example/job.example.json
```

`start` 真实调用模型。若报告是 `paused`，查看 `pending` 中的完整候选稿；若是 `needs_revision`，先处理检查意见。每个运行目录承载一个任务，重新启动新任务要选择新目录。

接受候选稿并注入一次归档完成后的故障：

```powershell
uv run --project .. --env-file ../.env python -m workflow_example.run approve --directory workflow_example/runs/demo --decision accept --fail-after-write
```

这一步保存 Artifact 和业务回执后主动失败，报告应是 `failed`，并包含 `ConnectionError` 故障事件。再启动第三个进程：

```powershell
uv run --project .. --env-file ../.env python -m workflow_example.run recover --directory workflow_example/runs/demo
```

最终报告应为 `archived`：模型响应数不增加、归档尝试为两次、业务回执只有一条、Artifact 版本只有 `[0]`。恢复使用同一 invocation，不重新提交审批。

普通接受不加 `--fail-after-write`；拒绝使用 `--decision reject`。`--mode offline` 替换内容后端以验证业务分支，恢复必须保持同一后端。Notebook 用临时目录执行，读回并保存结果后自动清理。

## 保障边界

- 输入快照和流程版本需要保持兼容；`run_id` 不等于外部业务幂等键。
- 规则检查证明格式、长度和术语合规，事实正确性仍需对照输入和审核全文。
- 审批摘要绑定候选稿内容，不代替身份认证；CLI 的接受/拒绝参数代表用户提供的决定。
- 本实验顺序启动各阶段，只有一个归档写入方。并发发布需要外部存储的原子条件写入或事务协调。
- 案例验证指定的“外部写入已完成、节点尚未完成”窗口，不声称覆盖所有存储故障点。
