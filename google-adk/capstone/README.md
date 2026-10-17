# Capstone：售后 Agent 工程验收

这是一套真实的单机售后应用。HTTP 请求通过演示身份认证后，由 ADK Runner 调用业务工具，Session 与退款账本分别存入 SQLite。默认模型是确定性协议替身，方便零费用重现错误；在线模式替换为 DeepSeek。

## 先运行再看实现

从仓库根目录开始：

```bash
cd google-adk
uv run --project .. python -m capstone.verify
# 可选：两个真实模型请求，每次最多 4 次 LLM 调用
uv run --project .. --env-file ../.env python -m capstone.verify --backend deepseek
```

默认验收包含：可信身份/租户、伪造与过期审批、金额校验、相同 key 不同请求；第一个 HTTP 进程登记退款后退出，第二个进程恢复历史并重试；最终账本只有一行。`--with-server` 作为兼容参数保留，现在默认就运行服务验收。

上述默认 HTTP 验收直接运行联合路径（同一 Agent、同一 Session 数据库、同一退款账本）：真实 `SkillToolset` 加载本工程的退款 Skill → `LexicalIndex` 按当前身份租户检索政策 → 调用同一 `RefundStore`。viewer 即使加载了 Skill、读到退款政策和持有审批号，也不能写入；agent 使用匹配审批才写入。联合路径使用离线模型，不能证明真实模型会自行选对 Skill。在线冒烟使用同一服务的 `--business-only` 配置（查订单 → 退款），每个请求至多 4 次模型调用；第 13、14 章另提供 RAG/Skills 真实模型轨迹。

## 实现地图

| 文件 | 职责 | 对应课程 |
|---|---|---|
| `server.py` | HTTP 身份绑定、会话定位与 Runner | 02、06、11、12 |
| `agent.py` | 工具签名、离线/在线模型选择 | 03、04 |
| `store.py` | 审批、事务、请求指纹、幂等账本 | 09、12 |
| `knowledge.py` | RAG/Skill 与业务工具联合验收 | 13、14 |
| `skills/` | 本项目的退款操作指引，不授予权限 | 14 |
| `verify.py` | 真实 HTTP、进程重启、事件与副作用断言 | 10、15 |

## 数据与凭据边界

- `sessions.sqlite` 保存 ADK 会话；`business.sqlite` 保存订单、审批和退款，两者不是同一数据责任。
- `demo-alice/demo-viewer/demo-bob` 是本机演示 token。服务只监听 127.0.0.1；公网部署必须换为真实 IdP、密钥托管和限流。
- 验收夹具调用 `issue_approval` 模拟可信人工入口，未提供审批 UI；交互式暂停与恢复见第 09 章。审批签发不注册为 Agent 工具。审批绑定用户、租户、订单、金额、有效期，并在写入退款的事务内消费。
- 金额单位为分，示例登记的是本地账本，没有执行真实资金转移。SQLite 事务不覆盖未来接入的支付渠道，渠道仍需幂等与对账。
- 默认验证创建临时目录，退出时关闭自己启动的服务并清理数据；不操作现有 Docker 容器。

## 怎样继续做毕业练习

先预测并新增“过期政策 / 不可退款订单 / 审批金额不符”的反例，再做实现。提交事件、账本和验收结果。质量评估分别使用 [官方 CLI](../official_eval_example/README.md) 与 [售后回归集](../eval_example/README.md)；不要把协议验收通过写成真实模型质量已通过。

## 本次在线冒烟

2026-10-17 的两次业务请求共发生 5 次真实 DeepSeek 模型调用。服务重启后 Session 仍有历史，重试返回原退款凭证，账本仅一行。精简证据见 [online_smoke_report.json](online_smoke_report.json)。这是正常请求与重复请求的冒烟，不是完整在线回归；完整 Skill/RAG HTTP 链路当前通过的是离线模型机制验收。
