---
name: sdk-release
description: >-
  This skill should be used when the user asks to "release the SDK",
  "prepare a release", "publish a new version", "cut a release",
  "do a release", or mentions the SDK release checklist or release process.
  Guides through the full software-agent-sdk release workflow
  from version bump to PyPI publication, emphasizing human checkpoints.
---

<a id="sdk-release-guide"></a>

# SDK 发布指南

本技能一步步走遍软件-智能体-SDK发布流程。

> **🚨 CRITICAL**: 绝不合并版本 PR 或创建/发布 GitHub
> 未经人类明确批准就发布。 发布是最后一行
> 人类的防御。 始终呈现当前状态并询问
> 在执行任何不可逆转的操作之前进行确认。

<a id="phase-1-trigger-the-prepare-release-workflow"></a>

## 第 1 阶段：触发准备-发布工作流程

确定目标版本 (SemVer `X.Y.Z`)。 然后触发
`prepare-release.yml` 工作流程，自动创建发布分支和 PR。

<a id="via-github-ui"></a>

### 通过 GitHub 用户界面

导航到 <https://github.com/OpenHands/software-agent-sdk/actions/workflows/prepare-release.yml>，单击 **运行工作流程**，输入版本 (e.g. `1.16.0`），然后运行它。

<a id="via-github-api"></a>

### 通过 GitHub API

```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/actions/workflows/prepare-release.yml/dispatches" \
  -d '{
    "ref": "main",
    "inputs": {
      "version": "1.16.0"
    }
  }'
```

工作流程将：
1. 验证版本格式
2. 创建分支 `rel-<version>`
3. 在所有包中运行 `make set-package-version version=<version>`
4. 更新评估工作流程中的 `sdk_ref` 默认值
5. 打开标题为 **"Release v\<version\>"** 的 PR，并带有标签
   `integration-test`、`behavior-test`、`test-examples` 和 `security-scan`
6. 使用发布 PR 链接和工作流程参与者通知 `#proj-agent`

<a id="-checkpoint--confirm-pr-created"></a>

### ⏸ 检查点 — 确认 PR 已创建

在继续之前，请验证 PR 是否存在并且版本更改看起来正确。

```bash
gh pr list --repo OpenHands/software-agent-sdk \
  --head "rel-<version>" --json number,title,url
```

<a id="phase-2-address-deprecation-deadlines"></a>

## 第 2 阶段：地址弃用截止日期

`deprecation-check` CI 作业在每个 PR 上运行。 如果发布版本超过了代码库中声明的任何弃用截止日期，则检查将失败。

查看失败的检查输出并执行以下任一操作：
- 如果已过截止日期，则删除已弃用代码，** 或 **
- 延长期限并提供合理理由。

将修复推送至发布分支。 合并前必须通过检查。

<a id="phase-3-wait-for-ci--checks-must-pass"></a>

## 第 3 阶段：等待 CI — 检查必须通过

释放 PR 会触发三个标记测试套件和安全扫描。
**全部四项都必须通过。**

| 标签 | 套房 | 它涵盖什么 |
|-------|-------|----------------|
| `integration-test` | 集成测试 | 端到端智能体个场景 |
| `behavior-test` | 行为测试 | 智能体行为约束检查 |
| `test-examples` | 测试示例 | `examples/` 中所有可运行的示例 |
| `security-scan` | 发布安全扫描 | 批准偏差和依赖性差异检查 |

监控状态：

```bash
gh pr checks <PR_NUMBER> --repo OpenHands/software-agent-sdk
```

<a id="-checkpoint--human-judgment-on-failures"></a>

### ⏸ 检查点——人类对失败的判断

一些测试失败可能是预先存在的或不稳定的。 与团队一起决定每次失败是否：
- **阻塞** — 必须在发布前修复
- **已知/预先存在** - 可以在后续问题中发布
- **Flaky** — 重新运行工作流程

重新运行失败的作业：

```bash
# 查找运行 ID
gh run list --repo OpenHands/software-agent-sdk \
  --branch "rel-<version>" --limit 5

# 重新运行失败的作业
gh run rerun <RUN_ID> --repo OpenHands/software-agent-sdk --failed
```

