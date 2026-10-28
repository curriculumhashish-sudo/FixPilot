---
name: manage-evals
description: This skill should be used when the user asks to "trigger an eval", "run evaluation", "run swebench", "run gaia", "run benchmark", "compare eval runs", "compare evaluation results", "check eval regression", "compare benchmark results", "what changed in the eval", "diff eval runs", or mentions triggering, comparing, or reporting on SWE-bench, GAIA, or other benchmark evaluation results. Provides workflow for triggering evaluations on different benchmarks, finding and comparing runs, and reporting performance differences.
---

<a id="managing-evaluations"></a>

# 管理评估

<a id="overview"></a>

## 概述

OpenHands 评估产生的结果存储在 CDN 的 `https://results.eval.all-hands.dev/` 处。 每次运行都由路径标识：`{benchmark}/{model_slug}/{github_run_id}/`。 此技能可以触发评估运行、比较运行之间的结果以及将性能报告发布为 GitHub PR 评论。

<a id="quick-start"></a>

## 快速入门

<a id="trigger-an-evaluation"></a>

### 触发评估

```bash
python .agents/skills/manage-evals/scripts/manage_evals.py trigger \
    --sdk-ref <BRANCH_OR_TAG> --benchmark swebench --eval-limit 50
```

<a id="compare-runs"></a>

### 比较运行

```bash
python .agents/skills/manage-evals/scripts/manage_evals.py compare \
    "<benchmark>/<model_slug>/<run_id>/" \
    --auto-baseline
```

<a id="compare-and-post-to-pr"></a>

### 比较并发布到 PR

```bash
python .agents/skills/manage-evals/scripts/manage_evals.py compare \
    "<benchmark>/<model_slug>/<run_id>/" \
    --auto-baseline \
    --post-comment --pr <PR_NUMBER> --repo OpenHands/software-agent-sdk
```

<a id="triggering-evaluations"></a>

## 触发评估

<a id="using-the-script"></a>

### 使用脚本

```bash
# PR 分支上的 SWE-bench（默认）
python .agents/skills/manage-evals/scripts/manage_evals.py trigger \
    --sdk-ref my-feature-branch --eval-limit 50

# GAIA 基准测试
python .agents/skills/manage-evals/scripts/manage_evals.py trigger \
    --sdk-ref main --benchmark gaia --eval-limit 50

# 有具体型号的
python .agents/skills/manage-evals/scripts/manage_evals.py trigger \
    --sdk-ref v1.16.0 --benchmark swebench --model-ids gemini-3-flash --eval-limit 50

# Multiple 基准测试（多次运行该命令）
for bench in swebench gaia; do
    python .agents/skills/manage-evals/scripts/manage_evals.py trigger \
        --sdk-ref main --benchmark "$bench" --eval-limit 50 --reason "Multi-benchmark eval"
done
```

<a id="available-benchmarks"></a>

### 可用基准测试

| 基准测试 | 描述 |
|-----------|-------------|
| `swebench` | SWE-bench（默认）——软件工程任务 |
| `swebenchpro` | SWE-Bench Pro — 更困难的软件工程任务 |
| `gaia` | GAIA — 一般人工智能助理任务 |
| `swtbench` | SWT-bench — 软件测试任务 |
| `commit0` | Commit0 — 提交生成任务 |
| `swebenchmultimodal` | SWE-bench Multimodal — 带有图像的任务 |
| `terminalbench` | TerminalBench — 终端交互任务 |
| `programbench` | ProgramBench — 针对黄金标准测试二进制文件的程序修复任务 |

<a id="trigger-options"></a>

### 触发选项

| 选项 | 默认 | 描述 |
|--------|---------|-------------|
| `--sdk-ref` | *（必填）* | 要评估的分支、标记或提交 SHA |
| `--benchmark` | `swebench` | 基准测试运行 |
| `--eval-limit` | `50` | 要评估的实例数 |
| `--model-ids` | *（配置中的第一个）* | 来自 `resolve_model_config.py` 的逗号分隔模型 ID |
| `--tool-preset` | `default` | 工具预设：`default`、`gemini`、`gpt5`、`planning` |
| `--agent-type` | `default` | 智能体类型：`default`、`acp-claude`、`acp-codex` |
| `--instance-ids` | | 要评估的特定实例 ID（覆盖 eval-limit） |
| `--reason` | | 人类可读的原因（在通知中显示） |
| `--benchmarks-branch` | `main` | 基准测试存储库的分支 |
| `--eval-branch` | `main` | 评估回购分支 |

<a id="via-pr-labels-alternative"></a>

### 通过 PR 标签（替代）

向 PR 添加标签也会触发评估：
- `run-eval-1` — 1 个实例（快速健全性检查）
- `run-eval-50` — 50 个实例（标准比较）
- `run-eval-200` — 200 个实例
- `run-eval-500` — 500 个实例（完整基准测试）

<a id="comparing-evaluation-runs"></a>

## 比较评估运行

<a id="step-1-find-the-current-prs-eval-run"></a>

### 第 1 步：查找当前 PR 的 Eval Run

