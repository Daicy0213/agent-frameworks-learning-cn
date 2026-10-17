# 附录 · ADK 术语表

> 用法：读某一章卡住时，先在这里查词，再回到首次出现的章节看上下文。
> 术语首现格式统一为：**中文名（English，`代码名`）**。

## 一、运行时

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 智能体 | Agent，`LlmAgent` | 描述"我是谁、听什么指令、能用什么工具" | 第 1 章 |
| 运行器 | Runner，`Runner` | 驱动"模型思考 → 工具执行 → 再思考"的循环 | 第 1 章 |
| 会话 | Session，`Session` | 一次对话的完整档案，由 `app_name + user_id + session_id` 定位 | 第 1 章 |
| 事件 | Event，`Event` | 运行中的一个动作：发言、工具调用、工具返回、状态变更 | 第 1 章 |
| 事件流 | Event Stream | `run_async()` 逐条产出的 `Event` 序列 | 第 1 章 |
| 最终响应 | final response，`is_final_response()` | 标记本轮最终答复；子节点也会产生最终事件 | 第 1 章 |
| 调用 ID | `invocation_id` | 会话中的一次执行 | 第 9 章 |
| 运行 ID | `run_id` / `node_info.path` | 一次执行中的一步，默认由节点名和调用计数生成 | 第 8、9 章 |
| 检查点 | checkpoint | 已完成的节点结果，用于恢复时回放 | 第 9 章 |
| 回放 | replay | 恢复时不重跑已完成节点，直接使用检查点结果 | 第 9 章 |

## 二、Agent 配置

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 指令 | instruction | 人设、行为准则、输出要求；支持 `{key}` 状态插值 | 第 1、2 章 |
| 描述 | description | 写给调度者看的岗位简介，决定路由 | 第 3 章 |
| 输出键 | `output_key` | 把最终回复写入 `session.state` | 第 3 章 |
| 输出模式 | `output_schema` | 输出结构声明；供应商约束支持须实测，仍需校验业务事实 | 第 3 章 |
| 生成配置 | `generate_content_config` | 温度、最大输出长度等 | 第 3 章 |
| 对话模式 | `mode="chat"` | 读会话历史，可被转移 | 第 8 章 |
| 单轮模式 | `mode="single_turn"` | 读上游节点传入的 `node_input` | 第 8 章 |

## 三、工具与多智能体

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 函数工具 | `FunctionTool` | 把普通 Python 函数变成模型可调用的工具 | 第 4 章 |
| 工具上下文 | `ToolContext` | 工具读写 Session 状态的通道 | 第 4 章 |
| 智能体工具 | `AgentTool` | 把另一个 Agent 当函数调用，调用完控制权返回 | 第 4 章 |
| 子智能体 | `sub_agents` | 父 Agent 可转移任务的下级 Agent | 第 5 章 |
| 转移 | `transfer_to_agent` | 把任务和控制权一起交给子 Agent | 第 5 章 |
| 串行编排 | `SequentialAgent` | 按列表顺序依次执行 | 第 5 章迁移深读 |
| 并行编排 | `ParallelAgent` | 同时执行多个分支，结果写不同 key | 第 5 章迁移深读 |
| 循环编排 | `LoopAgent` | 按条件重复，`escalate` 主动退出 | 第 5 章迁移深读 |
| 模型上下文协议 | MCP，`McpToolset` | 接入外部 MCP Server 的工具集 | 第 4 章 |
| 长时任务 | `LongRunningFunctionTool` | 先挂起、完成后回填结果的工具 | 第 4 章 |

## 四、记忆

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 状态 | State，`session.state` | 按作用域组织的键值数据；持久性取决于存储服务 | 第 3 章 |
| 用户级状态 | `user:` 前缀 | 同一用户跨会话共享 | 第 6 章 |
| 应用级状态 | `app:` 前缀 | 该应用下所有用户共享 | 第 6 章 |
| 临时状态 | `temp:` 前缀 | 仅当前一轮，不落盘 | 第 6 章 |
| 记忆服务 | `MemoryService` | 已写入且可检索的记忆；内存实现重启会丢失 | 第 6 章 |
| 预加载记忆 | `PreloadMemoryTool` | 每轮自动召回相关记忆 | 第 6 章 |
| 持久会话 | `DatabaseSessionService` | 把会话写进 SQLAlchemy 数据库 | 第 6 章 |
| 单机会话 | `SqliteSessionService` | 单文件 SQLite 会话存储 | 第 9 章 |
| 产物 | Artifact，`ArtifactService` | 带版本管理的文件存储 | 第 6 章 |

