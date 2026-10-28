---
name: run-eval
description: Trigger and monitor evaluation runs for benchmarks like SWE-bench, GAIA, and others. Use when running evaluations via GitHub Actions or monitoring eval progress through Datadog and kubectl.
triggers:
- run eval
- trigger eval
- evaluation run
- swebench eval
---

<a id="running-evaluations"></a>

# 运行评估

<a id="trigger-via-github-api"></a>

## 通过 GitHub API 触发

```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/actions/workflows/run-eval.yml/dispatches" \
  -d '{
    "ref": "main",
    "inputs": {
      "benchmark": "swebench",
      "sdk_ref": "main",
      "eval_limit": "50",
      "model_ids": "claude-sonnet-4-5-20250929",
      "reason": "Description of eval run",
      "benchmarks_branch": "main"
    }
  }'
```

**关键参数：**
- `benchmark`: `swebench`, `swebenchpro`, `swebenchmultimodal`, `gaia`, `swtbench`, `commit0`, `multiswebench`, `terminalbench`, `programbench`
- `eval_limit`：任意正整数（e.g.、`1`、`10`、`50`、`200`）
- `model_ids`：请参阅 `.github/run-eval/resolve_model_config.py` 了解可用型号
- `benchmarks_branch`：在合并之前使用基准测试存储库中的功能分支来测试基准测试更改

**注意：**运行完整评估时，您必须选择大于或等于基准测试中实际实例数的`eval_limit`。 如果指定较小的限制，则只会评估那么多实例（部分评估）。

<a id="monitoring"></a>

## 监控

**Datadog 脚本**（需要 `OpenHands/evaluation` 存储库； 设置 DD_API_KEY、DD_APP_KEY 和 DD_SITE 环境变量）：
```bash
DD_API_KEY=$DD_API_KEY DD_APP_KEY=$DD_APP_KEY DD_SITE=$DD_SITE \
  python scripts/analyze_evals.py --job-prefix <EVAL_RUN_ID> --time-range 60
# EVAL_RUN_ID 格式：通常是来自 GitHub 操作的工作流运行 ID
```

**kubectl**（对于具有集群访问权限的用户 - 智能体没有 kubectl 访问权限）：
```bash
kubectl logs -f job/eval-eval-<RUN_ID>-<MODEL_SLUG> -n evaluation-jobs
```

<a id="common-errors"></a>

## 常见错误

| 错误 | 原因 | 修复 |
|-------|-------|-----|
| `503 Service Unavailable` | 基础设施超载 | 要求用户停止一些评估运行 |
| `429 Too Many Requests` | 速率限制 | 等待或减少并发 |
| `failed after 3 retries` | 实例失败 | 检查 Datadog 日志以查找根本原因 |

<a id="limits"></a>

## 限制

- 最多 256 个并行运行时（如果超过此限制，作业将排队）
- 完整评估通常需要 1-3 小时，具体取决于基准测试大小
