# Agent 框架深度教学：Google ADK vs LangChain / LangGraph

本仓库是一套**可执行的 Jupyter 教学笔记**，以教学视角系统讲解两大主流 Agent 开发框架：

- **Google ADK（Agent Development Kit）** —— Google 开源的智能体开发套件
- **LangChain / LangGraph** —— 生态最庞大的 LLM 应用框架与底层图编排引擎

所有代码示例均使用 **DeepSeek**（`deepseek-chat`）作为底层大模型，开箱即可运行。

---

## 📂 目录结构

```
agent-frameworks/
├── README.md                              ← 本文件
├── 00-框架全景与选型对比.ipynb              ← 建议从这里开始！
│
├── google-adk/                            【Google ADK 系列】
│   ├── 01-初识ADK-快速上手.ipynb
│   ├── 02-Agent详解与模型接入.ipynb
│   ├── 03-工具系统.ipynb
│   ├── 04-多智能体与工作流.ipynb
│   ├── 05-会话-状态与记忆.ipynb
│   ├── 06-回调-观测与部署.ipynb
│   ├── 07-动态工作流-Dynamic-agent-workflows.ipynb
│   ├── 08-动态工作流-恢复与运行保障.ipynb
│   ├── practice/                          ← 各章练习的参考实现（c1_* / c7_* / c8_*）
│   ├── eval_example/                      ← 第六章「评估」的完整可运行工程
│   └── workflow_example/                  ← 第八章独立进程综合工程
│
└── langchain-langgraph/                   【LangChain / LangGraph 系列】
    ├── 01-LangChain生态与模型接入.ipynb
    ├── 02-LCEL与链式编排.ipynb
    ├── 03-Agent与工具调用.ipynb
    ├── 04-LangGraph核心-图与状态.ipynb
    ├── 05-持久化-流式与人机协同.ipynb
    └── 06-多智能体模式与生态对比.ipynb
```

## ⚙️ 环境配置

本项目使用 **[uv](https://docs.astral.sh/uv/)** 管理环境与依赖（`pyproject.toml` + `uv.lock`），在 **Python 3.12** 下验证通过。

### 1. 安装依赖

```bash
# 安装 uv（如已安装可跳过）：https://docs.astral.sh/uv/getting-started/installation/
# 一键创建 .venv 并按 uv.lock 安装全部依赖
uv sync
```

> 本仓库验证时的版本：`google-adk 2.6.3`、`langchain 1.2.15`、`langgraph 1.1.10`、`langchain-openai 1.6.0`、`litellm 1.96.2`。
> ⚠️ 注意：`langchain 1.2.x` 需要 `langgraph >= 1.0`（0.x 会出现 `No module named 'langgraph._internal'` 报错）；同时 `langchain 1.2.15` 要求 `langgraph < 1.2.0`，因此锁定在 1.1.x。

### 2. 配置 DeepSeek API Key

代码通过环境变量读取密钥（**不要把密钥写进代码或 notebook**）。推荐复制 `.env.example` 为 `.env` 并填入密钥：

```bash
cp .env.example .env   # 然后编辑 .env 填入 sk-xxxxxxxx
```

启动时通过 `--env-file` 注入（见下文运行命令）。也可以手动设置环境变量：

```powershell
# Windows PowerShell（当前会话）
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxx"

# Windows（永久写入用户环境变量）
setx DEEPSEEK_API_KEY "sk-xxxxxxxx"
```

```bash
# Linux / macOS
export DEEPSEEK_API_KEY="sk-xxxxxxxx"
```

两个框架接入 DeepSeek 的方式对比（各章节会详细展开）：

| 框架 | 接入方式 | 关键代码 |
|---|---|---|
| **Google ADK** | 通过内置 **LiteLLM** 适配层（LiteLLM 原生支持 DeepSeek，自动读取 `DEEPSEEK_API_KEY`） | `LiteLlm(model="deepseek/deepseek-chat")` |
| **LangChain** | DeepSeek 提供 **OpenAI 兼容接口**，用 `ChatOpenAI` 改 `base_url` 即可 | `ChatOpenAI(model="deepseek-chat", base_url="https://api.deepseek.com")` |

### 3. 运行

```bash
# 注入 .env 中的密钥并启动 JupyterLab（uv 自动使用项目 .venv）
uv run --env-file .env jupyter lab

# 若已用其他方式设置好 DEEPSEEK_API_KEY，直接：
uv run jupyter lab
```

> 💡 **Mermaid 图表**：笔记中的架构图使用 Mermaid 语法，在 **VS Code**、**GitHub** 及较新版 **JupyterLab** 的 Markdown 预览中可直接渲染；纯 JupyterLab 经典界面可能显示为源码，属正常现象。

## 🧭 推荐学习路径

```mermaid
flowchart TD
    A["00 框架全景与选型对比<br/>（建立全局认知）"] --> B{"选择学习线路"}
    B --> C["Google ADK 线路<br/>01 → 02 → 03 → 04 → 05 → 06 → 07 → 08"]
    B --> D["LangChain / LangGraph 线路<br/>01 → 02 → 03 → 04 → 05 → 06"]
    C --> E["对照阅读：两大框架同主题章节互看<br/>（工具 vs 工具、多智能体 vs 多智能体……）"]
    D --> E
    E --> F["回到 00 章，重新理解选型决策"]
```

- **零基础**：先读 `00`，再任选一条线路顺序学习；
- **已有 LangChain 经验**：直接进 ADK 线路，每章末尾都有「与 LangChain 对照」小节；
- **已有 ADK 经验**：直接进 LangChain 线路，重点关注 `04`（LangGraph 图模型）——这是两个框架设计哲学差异最大的地方。
- **ADK 2.x 动态编排**：先读 [07-动态工作流基础](google-adk/07-动态工作流-Dynamic-agent-workflows.ipynb)，从第四章写作流水线迁移，学习传值、条件、迭代和并发；再读 [08-恢复与运行保障](google-adk/08-动态工作流-恢复与运行保障.ipynb)，学习人工确认、checkpoint、execution ID、重试、超时与存储幂等。第八章的 [综合工程](google-adk/workflow_example/README.md) 实际验证三进程间的模型调用、持久归档与故障恢复。两章分别独立运行，需要 `DEEPSEEK_API_KEY`，均保留实际执行输出和验收汇总；所需依赖已纳入 `uv sync`。