## 五、回调与观测

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 生命周期回调 | `before_agent_callback` 等六种 | 在关键节点插入逻辑；返回 `None` 放行，返回对象的语义依钩子而定；after_agent 追加事件 | 第 7 章 |
| 模型错误回调 | `on_model_error_callback` | 模型异常时给出兜底响应 | 第 7 章 |
| 工具错误回调 | `on_tool_error_callback` | 工具异常时给出结构化结果 | 第 7 章 |
| 插件 | Plugin，`BasePlugin` | 应用级的回调集合 | 第 7 章 |
| 评估集 | evalset | 期望的交互剧本，用于回放打分 | 第 10 章 |
| 轨迹指标 | `tool_trajectory_avg_score` | 工具调用序列与期望的匹配度 | 第 10 章 |
| 回答指标 | `response_match_score` | 最终回答与参考答案的相似度 | 第 10 章 |

## 六、动态工作流

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 工作流 | `Workflow` | 声明式组织节点与边 | 第 5 章 |
| 节点 | `@node` | 把函数登记为框架可调度的节点 | 第 8 章 |
| 运行节点 | `ctx.run_node()` | 调用子节点并取回返回值（调用-返回） | 第 8 章 |
| 节点输入 | `node_input` | 上游显式传入的数据 | 第 8 章 |
| 输出归属 | `node_info.output_for` | 输出属于哪个节点路径；不含 `/` 指向根 | 第 8 章 |
| 恢复重跑 | `rerun_on_resume` | 父节点恢复时重新进入函数体 | 第 8、9 章 |
| 人工输入 | `RequestInput` | 请求人工确认并使流程暂停 | 第 9 章 |
| 重试配置 | `RetryConfig` | 显式声明重试次数与退避 | 第 9 章 |
| 尝试计数 | `ctx.attempt_count` | 从 1 开始的尝试序号 | 第 9 章 |
| 批并发上限 | `max_parallel_workers` | 只约束本批次，不等于 API 配额 | 第 8 章 |

## 七、命令行

| 命令 | 作用 | 首次出现 |
|---|---|---|
| `adk run <agent_dir>` | 终端运行单个 Agent | 第 2 章 |
| `adk web <agents_dir>` | 带 Web UI 的调试服务 | 第 2 章 |
| `adk api_server <agents_dir>` | 纯 HTTP API 服务 | 第 2 章 |
| `adk eval <module> <evalset>` | 用评估集回放并打分 | 第 10 章 |

## 八、检索、Skills 与工程边界

| 术语 | 英文 / 代码名 | 一句话 | 首次出现 |
|---|---|---|---|
| 上下文压缩 | EventsCompactionConfig | 用摘要替代部分历史输入；不保证事实无损 | 第 11 章 |
| 可信身份 | Principal | 宿主认证后绑定的用户/租户/角色；不是模型参数 | 第 12 章 |
| 幂等冲突 | idempotency conflict | 相同 key 对应不同请求，必须拒绝而非复用旧成功 | 第 12 章 |
| 检索增强生成 | RAG | 先找依据，再约束回答和引用 | 第 13 章 |
| 文档片段 | chunk / chunk_id | 可定位到文档、版本和段落的最小检索单元 | 第 13 章 |
| 召回率 | Recall@k | 前 k 个结果覆盖多少应命中的证据 | 第 13 章 |
| 首条命中排序 | MRR | 首个相关结果名次倒数的平均值 | 第 13 章 |
| 技能包 | Skill / SKILL.md | 描述、操作指引和资源组成的可复用任务流程 | 第 14 章 |
| 技能工具集 | SkillToolset | 通过工具按需把 Skill 内容送入模型上下文 | 第 14 章 |
| 渐进加载 | progressive disclosure | 模型先见摘要，再见正文/资源；不等于延迟读磁盘 | 第 14 章 |
