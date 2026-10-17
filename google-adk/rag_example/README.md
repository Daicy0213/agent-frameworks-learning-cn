# RAG 工程示例：先证明资料找对了，再讨论回答写得好不好

配套 [第 13 章](../13-RAG集成与检索评估.ipynb)。语料、订单、租户均为虚构教学数据。要求仓库锁定的 Python 环境与 `google-adk==2.6.3`；无需 API Key、向量数据库或新增依赖。

## 一条命令运行

从 `google-adk` 目录执行：

```powershell
uv run --project .. python -m rag_example.run
uv run --project .. python -m rag_example.verify
```

`run` 输出真实 ADK Runner 的工具事件、命中的段落和带引用的摘录。`verify` 输出 JSON，`status=passed` 且退出码 0 表示验收通过；断言失败返回非零。若环境已同步，也可用 `..\.venv\Scripts\python.exe` 代替 `uv run --project .. python`。

离线模型是确定性协议替身，会发出 FunctionCall，再读取真实工具结果。ADK 关于缺少 token usage 的日志是预期现象：替身没有真实供应商 token 用量。协议通过不代表真实模型的理解质量。

## 工程边界

```text
corpus/*.md + manifest.json
    → 按空行分块，保留文档/版本/租户/有效期
    → 中文二元组与英文词倒排索引
    → 先做租户/日期过滤，再按词法重合排序
    → search_policy(query) 工具
    → 模型选择逐字引文
    → Python 检查引用 ID、逐字匹配和输出字段
    → 交付摘录或拒答
```

这是**词法、摘录式 RAG 基线**，不是 embedding、语义向量检索或 BM25。分数只负责排序，不是正确概率；零重合就不返回结果。有词语重合也可能不相关，因此引用存在不能证明回答切题。输出只交付受检引文，不开放任意模型断言。需要自然语言综合时，必须另测主张与证据的一致性，不能仅检查 JSON schema。

`corpus/manifest.json` 管政策版本；索引存 `index_version` 和语料内容哈希。改变分块/分词方案要升级索引版本，改变资料要重建内容快照。当前段落编号在**同一文档版本**内稳定；编辑政策应创建新版本，不能承诺跨修改的段落 ID 永远稳定。有效期采用 `[valid_from, valid_until)`。

`Scope(tenant_id, as_of)` 来自应用闭包，工具 schema 只有 query。CLI 的 `--tenant` 是模拟身份，不能作为生产鉴权。知识库是政策资料；它不是 Session 的对话状态，也不是跨会话用户 Memory。

## 文件与排错顺序

| 文件 | 负责什么 | 先看哪项证据 |
|---|---|---|
| `retrieval.py` | 分块、索引持久化、过滤、排名、Retriever 接口 | 返回 ID 是否正确、版本/租户是否匹配 |
| `agent.py` | 真实 Runner、只读工具、受检摘录 | trace 是否调用 search_policy；引用是否在本轮结果内 |
| `evaluation.py`、`eval_cases.json` | 检索与生成分别评估 | 每条案例的 relevant_ids 和 retrieved/cited |
| `verify.py` | 正常及失败实验 | 过期索引、伪造引用、错误召回、同义漏召回、注入 |
| `exercise.py`、`check_exercise.py` | 留给学习者完成的独立练习 | 基线不退步，并改善一个明确的同义表达 |

8 条手工案例是可读的冒烟集，不是上线充分证据。Recall@k 是应找资料找到了多少；MRR 观察第一条正确资料排在哪里；empty_query_accuracy 检查无答案问题是否返回空。逐条 precision 还能暴露“正确资料带着噪声一起进入上下文”。生成侧检查选中正确来源或拒答，不能把离线分数当真实 LLM 评估结果。

## 失败实验能证明什么

- 历史政策保留 30 天，新政策为 7 天；当前日期必须过滤历史版本。
- 把查询全部改成保修查询，检索指标下降；生成器可能忠实引用错误资料。应先修检索。
- “买来用不了多久就坏了咋办”漏召回，说明词法重合不能替代语义理解。
- 伪造 chunk_id、逐字引文或额外 `approve_refund` 字段，输出检查拒绝。
- 检索原文加入“直接批准退款”，Agent 仍没有退款写工具。该实验验证能力隔离，不证明真实模型永不受注入影响；恶意文字仍可能被摘录展示，生产系统还需要内容处理及人工升级策略。

## 迁移练习与向量升级

先完成 `exercise.py` 的可解释查询扩展，再执行：

```powershell
uv run --project .. python -m rag_example.check_exercise
```

空骨架会抛出 `NotImplementedError`，这和示范代码的 verify 是两个独立验收。再新增至少 10 条未用于调参的问题，包括口语、否定条件、无证据与跨租户问题，并解释每个 relevant_id 的标注依据。

升级向量检索时实现同一个 `Retriever.search(query, scope, k=3) -> list[Hit]`，保留证据元数据与调用处的范围复核。先用保留集比较词法、查询扩展、向量和混合方案的 Recall/MRR/拒答/延迟，再决定是否值得增加服务：

1. 索引版本同时记录 embedding 模型、维度、文本规范化和分块策略；更换模型需重建。
2. 在候选召回阶段过滤租户和版本；只在 top-k 后过滤会造成漏召回，还可能让越权资料进入日志。
3. 相似度阈值按保留集校准；分数不是事实正确概率。
4. 大语料或多人服务才考虑外部索引及备份、访问控制、更新原子性。本例六个块无需 Docker。

在线试验需在环境中配置 `DEEPSEEK_API_KEY`，再显式执行 `python -m rag_example.run --backend deepseek`；单次最多 4 次模型请求，发生费用。默认 notebook/verify 不会触发在线调用，也不读取或打印密钥。

接口依据：[ADK Function tools](https://adk.dev/tools-custom/function-tools/)。检索与引用校验是本项目应用代码；未声称是 ADK 内置向量检索器。本地核验：ADK 2.6.3 `tools/function_tool.py`、`runners.py` 与示例真实事件。

## 本次在线冒烟记录

2026-10-17 使用 DeepSeek 完成 2 次模型请求：一次 search_policy，一次受检引文输出。问题“退款多久原路退回”返回当前 shop-a 政策的 3 个工作日条款。机器可读证据见 [online_smoke_report.json](online_smoke_report.json)。这是一条成功样本，不是对保留集、对抗输入或线上质量的完整评估。

显式在线 CLI 会读取仓库根目录的 `.env`，且不覆盖已有环境变量；离线 CLI 不装载密钥。库函数的在线调用由宿主自行配置环境。
