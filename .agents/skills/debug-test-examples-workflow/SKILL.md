---
name: debug-test-examples-workflow
description: Guide for debugging failing example tests in the `test-examples` labeled workflow. Use this skill when investigating CI failures in the run-examples.yml workflow, when example scripts fail to run correctly, when needing to isolate specific test failures, or when analyzing workflow logs and failure patterns.
---

<a id="debugging-test-examples-workflow"></a>

# 调试测试示例工作流程

<a id="overview"></a>

## 概述

`run-examples.yml` 工作流程运行 `examples/` 目录中的示例脚本。 触发器：
- 将 `test-examples` 标签添加到 PR
- 手动工作流调度

<a id="debugging-steps"></a>

## 调试步骤

<a id="1-isolate-failing-tests"></a>

### 1. 隔离失败的测试

修改`tests/examples/test_examples.py`以专注于特定测试：

```python
_TARGET_DIRECTORIES = (
    # EXAMPLES_ROOT/“01_standalone_sdk”，
    EXAMPLES_ROOT / "02_remote_agent_server",  # 仅保留失败目录
)
```

<a id="2-exclude-tests"></a>

### 2. 排除测试

添加到`_EXCLUDED_EXAMPLES`并附上说明：

```python
_EXCLUDED_EXAMPLES = {
    # 排除原因
    "examples/path/to/failing_test.py",
}
```

<a id="3-trigger-workflow"></a>

### 3. 触发工作流程

切换 `test-examples` 标签：

```bash
# 去除标签
curl -X DELETE -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/issues/${PR_NUMBER}/labels/test-examples"

# 添加标签
curl -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/issues/{PR_NUMBER}/labels" \
  -d '{"labels":["test-examples"]}'
```

<a id="4-monitor-progress"></a>

### 4. 监控进度

```bash
# 检查状态
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/actions/runs/{RUN_ID}" | jq '{status, conclusion}'

# 下载日志
curl -sL -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/actions/runs/{RUN_ID}/logs" -o logs.zip
unzip logs.zip -d logs
```

<a id="common-failure-patterns"></a>

## 常见故障模式

| 图案 | 原因 | 解决方案 |
|---------|-------|----------|
| 端口冲突 | 固定端口（8010、8011） | 使用 `-n 1` 运行或使用不同的端口 |
| 容器问题 | Docker/Apptainer 设置 | 检查 Docker 可用性，图像拉取 |
| LLM 失败 | 瞬态 API 错误 | 重试测试 |
| 错误示例 | 代码错误 | 检查回溯 |


<a id="key-configuration"></a>

## 关键配置

**工作流程** (`.github/workflows/run-examples.yml`)：
- 跑步者：`blacksmith-2vcpu-ubuntu-2404`
- 超时：60 分钟
- 并行度：`-n 4`（pytest-xdist：4 个并行工作线程）

**测试** (`tests/examples/test_examples.py`)：
- 超时每个示例：600 秒
- 目标目录：`_TARGET_DIRECTORIES`
- 排除的示例：`_EXCLUDED_EXAMPLES`
