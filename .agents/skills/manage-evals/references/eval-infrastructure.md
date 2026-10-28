<a id="evaluation-infrastructure-reference"></a>

# 评估基础设施参考

<a id="architecture-overview"></a>

## 架构概述

评估管道跨越三个存储库：

1. **OpenHands/software-智能体-SDK** — 通过 `run-eval.yml` 工作流程触发评估
2. **OpenHands/evaluation** — 通过 `eval-job.yml` 工作流程协调评估作业
3. **OpenHands/benchmarks** — 包含基准测试个跑步者（推理 + 评估）

<a id="trigger-flow"></a>

## 触发流程

<a id="pr-label-trigger"></a>

### PR 标签触发器

1. 将标签 (`run-eval-1`, `run-eval-50`, `run-eval-200`, `run-eval-500`) 添加到 PR
2. `software-agent-sdk/.github/workflows/run-eval.yml` 火灾
3. 它从 `.github/run-eval/resolve_model_config.py` 解析模型配置
4. 调度 `OpenHands/evaluation` 中的 `eval-job.yml`：
   - `sdk_commit`：PR的头部SHA
   - `sdk_workflow_run_id`：`run-eval.yml` 工作流运行 ID
   - `eval_limit`：从标签名称中提取
   - `models_json`：已解决的模型配置
   - `pr_number`：PR号码（用于结果发布）
5. 在 PR 上发表“评估已触发”评论

<a id="release-trigger"></a>

### 释放触发器

在 `release` 事件和 `eval_limit=50` 上自动运行。

<a id="manual-trigger"></a>

### 手动触发

通过带有显式参数的 `run-eval.yml` 上的 `workflow_dispatch`。

<a id="results-storage-gcs"></a>

## 结果存储 (GCS)

结果存储在 Google Cloud Storage 存储桶 `openhands-evaluation-results` 中，并通过 CDN 和 `https://results.eval.all-hands.dev/` 提供服务。

<a id="run-path-format"></a>

### 运行路径格式

```
{benchmark}/{model_slug}/{github_run_id}/
```

- **基准测试**: `swebench`, `swebenchpro`, `gaia`, `swtbench`, `commit0`, `swebenchmultimodal`, `terminalbench`, `programbench`
- **model_slug**：型号名称，`/:@.` 替换为 `-`
  - 示例：`litellm_proxy/claude-sonnet-4-5-20250929` → `litellm_proxy-claude-sonnet-4-5-20250929`
- **github_run_id**：`OpenHands/evaluation` 存储库中的 GitHub 操作运行 ID

<a id="files-per-run"></a>

### 每次运行的文件数

```
{run_path}/
├── metadata/
│   └── params.json          # 作业参数（作业开始时上传）
├── output.report.json       # 综合评价结果
├── cost_report.jsonl        # 每个实例的成本数据
└── results.tar.gz           # 完整档案
```

<a id="paramsjson-schema"></a>

### params.json 模式

```json
{
    "timestamp": "2026-03-31T00:54:15Z",
    "sdk_commit": "42852dc2260a461536acc186cd918ad5a58910dd",
    "sdk_workflow_run_id": "23775150328",
    "eval_limit": 50,
    "benchmark": "swebench",
    "model_name": "litellm_proxy/claude-sonnet-4-5-20250929",
    "model_id": "claude-sonnet-4-5-20250929",
    "model_display_name": "Claude Sonnet 4.5",
    "unique_eval_name": "23775164157-claude-son",
    "commit": "42852dc2260a461536acc186cd918ad5a58910dd",
    "pr_number": "2334",
    "triggered_by": "enyst",
    "tool_preset": "default",
    "agent_type": "default",
    "github_run_id": "23775164157"
}
```

<a id="outputreportjson-schema"></a>

### output.report.json 模式

```json
{
    "total_instances": 500,
    "submitted_instances": 50,
    "completed_instances": 50,
    "resolved_instances": 35,
    "unresolved_instances": 15,
    "empty_patch_instances": 0,
    "error_instances": 0,
    "completed_ids": ["instance_id_1", "..."],
    "resolved_ids": ["instance_id_1", "..."],
    "unresolved_ids": ["instance_id_1", "..."],
    "empty_patch_ids": [],
    "error_ids": []
}
```

<a id="daily-metadata"></a>

## 每日元数据

某一天登记的所有跑步均列于：

```
https://results.eval.all-hands.dev/metadata/YYYY-MM-DD.txt
```

每条线都是一条运行路径。 示例：

```
swebench/litellm_proxy-claude-sonnet-4-5-20250929/23773892085/
swebench/litellm_proxy-gemini-3-flash-preview/23774756886/
gaia/litellm_proxy-claude-sonnet-4-5-20250929/23775142614/
```

元数据文件根据生成前提条件自动更新并设置为 `Cache-Control: no-cache`。

<a id="dashboard"></a>

## 仪表板

`https://openhands-eval-monitor.vercel.app/` 处的评估监视器仪表板提供了运行的可视化视图。 构建 URLs。

```
https://openhands-eval-monitor.vercel.app/?run={benchmark}/{model_slug}/{run_id}/
```

<a id="bot-comments"></a>

## 机器人评论

当评估完成时，`all-hands-bot` 在 PR 上发布评论（如果提供了 `pr_number`）：

- 评估名称 (e.g., `23775164157-claude-son`)
- 型号名称
- 结果摘要（总计、已提交、已解决、未解决、空补丁、错误计数）
- 成功率
- 存档链接

<a id="model-slug-computation"></a>

## 模型段塞计算

模型 slug 源自 LLM 配置的 `model` 字段：

```python
model = config["model"]  # e.g.，“litellm_proxy/克劳德十四行诗-4-5-20250929”
for ch in "/:@.":
    model = model.replace(ch, "-")
# 结果：“litellm_proxy-claude-sonnet-4-5-20250929”
```

<a id="available-models"></a>

## 可用型号

模型在`software-agent-sdk/.github/run-eval/resolve_model_config.py`中定义。 每个模型都有 `id`、`display_name` 和 `llm_config`，其中包含模型路径和参数。

<a id="variance-between-runs"></a>

## 运行之间的差异

对于 50 个实例 SWE 基准评估：
- 相同配置之间的自然方差通常为 ±2-4 个解析实例
- 关注实例级别的变化（特定实例获得/丢失）以区分真实回归和噪音
- 如果解析的实例集相同，则运行等效
