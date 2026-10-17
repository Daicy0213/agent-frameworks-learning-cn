# 附录 B · 排错手册

> 用法：先按报错关键字定位，再看"原因"和"处理"。每条都来自本教程实际运行中踩过的坑。

## 一、指令与状态

| 现象 | 原因 | 处理 |
|---|---|---|
| `KeyError: Context variable not found: user_level` | `instruction` 里用了 `{user_level}`，但 Session 状态没有这个键 | 初始化状态；或把确实可选的字段写成 `{user_level?}`（缺失时为空字符串） |
| `{key}` 原样出现在提示词里 | 键名不是合法标识符，ADK 不会替换 | 只用 `name`、`user:name`、`app:name`、`temp:name` 这类合法名 |
| 改了状态但下一轮没生效 | 直接修改了 `get_session()` 返回的副本 | 用 `tool_context.state[...] = ...`，或 `append_event(session, Event(actions=EventActions(state_delta=...)))` 提交 |
| 多轮对话"失忆" | 换了 `session_id`，或用了 `InMemorySessionService` 且进程重启 | 复用同一 `session_id`；生产改用持久化实现 |

## 二、工作流与恢复

| 现象 | 原因 | 处理 |
|---|---|---|
| `This is not supported because chat-mode agents rely on conversational history...` | 把 `mode="chat"` 的 Agent 接在其他节点后面 | 改成 `mode="single_turn"`，让它读 `node_input` |
| 恢复后模型被重复调用 | 父函数里的模型调用没有登记为节点，恢复时被重跑 | 把模型调用放进 `@node` 叶子节点 |
| 已完成节点在恢复后执行计数变成 2 | 父节点设置了 `rerun_on_resume=True`，且副作用写在了父函数里；恢复时父函数会重入 | 父函数只做编排，副作用放独立叶子节点；必须重入时保证父函数幂等 |
| 流程返回 `None`，被当成失败 | 暂停同样没有根输出 | 检查 `pending_input()` / 待处理请求事件 |
| 只写 `RetryConfig()`，副作用执行了 5 次 | 漏写 `max_attempts`，默认预算就是 5 次 | 显式写 `RetryConfig(max_attempts=1)` 或明确次数 |
| 超时后数据库里仍有写入 | 超时不会撤销已提交的外部写入 | 业务幂等键 + 事务边界，不能只靠超时 |

## 三、工具与 MCP

| 现象 | 原因 | 处理 |
|---|---|---|
| `ImportError: cannot import name 'MCPToolset'` | 版本已弃用旧名，或没装 `mcp` | 用 `from google.adk.tools import McpToolset`；`uv sync` 安装 `mcp` |
| `StdioServerParameters is not recommended` | 旧连接参数写法 | 用 `StdioConnectionParams(server_params=...)` |
| MCP Server "进程启动失败" | `command`/路径相对于错误的工作目录 | 用 `sys.executable`，路径相对启动目录 |
| Agent 级 `after_tool_callback` 报 `unexpected keyword argument 'tool_response'` | 第 4 个参数名写成了 `result` | Agent 级签名是 `(tool, args, tool_context, tool_response)` |
| Plugin 级 `after_tool_callback` 报 `unexpected keyword argument 'result'` | 套用了 Agent 级的参数名 | Plugin 级签名是 `(*, tool, tool_args, tool_context, result)` |
| 工具被拦截但仍有副作用 | 只在回调里检查，工具本体没复核 | 工具本体再检查一次权限、参数、审批 |
| 工具返回字符串，模型理解不稳定 | 返回了自由文本 | 返回结构化 `dict`，错误也结构化 |

## 四、回调与插件

| 现象 | 原因 | 处理 |
|---|---|---|
| 插件报 `NoneType can't be used in 'await' expression` | 插件钩子写成了同步函数 | 全部改成 `async def` |
| 回调返回 `None` 后仍然短路 | 误以为 `None` 表示拒绝 | 返回 `None` = 放行；返回对象的作用依钩子而定；after_agent 会追加事件 |
| 父 Agent 的护栏没拦住子 Agent | 回调不会自动继承给子 Agent | 给需要保护的每个 Agent 单独挂，或用应用级插件 |
| `on_model_error_callback` 没触发 | 异常被更外层的重试吞掉，或没有抛出 | 用假模型验证回调本身；确认异常类型 |

