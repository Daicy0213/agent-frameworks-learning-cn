# 附录 C · A2A 与跨 Agent 互通

> 本附录只讲概念和最小代码，**不在本教程中运行**：A2A 需要额外依赖，且默认场景需要启动两个独立服务。当前环境与主线路只使用 DeepSeek。

## 1. A2A 解决什么问题

MCP 解决的是"Agent 如何调用工具"；**A2A（Agent-to-Agent）解决的是"一个 Agent 如何调用另一个独立部署的 Agent"**。

| 场景 | 适合的机制 |
|---|---|
| 同一个进程里拆分职责 | `sub_agents` / `AgentTool`（第 5 章） |
| 跨语言、跨团队、跨服务调用 | **A2A** |
| 调用外部工具集 | MCP（第 4 章） |

一句话：**A2A 把"另一个 Agent"变成一个可发现的远程服务**，双方通过 Agent Card 描述能力，通过 HTTP 交换消息。

## 2. 所需依赖

A2A 是可选能力，需要安装：

```bash
uv add "google-adk[a2a]"
```

对应的包是 `a2a-sdk`。不安装时，导入相关模块会报：

```text
ModuleNotFoundError: No module named 'a2a'
```

## 3. 服务端：把 Agent 暴露成 A2A 服务

```python
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

agent = Agent(
    name="analysis_agent",
    model=...,
    instruction="...",
    description="负责数据分析的远程 Agent",
)

# 生成一个 Starlette 应用，可由 uvicorn 启动
app = to_a2a(agent, host="localhost", port=8000)
```

调用方通过 `http://localhost:8000` 上的 Agent Card 发现能力。

## 4. 客户端：把远程 Agent 当成子 Agent

```python
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

remote = RemoteA2aAgent(
    name="remote_analysis",
    agent_card="http://localhost:8000/.well-known/agent-card.json",
    description="远程数据分析 Agent",
)

local = Agent(
    name="coordinator",
    model=...,
    instruction="需要数据分析时把任务交给 remote_analysis。",
    sub_agents=[remote],
)
```

`RemoteA2aAgent` 也接受 Agent Card 对象或本地文件路径。

## 5. 与本教程其他章节的关系

| 本地机制 | A2A 对应 |
|---|---|
| `sub_agents` 转移 | 远程 Agent 作为子 Agent |
| `AgentTool` 调用-返回 | 远程 Agent 作为工具（取决于封装方式） |
| `description` 路由 | Agent Card 的能力描述 |
| 本地 401/超时 | 远程调用的鉴权、超时、重试 |

## 6. 为什么本教程不运行它

1. **需要额外依赖**，会改变锁文件；
2. **需要两个独立服务**，教学内容会从"框架使用"偏移到"服务编排"；
3. **鉴权与网络安全**需要单独一章，当前环境没有可用的身份提供方。

## 7. 上生产前必须回答的问题

- [ ] 远程 Agent 的身份如何认证？调用方如何授权？
- [ ] Agent Card 暴露了哪些能力？是否泄露内部信息？
- [ ] 超时、重试、熔断、幂等如何处理？
- [ ] 远程 Agent 返回的内容是否按"不可信输入"处理（间接注入）？
- [ ] 跨服务追踪（trace id）如何透传？
- [ ] 数据合规：请求和响应会经过哪些地区与系统？

> ⚠️ **A2A 放大了权限问题。** 一个能被远程调用的 Agent，等于一个对外暴露的接口；先按第 12 章做威胁模型，再考虑接入。

## 8. 参考

- ADK A2A 文档：<https://adk.dev/a2a/>
- A2A 协议：<https://a2a-protocol.org/>
