# Agent 框架教学：Google ADK 与 LangChain / LangGraph

这套课程面向**会写 Python、了解 LLM 基本原理、尚未学过 ADK** 的读者。目标是从跑通一个 Agent，逐步走到能设计数据契约、诊断失败、检验模型质量，并交付可验收的服务。

课程使用锁定版本的真实框架。机制实验采用确定性的本地模型或普通节点；观察真实生成行为时使用 DeepSeek。**离线验收证明协议与代码路径，在线评估检验目标模型的表现，二者都需要。**

## 能力路线与毕业标准

先读 [00-框架全景与选型对比](00-框架全景与选型对比.ipynb)，再按阶段前进。阶段验收要求修改或解释新案例，不能只以原例运行成功作为学会的证据。

| 阶段 | 章节 | 完成后能独立做什么 |
|---|---|---|
| 运行一个 Agent | [01 快速上手](google-adk/01-初识ADK-快速上手.ipynb) → [02 工程与 CLI](google-adk/02-ADK工程骨架与CLI.ipynb) | 建立工程，解释 Agent / Runner / Session / Event，定位失败层次 |
| 建立数据契约 | [03 Agent、State 与输出](google-adk/03-Agent详解-指令与结构化输出.ipynb) → [04 工具](google-adk/04-工具系统.ipynb) | 提交 State 增量；分别验证 JSON、字段、业务事实；调用并关闭 MCP 工具 |
| 组织流程与数据 | [05 声明式 Workflow](google-adk/05-多智能体与工作流.ipynb) → [06 状态与记忆](google-adk/06-会话-状态与记忆.ipynb) → [07 回调与观测](google-adk/07-回调与可观测性.ipynb) | 运行顺序、条件、汇合；分清读取方式、共享范围和持久化；用事件验证回调行为 |
| 处理运行中的变化 | [08 动态工作流](google-adk/08-动态工作流基础.ipynb) → [09 恢复与运行保障](google-adk/09-动态工作流-恢复与运行保障.ipynb) | 编写有界循环与并发；验证人工确认、重入、回放、重试和业务幂等 |
| 检验并提供服务 | [10 评估](google-adk/10-评估与测试工程.ipynb) → [11 流式与服务](google-adk/11-流式输出与服务化.ipynb) → [12 安全与鉴权](google-adk/12-安全与鉴权.ipynb) | 区分机制测试与质量评估；正确消费文本增量；在服务和工具边界验证可信身份与审批 |
| 扩展并综合交付 | [13 RAG](google-adk/13-RAG集成与检索评估.ipynb) → [14 Skills](google-adk/14-Skills工程与渐进加载.ipynb) → [15 综合工程](google-adk/15-Capstone-售后Agent工程验收.ipynb) | 分开评估检索与生成；按需加载技能；让检索、技能和退款工具共用业务授权边界 |

05 主线使用当前声明式 `Workflow`，旧 `SequentialAgent`、`ParallelAgent`、`LoopAgent` 放在迁移深读。08 先运行普通 Python 与最小 ADK 程序，再解释动态调度术语。09 的机制部分不需要密钥，真实模型综合运行另有明确入口。

毕业至少需要五类证据：

1. **解释**：为未见过的请求画出数据、控制权、状态提交和外部写入路径。
2. **实现**：不看答案完成 State、恢复、权限学生题，通过独立验收。
3. **排错**：注入缺失状态、错误检索、模型异常或重复请求，定位并验证修复。
4. **运行**：走真实 HTTP / Runner / 工具路径；服务重启后历史仍在，重复退款只产生一笔业务记录。
5. **评估**：用未参与调参的案例检查检索、引用、工具轨迹和业务结果，明确离线实验没有证明的模型能力。

综合工程边界见 [capstone/README.md](google-adk/capstone/README.md)。课程验收说明所列案例成立；实际部署还需按目标环境补齐身份提供方、密钥管理、存储运维和质量门槛。

本轮修改范围与测试证据见 [课程改造与验证记录](google-adk/课程改造与验证记录.md)。

## 环境与运行约定