通过将 `run-eval-50` 等标签添加到 PR 来触发评估运行。 完成后，`all-hands-bot` 发布了带有结果的评论。

**选项 A — 来自机器人对 PR:** 的评论

```bash
gh api repos/OpenHands/software-agent-sdk/issues/<PR_NUMBER>/comments \
    --jq '.[] | select(.user.login == "all-hands-bot") | .body' \
    | grep -o 'Evaluation:.*' | head -1
```

评估名称遵循格式 `{github_run_id}-{model_slug_short}` (e.g., `23775164157-claude-son`)。 从中提取`github_run_id`。

**选项 B — 来自“评估触发”机器人评论：**

```bash
gh api repos/OpenHands/software-agent-sdk/issues/<PR_NUMBER>/comments \
    --jq '.[] | select(.body | test("Evaluation Triggered")) | .body'
```

这包含 SDK 提交 SHA。 与每日元数据交叉引用以查找运行 ID。

**选项 C — 来自每日元数据：**

```bash
curl -s "https://results.eval.all-hands.dev/metadata/$(date -u +%Y-%m-%d).txt"
```

每条线都是一条运行路径。 通过基准测试和模型匹配来查找运行。

<a id="step-2-identify-the-run-path-components"></a>

### 第 2 步：识别运行路径组件

运行路径由三个组成部分组成：
- **基准测试**: `swebench`, `swebenchpro`, `gaia`, `swtbench`, `commit0`, `swebenchmultimodal`, `terminalbench`, `programbench`
- **model_slug**：源自型号名称，其中 `/:@.` 替换为 `-`（e.g.、`litellm_proxy-claude-sonnet-4-5-20250929`）
- **run_id**：`OpenHands/evaluation` 存储库中的 GitHub 操作工作流运行 ID

<a id="step-3-verify-results-exist"></a>

### 第 3 步：验证结果是否存在

```bash
curl -sI "https://results.eval.all-hands.dev/<benchmark>/<model_slug>/<run_id>/output.report.json" | head -1
```

`200` 状态确认运行已完成并且结果可用。

<a id="step-4-find-a-baseline-for-comparison"></a>

### 第 4 步：找到比较基准

**自动**：比较脚本的`--auto-baseline`标志扫描回溯14天的元数据文件，以找到与相同基准测试和模型的最最近完成运行。

**手动**：检查元数据文件或其他PR机器人注释以识别特定运行：

```bash
# 查看今天的跑步情况
curl -s "https://results.eval.all-hands.dev/metadata/$(date -u +%Y-%m-%d).txt" | grep "swebench/litellm_proxy-claude"

# 查看昨天的跑步情况
curl -s "https://results.eval.all-hands.dev/metadata/$(date -u -d yesterday +%Y-%m-%d).txt" | grep "swebench/litellm_proxy-claude"
```

<a id="step-5-run-the-comparison"></a>

### 第 5 步：运行比较

```bash
python .agents/skills/manage-evals/scripts/manage_evals.py compare \
    "swebench/litellm_proxy-claude-sonnet-4-5-20250929/23775164157/" \
    --baseline "swebench/litellm_proxy-claude-sonnet-4-5-20250929/23773892085/"
```

或者使用自动基线和 PR 评论发布：

```bash
python .agents/skills/manage-evals/scripts/manage_evals.py compare \
    "swebench/litellm_proxy-claude-sonnet-4-5-20250929/23775164157/" \
    --auto-baseline \
    --post-comment --pr 2334 --repo OpenHands/software-agent-sdk
```

<a id="available-data-per-run"></a>

## 每次运行的可用数据

每次运行都将文件存储在 `https://results.eval.all-hands.dev/{run_path}/` 处：

| 文件 | 描述 |
|------|-------------|
| `metadata/params.json` | 运行参数：SDK提交，PR数量，型号，eval_limit，triggered_by |
| `output.report.json` | 聚合结果：已解决/已提交/总计数和实例 ID |
| `cost_report.jsonl` | 每个实例的成本数据 |
| `results.tar.gz` | 包含所有输出的完整存档 |

<a id="dashboard"></a>

## 仪表板

评估监视器仪表板提供运行的可视化视图：

```
https://openhands-eval-monitor.vercel.app/?run={benchmark}/{model_slug}/{run_id}/
```

<a id="interpreting-results"></a>

## 解释结果

- **成功率** = 已解决 / min(eval_limit, total_instances)
- 50 个实例的样本在运行之间具有 ±2-4 个解析实例的自然方差
- 关注**实例级别的变化**（获得/丢失）以了解回归与回归。 噪音
- 如果解决了同一组实例，则差异可能是噪声

<a id="additional-resources"></a>

## 其他资源

<a id="reference-files"></a>

### 参考文件
- **`references/eval-infrastructure.md`** — 有关评估基础设施、GCS 路径、元数据格式和工作流程触发器的详细文档

<a id="scripts"></a>

### 脚本
- **`scripts/manage_evals.py`** — 具有自动基线检测和 GitHub 评论发布的独立比较脚本
