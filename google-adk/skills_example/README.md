# Skills 工程示例：把工作规程按需交给 Agent

配套 [第 14 章](../14-Skills工程与渐进加载.ipynb)。使用 **ADK 2.6.3 的真实 `SkillToolset`**；这是 ADK Agent 的技能，不是 Codex 的个人 Skill 配置。官方将该功能标为 Experimental，升级版本后应重跑验收。

## 运行与证据

从 `google-adk` 目录执行：

```powershell
uv run --project .. python -m skills_example.run
uv run --project .. python -m skills_example.run --approved
uv run --project .. python -m skills_example.verify
```

默认离线，真实 Runner 调用真实 SkillToolset 与业务工具；只有模型由确定性替身提供。无需密钥或新依赖。`verify` 的 `status=passed`、退出码 0 是验收标准。缺少 token usage 的 ADK 日志源于替身未产生供应商 token 账单，不是工具失败。

`run` 默认模拟 viewer：完成相同加载过程后受理被拒绝。`--approved` 使用服务器已经批准教学订单的身份，创建一个内存受理记录，不转账。这个 CLI 参数只是实验输入，不是生产认证方式。

| 请求时点 | 模型已读材料 | 业务工具 |
|---|---|---|
| 初始 | 通用使用说明 | 尚无 |
| list_skills 后 | 两个 Skill 的名字与 description | 尚无 |
| load_skill 后 | refund-triage 的 SKILL.md 正文与 frontmatter | lookup_refund_policy、request_refund 可见 |
| load_skill_resource 后 | 指定的 reference，随后指定 asset | 可见，但业务授权仍独立检查 |

`snapshots` 从 `before_model_callback` 的真实 `LlmRequest` 记录 marker 是否出现、工具名和上下文字符数。`trace` 记录真正发生的 FunctionCall/FunctionResponse。字符数不是 token 计数，也不是节省费用的实测结论。无关 shipment-status 正文未加载。

重要区别：`load_skill_from_dir` 在应用启动时已经把本地文件读入 Python；“渐进加载”指内容何时进入**模型请求**，不是磁盘延迟读取。ADK 2.6.3 默认提供 list_skills；不要假设首次请求已带完整目录。资源加载顺序属于使用规程，不能把提示词中的顺序当安全访问控制。已激活 Skill 的状态可以在同一 Session 延续，本例每次新建 Session 以便对照观察，不假定每轮自动卸载。

## 目录与责任

- `skills/refund-triage/SKILL.md`：何时用、执行顺序、失败处理，以及 `metadata.adk_additional_tools`。
- `references/rules.md`：业务规则说明；`assets/result-contract.json`：回执模板；`scripts/check_amount.py`：失败实验用脚本资源。
- `skills/shipment-status/SKILL.md`：不相关的对照技能。
- `agent.py`：公开 `build_toolset(desk)`，可嵌入其他 Agent；`run_skill_case()` 提供离线轨迹。
- `business.py`：可信 Principal、政策检索、工具内的租户/角色/审批/金额核验。
- `verify.py`：渐进上下文、权限、资源失败和同进程幂等验收。

Skill 说明怎么做，Tool 执行一次操作，权限决定当前调用者是否允许执行。`adk_additional_tools` 从宿主预先注册的函数中决定可见工具；它不凭空创建 Python 函数，也不授予用户退款权。生产环境应在工具边界读取真实身份与最新审批，不从 Skill、模型参数或资源文字中取信任。

## 故障实验

```powershell
uv run --project .. python -m skills_example.run --scenario missing_resource
uv run --project .. python -m skills_example.run --scenario no_executor
uv run --project .. python -m skills_example.run --approved --scenario duplicate
```

预期依次观察 `RESOURCE_NOT_FOUND`、`NO_CODE_EXECUTOR`、两次相同回执但一个受理记录。本例没有配置代码执行器；有 scripts 文件不代表脚本自动运行。需要执行时，应选择受控执行环境并单独管理文件、网络与时间权限。

verify 还把“忽略身份直接批准”注入临时资源副本，再走真实 Runner：业务工具仍拒绝 viewer。这证明服务边界不依赖资源文字；由于模型是固定协议替身，不能据此宣称真实 LLM 具备注入免疫。内存去重只在本次进程有效；[第 15 章](../15-Capstone-售后Agent工程验收.ipynb)负责持久化受理与重复请求。

## 独立练习

实现 `exercise.py` 的换货授权，再运行 `python -m skills_example.check_exercise`。空骨架应失败；示范 verify 通过不代表练习完成。

随后创建 `exchange-triage`，复用权限检查，并增加真实 Runner 验收：目录可发现、加载前正文不可见、加载后只出现需要的资源、缺审批拒绝、跨租户拒绝。不要把已有退款 Skill 全文复制过来；description 写清触发边界，把共同规则放独立资源，并通过已审查的构建过程打包进每个 Skill。正式发布前固定版本/哈希、审查资源与脚本、运行回归集，再灰度给真实模型比较选 Skill 正确率、错误加载率与请求成本。

在线模式显式执行 `python -m skills_example.run --backend deepseek`，需 `DEEPSEEK_API_KEY`，最多 8 次模型请求并产生费用。默认运行及 notebook 不在线。在线模型可能跳步或误选，应从 trace 定位；协议替身不能覆盖这些错误。

参考：[官方 Skills 文档](https://adk.dev/skills/)。版本核验源码：本地 `google/adk/skills/_utils.py`（文件装载）、`skills/models.py`（frontmatter）、`tools/skill_toolset.py`（加载工具、附加工具解析与执行器）。本文基于锁定的 2.6.3 行为，不把可变的最新文档视为版本保证。

## 本次在线冒烟记录

2026-10-17 使用 DeepSeek 完成 5 次模型请求：list_skills → load_skill → 同轮加载两份资源并查询政策 → request_refund → 最终答复。viewer 的请求被拒绝，没有受理记录，最终文本说明缺少服务器审批。机器可读证据见 [online_smoke_report.json](online_smoke_report.json)。

真实模型没有机械复现离线的逐步顺序：两份资源与只读政策查询在同轮并行发生。此样本验证了加载和业务回执路径，不证明 SKILL.md 的每一步都是强制执行顺序。本例查询不依赖资源返回值，可以并行；若业务必须“完成校验 A 才允许调用 B”，应由工具服务或宿主工作流强制执行，并新增顺序验收。一次任务成功也不能代替选 Skill 的保留集评估。

显式在线 CLI 会读取仓库根目录的 `.env`，且不覆盖已有环境变量；离线 CLI 不装载密钥。库函数的在线调用由宿主自行配置环境。
