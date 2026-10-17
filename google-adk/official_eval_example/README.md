# 三条案例学会真正的 `adk eval`

你已会 Agent、Runner 和工具；本实验让你完成一次 **预测→运行→读证据→制造失败→修复→回归**。默认全程离线，不需要模型密钥。在线 DeepSeek 路径单独选择。

## 1. 环境与边界

`OrderModel(BaseLlm)` 只替换模型响应，ADK Runner、Session、FunctionTool、调用事件和官方评估器仍真正运行。离线通过证明本例的运行/评估链路正常，不能证明真实模型理解了任务。

主环境保持 `google-adk==2.6.3`、`litellm==1.96.2`。ADK 的默认评估注册表导入 Vertex SDK，所以 CLI 隔离环境包含 `google-cloud-aiplatform==2.5.0` 基础包；此例没有使用 Vertex Judge，也不会调用 Vertex 服务。没有安装完整 `[eval]` extra：该扩展的 Vertex evaluation 依赖在 Python 3.12 下限制 LiteLLM `<1.86`，与课程版本冲突。

依赖见 `requirements-cli.txt`，本次实际解析版本见 `verification-record.json`。这是专用 CLI 环境，不要求给主项目降级。

## 2. 首次运行：三条绿灯

从仓库根目录执行。构建需要联网下载依赖，后续离线运行明确禁用容器网络：

```powershell
docker build -f google-adk/official_eval_example/Dockerfile -t adk-course-eval:2.6.3 .
docker run --rm --network none --name adk-course-eval-green adk-course-eval:2.6.3
```

Docker 的入口就是官方 `adk eval official_eval_example`。它实际执行：

```text
adk eval official_eval_example official_eval_example/three_cases.evalset.json --config_file_path official_eval_example/evaluation_config.json --print_detailed_results
```

三条分别是存在订单、订单不存在、缺订单号。前两条应调用 `query_order`，第三条应澄清且不调用工具。配置要求轨迹为 `1.0`，回答 ROUGE-1 至少 `0.8`。

不使用 Docker 时，可以建立专用环境（本机 Windows 的独立环境因 DLL/临时目录限制未完成运行验收，已验收路径是 Docker Linux）：

```powershell
uv venv .venv-eval --python 3.12
uv pip install --python .venv-eval/Scripts/python.exe -r google-adk/official_eval_example/requirements-cli.txt
Set-Location google-adk
..\.venv-eval\Scripts\adk.exe eval official_eval_example official_eval_example/three_cases.evalset.json --config_file_path official_eval_example/evaluation_config.json --print_detailed_results
```

Linux 对应可执行文件是 `.venv-eval/bin/adk`。不必把该目录加入主项目依赖。

## 3. 有意失败：答案正确，工具没执行

先预测两项分数，再运行：

```powershell
docker run --rm --network none --name adk-course-eval-broken -e ADK_EVAL_INJECT_BUG=skip_tool adk-course-eval:2.6.3 official_eval_example/three_cases.evalset.json:order_found --config_file_path official_eval_example/evaluation_config.json --print_detailed_results
```

`skip_tool` 让模型替身直接返回正确文本。实际证据是轨迹 `0.0`、回答 `1.0`、案例 `FAILED`。回答相似不能替代执行证据。修复是取消故障变量，然后再次执行第 2 节的三条全量命令；不需要降低阈值。

选择案例语法：`file.evalset.json:order_found`；多个案例用 `:order_found,order_missing`。例如只回归错误订单：

```powershell
docker run --rm --network none --name adk-course-eval-selected adk-course-eval:2.6.3 official_eval_example/three_cases.evalset.json:order_missing --config_file_path official_eval_example/evaluation_config.json --print_detailed_results
```

## 4. 报告与 CI：不要只看 CLI 的退出码

ADK 2.6.3 本次实测：上面的失败案例 **CLI 仍返回 0**。该退出码只表明命令完成，不能授予质量通过。

原生 JSON 写入 `<agent>/.adk/eval_history/*.evalset_result.json`；每条案例的 `final_eval_status` 是 1/PASSED、2/FAILED、3/NOT_EVALUATED。报告同时保留每项指标和各轮实际/期望轨迹。`NOT_EVALUATED` 也不能通过 CI。

本仓库验证脚本用独立临时目录接收每次报告，避免读到历史结果，随后把原始 JSON 与日志复制到 `reports/`：

```powershell
.venv\Scripts\python.exe google-adk/official_eval_example/verify_cli.py --backend docker
```

预期顺序：`green` 3/3 → `broken` 0/1（这是预期失败）→ `repaired` 3/3 → `selected` 1/1。脚本自身只有在四次都符合预测时返回 0；它每次都实际启动官方 CLI，不伪造评分结果。

单独让一份官方报告成为 CI 检查：

```powershell
.venv\Scripts\python.exe google-adk/official_eval_example/check_result.py google-adk/official_eval_example/reports/green.evalset_result.json
# 预期退出码 0
.venv\Scripts\python.exe google-adk/official_eval_example/check_result.py google-adk/official_eval_example/reports/broken.evalset_result.json
# 预期退出码 1
```

报告为空/无法读取返回 2。脚本只汇总本报告，不会证明数据集覆盖充分。`reports/` 是本地生成物；仓库中的 `verification-record.json` 记录本次已执行结果。

## 5. 可选：将相同案例交给 DeepSeek

这一段会产生模型费用，需要网络。先在当前进程安全设置 `DEEPSEEK_API_KEY`（不把值写进命令历史或课程文件），随后只运行一条。`-e DEEPSEEK_API_KEY` 从宿主环境传入，命令中不出现密钥值：

```powershell
docker run --rm --name adk-course-eval-online -e DEEPSEEK_API_KEY -e ADK_EVAL_BACKEND=deepseek adk-course-eval:2.6.3 official_eval_example/three_cases.evalset.json:order_found --config_file_path official_eval_example/evaluation_config.json --print_detailed_results
```

一次查单通常包括一次决定工具调用和一次读工具结果后的回答；错误重试会增加请求数。固定温度 0 不能保证供应商模型完全确定。在线失败时先读轨迹和回答，判断是凭据/网络、工具参数还是模型表现；离线结果仍可用于排除基础链路问题。

2026-10-17 已实际执行上述单案例在线路径：两个带 token usage 的模型事件，轨迹与 ROUGE 均为 1，案例 PASSED。仅验证这一条，不声称 26 条或真实模型完整评估通过。

主项目 `.env` 不会自动传入 Docker；只传需要的模型密钥，不应把整个密钥文件打包进镜像。本例工具只有确定性的演示订单查询。

## 6. 迁移到 26 条与业务效果

三条学会流程后，再使用 [`../eval_example`](../eval_example/README.md) 的 26 条售后数据。官方 CLI 理解原生输入、轨迹和参考回答；`test_spec` 中的账本断言由 `run_quality_eval.py` 执行。

- 文本正确但没写账本：任务失败。
- 拒答正确但发生写入：任务失败。
- 单案例冒烟通过：只说明所选案例通过，`release_ready=false`。
- 没运行安全案例：安全率为 `null`，不能解释为 100%。

练习：增加缺订单号/不完整订单号案例，先预测零调用，再保存失败和修复报告；最后回归原三条。有限测试不能保证所有未知输入正确。

官方资料：[评估工作流](https://adk.dev/evaluate/) · [指标定义](https://adk.dev/evaluate/criteria/)。具体 CLI 退出码以上述 2.6.3 实测为准。