## 五、会话与服务

| 现象 | 原因 | 处理 |
|---|---|---|
| `SessionNotFoundError` / HTTP 404 | 没先建会话，或 `session_id` 拼错 | 先 `POST /apps/{app}/users/{user}/sessions` |
| 服务重启后会话丢失 | 显式使用内存或数据库路径/挂载改变 | `--session_service_uri` 指向 SQLite 或数据库 |
| SQLite URL 打不开（Windows） | 用了 Git Bash 的 `/d/...` 路径 | 用相对路径，如 `sqlite+aiosqlite:///./adk_sessions.db` |
| `/run_sse` 没有打字机效果 | 请求体没传 `"streaming": true` | 加上该字段；仍是事件级流式时检查 `RunConfig` |
| `adk web` 找不到 Agent | 目录层级指错，或缺少 `root_agent` / 入口文件 | 传"每个子目录一个 Agent"的父目录；确认 `agent.py` 中定义了 `root_agent` |
| 401 / 认证失败 | `DEEPSEEK_API_KEY` 没注入进程 | 用 `--env-file` 或先导出环境变量 |

## 六、异步与并发

| 现象 | 原因 | 处理 |
|---|---|---|
| 逐项 `await` 后并没有更快 | `async` 不等于并行 | 用 `asyncio.gather` 或 `parallel_worker` |
| CPU 密集任务没有加速 | `asyncio` 是单线程协作式调度 | 换多进程或线程池 |
| 并发峰值超过预期 | 批次上限会随嵌套叠乘 | 另做全局限流；`max_parallel_workers` 只管本批次 |
| 取消后模型仍在生成 | 客户端断开不等于服务端取消 | 显式取消任务，设置单请求超时 |

## 七、评估

| 现象 | 原因 | 处理 |
|---|---|---|
| 单条案例通过就发布 | 样本量不足 | 用完整集检查类别覆盖与阈值；案例数本身不能证明质量 |
| 门禁永远为绿 | 阈值或判定写错 | 故意制造一次失败，确认课程门禁退出非零；官方 CLI 还要读取 case 的评估状态 |
| 文案相似度很高但工具调错 | 只看了回答指标 | 轨迹指标必须单独设阈值 |
| 评估结果波动大 | 温度高、案例少 | 降低温度；增加案例与重复次数 |

## 八、工程扩展

| 现象 | 原因 | 处理 |
|---|---|---|
| 流式答案显示两遍 | 增量和完整事件全部追加 | partial 只用于预览，完整结果替换预览，并按 author/invocation 隔离 |
| 调用预算到了却仍有副作用 | 预算不是事务回滚 | 看已执行工具与账本，重试使用原幂等键 |
| 检索能搜到但引用不合法 | 旧版本、跨租户或编造 chunk_id | 先做可信范围过滤，再核对引用属于本次证据 |
| 改了政策后仍用旧索引 | 语料/分块版本不匹配 | 校验 digest，重建索引并运行固定检索集 |
| 近义问法搜不到 | 词法基线不理解同义词 | 保留失败案例，再评估 BM25/向量/混合检索，不随意降低标准 |
| Skill 文件在磁盘上但模型看不到正文 | 尚未调用 load_skill | 查看模型请求快照与工具事件，不只检查文件存在 |
| 加载 Skill 后仍不能退款 | 工具仍校验可信身份/审批 | 检查服务端授权，不能让 Skill 自行授予权限 |
| 官方 adk eval 与主项目依赖冲突 | evaluation extra 的依赖范围不同 | 按 official_eval_example 的隔离环境运行，不修改主环境版本 |
| 冒烟集没有安全样本却显示绿色 | 把“未评估”当作通过 | 安全指标显示 null，完整覆盖之前 release_ready=false |