<a id="phase-4-run-evaluation-optional-but-recommended"></a>

## 第 4 阶段：运行评估（可选但推荐）

在 SWE 工作台（或另一个基准测试）上针对发布分支触发评估运行以捕获回归。 有关完整详细信息，请参阅 `run-eval` 技能。

```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/actions/workflows/run-eval.yml/dispatches" \
  -d '{
    "ref": "main",
    "inputs": {
      "benchmark": "swebench",
      "sdk_ref": "v<version>",
      "eval_limit": "50",
      "reason": "Pre-release eval for v<version>",
      "allow_unreleased_branches": "true"
    }
  }'
```

<a id="-checkpoint--evaluate-results"></a>

### ⏸ 检查点——评估结果

将评估结果与之前的版本进行比较。 分数大幅下降应该会阻止发布。

<a id="phase-5-merge-the-release-pr"></a>

## 第 5 阶段：合并版本 PR

> **🚨 STOP — 在没有明确人类批准的情况下进行不合并。**
> 呈现 CI 状态摘要并要求人员在合并前确认。
> 合并实际上是不可逆的——它会自动触发完整的合并
> 发布管道（GitHub发布→PyPI发布→下游版本更新）。

一旦人类批准：

```bash
gh pr merge <PR_NUMBER> --repo OpenHands/software-agent-sdk --merge
```

<a id="phase-6-automated-release-pipeline-no-action-needed"></a>

## 第 6 阶段：自动发布管道（无需采取任何操作）

合并版本 PR 时，会自动发生以下情况：

1. **`create-release.yml`** 检测合并的 `rel-*` 分支，创建带有标签 `v<version>` 和自动生成的发布说明的 GitHub 版本。
2. **`pypi-release.yml`** 在已发布的版本上触发并将所有四个包发布到 PyPI：
   - `openhands-sdk`
   - `openhands-tools`
   - `openhands-workspace`
   - `openhands-agent-server`
3. **`version-bump-prs.yml`** 在成功 PyPI 发布后触发并创建下游版本提升 PR。

<a id="-checkpoint--verify-pypi-publication"></a>

### ⏸ 检查点 — 验证 PyPI 发布

```bash
# 检查每个包是否可用（需要几分钟的时间进行索引）
for pkg in openhands-sdk openhands-tools openhands-workspace openhands-agent-server; do
  curl -s -o /dev/null -w "$pkg: %{http_code}\n" \
    "https://pypi.org/pypi/$pkg/<version>/json"
done
```

全部应该返回 `200`。

<a id="phase-7-post-release-announcements"></a>

## 第 7 阶段：发布后公告

自动管道完成后，编写一条 Slack 消息供人员发布，包括指向下游版本凹凸 PR 的链接：

```
🚀 *SDK v<version> published to PyPI!*

Version bump PRs:
• <https://github.com/All-Hands-AI/OpenHands/pulls?q=is%3Apr+bump-sdk-<version>|OpenHands>
• <https://github.com/OpenHands/openhands-cli/pulls?q=is%3Apr+bump-sdk-<version>|OpenHands-CLI>

Release: <https://github.com/OpenHands/software-agent-sdk/releases/tag/v<version>|v<version>>
```

有关审查下游 PR 和处理任何问题的详细信息，请参阅 `references/post-release-checklist.md`。

<a id="quick-reference--full-checklist"></a>

## 快速参考 - 完整清单

- [ ] 触发器 `prepare-release.yml` 与目标版本
- [ ] 验证版本 PR 已创建
- [ ] 修复弃用截止日期失败问题（如果有）
- []集成测试通过
- [ ] 行为测试通过
- [ ] 示例测试通过
- [ ] 安全扫描通行证
- [ ]（可选）评估运行显示没有回归
- [ ] **🚨 获得人工批准**，然后合并版本 PR
- [ ] _(Automated)_ GitHub 使用自动生成的注释创建的版本
- [ ] _(Automated)_ 软件包发布到 PyPI
- [ ] _(Automated)_ 已创建下游版本凹凸 PR
- [ ] 验证包出现在PyPI
- [ ] 发送带有下游版本升级的 Slack 消息 PR 链接