**以下命令均从仓库根目录开始执行。** 使用 Python 3.12 与 [uv](https://docs.astral.sh/uv/)，依赖以 `pyproject.toml` 和 `uv.lock` 为准。

```bash
uv sync
uv run jupyter lab
```

主要锁定版本：`google-adk 2.6.3`、`langchain 1.2.15`、`langgraph 1.1.10`、`litellm 1.96.2`。遇到 API 差异先同步环境，再检查对应版本。

离线实验不需要 `.env`：

```bash
uv run python -m pytest google-adk/tests google-adk/eval_example/tests -q
uv run python google-adk/mcp_example/verify.py
uv run --directory google-adk --project .. python -m graph_example.workflow
uv run --directory google-adk --project .. python -m runtime_example.verify
uv run --directory google-adk --project .. python -m rag_example.verify
uv run --directory google-adk --project .. python -m skills_example.verify
uv run --directory google-adk --project .. python -m capstone.verify
```

`--directory google-adk` 只为该命令设置工作目录，不用手动切目录。Capstone 验收会启动临时本地 HTTP 服务、验证两次独立进程运行，再清理临时数据。

真实 DeepSeek 示例需要根目录 `.env` 中的 `DEEPSEEK_API_KEY`。首次配置可复制 `.env.example`；已有文件时直接编辑。不要把密钥写入代码、Notebook 或输出。

```powershell
Copy-Item .env.example .env
# 编辑 .env 后启动
uv run --env-file .env jupyter lab
```

Linux / macOS 可用 `cp .env.example .env`。普通脚本与模块的运行方式：

```bash
uv run --env-file .env python google-adk/practice/c3_3.py
uv run --directory google-adk --project .. --env-file ../.env python -m capstone.verify --backend deepseek
```

真实模型会产生费用且结果可能变化。按章内预算逐个运行，记录模型、输入、指标和失败案例。第 10 章分别提供本地评估工具与官方 `adk eval` 路线，安装与入口见章内说明。

## 怎么读与练

按“已会与目标 → 问题 → 先猜 → 最小实验 → 证据 → 反例 → 迁移”阅读。先写预测，再执行；观察断言、事件与存储结果，不只看模型最后一句话。

- **主线**形成完整运行路径；**深读**提供实现细节、框架对照和旧接口迁移，不应提供后续主线必需变量。
- 已修改代码的旧 Notebook 输出会清除；你运行后产生的结果才是当前环境的证据。`offline` 标签标识可无密钥执行的机制实验。
- [练习目录](google-adk/practice/README.md) 区分 TODO 学生题、独立验收和参考答案。初始学生题失败是预期行为。
- 名词查 [术语表](google-adk/附录A-术语表.md)，失败查 [排错手册](google-adk/附录B-排错手册.md)；[A2A 附录](google-adk/附录C-A2A与跨Agent互通.md) 用于后续阅读。

## 工程索引

| 目录 | 用途 |
|---|---|
| `google-adk/agent_demo/` | 第 02 章 CLI 最小工程 |
| `google-adk/mcp_example/`、`openapi_example/` | 第 04 章工具协议与规格 |
| `google-adk/graph_example/` | 第 05 章声明式顺序、条件、汇合 |
| `google-adk/workflow_example/` | 第 09 章人工确认、独立进程恢复与归档 |
| `google-adk/eval_example/`、`official_eval_example/` | 第 10 章本地质量检查与官方评估 |
| `google-adk/runtime_example/` | 第 11 章流式、调用预算与上下文 |
| `google-adk/rag_example/`、`skills_example/` | 第 13、14 章扩展与独立练习 |
| `google-adk/capstone/` | 第 15 章服务、Runner、持久化与业务工具联合验收 |
| `google-adk/practice/`、`tests/` | 练习参考、学生骨架和机制回归测试 |

LangChain / LangGraph 路线保留六章：[01 模型接入](langchain-langgraph/01-LangChain生态与模型接入.ipynb) → [02 LCEL](langchain-langgraph/02-LCEL与链式编排.ipynb) → [03 Agent 与工具](langchain-langgraph/03-Agent与工具调用.ipynb) → [04 图与状态](langchain-langgraph/04-LangGraph核心-图与状态.ipynb) → [05 持久化与人机协同](langchain-langgraph/05-持久化-流式与人机协同.ipynb) → [06 多智能体](langchain-langgraph/06-多智能体模式与生态对比.ipynb)。学过其中一套后再按主题对照，最后回到 00 章重新做选型判断。
