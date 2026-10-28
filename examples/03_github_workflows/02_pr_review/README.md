<a id="pr-review-workflow"></a>

# PR 审核工作流程

此示例演示如何使用 OpenHands 智能体 SDK 设置 GitHub Actions 工作流程以进行自动拉取请求审查。 当 PR 被标记为 `review-this` 或当 OpenHands-智能体添加为审阅者时，OpenHands 将分析更改并提供详细的、建设性的反馈。

**注意**：实际的审核脚本现在位于 [OpenHands/extensions](https://github.com/OpenHands/extensions/tree/main/plugins/pr-review) 存储库中。 该目录包含引用这些脚本的示例工作流程。

<a id="files"></a>

## 文件

- **`workflow.yml`**：运行 PR 审核智能体的示例 GitHub 操作工作流程文件
- **`README.md`**：该文档文件

<a id="features"></a>

## 特点

- **自动触发**：在以下情况下触发审核：
  - 将 `review-this` 标签添加到 PR，或者
  - OpenHands-智能体被请求作为审稿人
- **内联评审评论**：直接在 PR diff 中的特定代码行上发布评审评论，而不是单个巨大的评论。 这使得更容易：
  - 准确查看反馈所指的行
  - 一一解决问题
  - 集中讨论特定的代码部分
- **评论上下文认知度 **：智能体考虑了之前的评论历史：
  - **以前的评论**：查看所有过去的评论决定（APPROVED、CHANGES_REQUESTED等）
  - **评论线程**：获取所有评论线程，包括其解决状态
  - **智能评论**：避免重复已经提出和解决的问题
  - **未解决的焦点**：优先考虑可能仍需要关注的未解决的线程
  - **分页限制**：每页最多获取 100 个线程（带分页），每个线程最多获取 50 条评论。 对于PR，其广泛的评论历史超过了这些限制，较旧的线程/评论可能会被省略。
- **基于技能的审核**：使用<https://github.com/OpenHands/extensions>中的公共技能：
  - **`/codereview`**：标准实用代码审查，重点关注简单性、类型安全性和向后兼容性
  - **`/codereview-roasted`**：Linus Torvalds 风格残酷诚实的评论，强调“好品味”和数据结构
- **完整的差异前期**：智能体在初始消息中接收每个文件的差异载荷，前面是列出 PR 中每个文件的 `Files Changed` 清单（因此，即使各个补丁被缩写，智能体也始终知道完整的文件集）
  - 每个文件的补丁上限为 `MAX_PER_FILE_PATCH`（8,000 个字符），因此单个大文件不会让小文件挨饿
  - 组合补丁块的上限为 `MAX_TOTAL_DIFF`（100,000 个字符）； 超过上限的文件出现在清单中，但它们的补丁被替换为 `[patch omitted: ...]` 标记
  - 智能体具有完整的存储库访问权限，并被指示直接从工作区读取截断的文件，而不是将它们视为丢失
- **综合分析**：分析整个存储库上下文中的代码更改
- **详细反馈**：提供结构化的审核意见，涵盖：
  - 变化的总体评估
  - 代码质量和最佳实践
  - 潜在问题和安全问题
  - 具体改进建议
- **GitHub API 集成 **：使用 GitHub API 直接在特定代码行上发布内联评论注释
- **版本控制**：使用`extensions-version`固定到扩展存储库的特定版本标签或分支

<a id="setup"></a>

## 设置

<a id="1-copy-the-workflow-file"></a>

### 1. 复制工作流程文件

将存储库中的 `workflow.yml` 复制到 `.github/workflows/pr-review-by-openhands.yml`：

```bash
cp examples/03_github_workflows/02_pr_review/workflow.yml .github/workflows/pr-review-by-openhands.yml
```

<a id="2-configure-secrets"></a>

### 2. 配置机密

在 GitHub 存储库设置中设置以下机密：

- **`LLM_API_KEY`**（必填）：您的 LLM API 密钥
  - 从 [OpenHands LLM 提供商 ](https://docs.all-hands.dev/openhands/usage/llms/openhands-llms) 获取一个

**注意**：工作流程自动使用所有 GitHub 操作工作流程中可用的 `GITHUB_TOKEN` 机密。

<a id="3-customize-the-workflow-optional"></a>

### 3. 自定义工作流程（可选）

编辑 `.github/workflows/pr-review-by-openhands.yml` 以自定义输入：

```yaml
            - name: Run PR Review
              uses: OpenHands/extensions/plugins/pr-review@main
              with:
                  # 根据需要自定义这些输入
                  llm-model: gpt-5.5
                  llm-base-url: ''
                  review-style: roasted
                  # 机密
                  llm-api-key: ${{ secrets.LLM_API_KEY }}
                  github-token: ${{ secrets.GITHUB_TOKEN }}
                  lmnr-api-key: ${{ secrets.LMNR_PROJECT_API_KEY }}
```

<a id="4-create-the-review-label"></a>

### 4. 创建评论标签

在您的存储库中创建一个 `review-this` 标签：

1. 转到您的存储库→问题→标签
2. 点击“新标签”
3. 姓名：`review-this`
4. 描述：`Trigger OpenHands PR review`
5. 颜色：选择您喜欢的任何颜色
6. 点击“创建标签”

<a id="usage"></a>

## 用途

<a id="triggering-a-review"></a>

### 触发审核

有两种方法可以触发拉取请求的自动审查：

<a id="option-1-using-labels"></a>

#### 选项 1：使用标签

1. 打开您想要审核的拉取请求
2. 将 `review-this` 标签添加到 PR
3. 工作流程将自动启动并分析更改
4. 审核意见完成后将发布到PR

<a id="option-2-requesting-a-reviewer-recommended"></a>

#### 选项 2：请求审稿人（推荐）

1. 打开您想要审核的拉取请求
2. 点击右侧边栏中的“审稿人”
3. 搜索并选择“OpenHands-智能体”作为审阅者
4. 工作流程将自动启动并分析更改
5. 审核意见完成后将发布到PR

**注意**：添加标签或请求*新*审阅者需要写入权限。 GitHub可能仍然允许PR作者对已经审阅过的审稿人使用“重新请求审阅”。

<a id="customizing-the-code-review"></a>

## 自定义代码审查

您可以通过将 `.agents/skills/code-review.md` 文件添加到存储库来自定义代码审查行为，而不是分叉 `agent_script.py`。 这是**推荐的定制方法**。

<a id="how-it-works"></a>

### 它是如何运作的

默认情况下，PR 评论智能体使用 [OpenHands/extensions](https://github.com/OpenHands/extensions) 存储库中的技能。 当您将 `.agents/skills/code-review.md` 文件添加到存储库时，它会使用您的自定义指南**覆盖**默认技能。

<a id="example-custom-code-review-skill"></a>

### 示例：自定义代码审查技能

在您的存储库中创建 `.agents/skills/code-review.md`：

```markdown
---
name: code-review
description: Custom code review guidelines for my project
triggers:
- /codereview
---

# My Project Code Review Guidelines

You are a code reviewer for this project. Follow these guidelines:

## Review Decisions

- **APPROVE** straightforward changes (config updates, typo fixes, documentation)
- **COMMENT** when you have feedback or concerns

## What to Check

- Code follows our project conventions
- Tests are included for new functionality
- No security vulnerabilities introduced
- Documentation is updated if needed

## Communication Style

- Be direct and constructive
- Use GitHub suggestion syntax for code fixes
- Approve quickly when code is good
```

<a id="benefits-of-custom-skills"></a>

### 定制技能的好处

1. **无需fork**：继续使用官方SDK，并自定义行为
2. **版本控制**：您的审核指南位于您的存储库中
3. **轻松更新**：SDK更新不会覆盖您的自定义设置
4. **团队对齐**：每个人都使用相同的审核标准

<a id="reference-example"></a>

### 参考示例

有关自定义代码审查技能的完整示例，请参阅 [software-智能体-SDK 自己的代码审查技能 ](https://github.com/OpenHands/software-agent-sdk/blob/main/.agents/skills/code-review.md)。

<a id="workflow-configuration"></a>

## 工作流程配置

使用 `OpenHands/extensions/plugins/pr-review` 操作的输入来配置工作流程。

<a id="action-inputs"></a>

### 动作输入

| 输入 | 描述 | 默认示例 |
|-------|-------------|---------|
| `llm-model` | LLM  model(s) - 可以用逗号分隔进行 A/B 测试 | `gpt-5.5` |
| `llm-base-url` | LLM 底座 URL（可选） | `''` |
| `review-style` | 评论风格：“标准”或“烘焙” | `roasted` |
| `llm-api-key` | LLMAPI键 | `${{ secrets.LLM_API_KEY }}` |
| `github-token` | GitHub token 用于 API 访问 | `${{ secrets.GITHUB_TOKEN }}` |
| `lmnr-api-key` | 用于可观察性的层流 API 键（可选） | `${{ secrets.LMNR_PROJECT_API_KEY }}` |

要使用扩展存储库的特定版本，请修改工作流文件中的 `uses` 行，e.g., `uses: OpenHands/extensions/plugins/pr-review@v1.0.0`。

<a id="ab-testing-with-multiple-models"></a>

## 使用多个模型进行 A/B 测试

PR 审核工作流程支持 A/B 测试不同的 LLM 模型。 当指定多个模型时，每次审核都会随机选择一个模型。

<a id="configuration"></a>

### 配置

在 `llm-model` 输入中将多个模型指定为逗号分隔的列表：

```yaml
            - name: Run PR Review
              uses: OpenHands/extensions/plugins/pr-review@main
              with:
                  # 用于 A/B 测试的多个模型 - 将随机选择一个
                  llm-model: 'gpt-5.5,gpt-4'
                  llm-api-key: ${{ secrets.LLM_API_KEY }}
                  github-token: ${{ secrets.GITHUB_TOKEN }}
                  # ... other inputs
```

<a id="observability"></a>

### 可观察性

启用层流可观测性后，所选模型将自动记录到跟踪元数据中：

- **跟踪元数据**：将 `model` 字段添加到层流跟踪元数据中
- **轨迹JSON**：所选模型记录在`laminar_trace_info.json`中
- **GitHub日志**：所选模型打印到工作流日志

这使得能够在层流仪表板中过滤和比较不同模型的审核有效性。

<a id="review-evaluation-observability"></a>

## 审查评估（可观察性）

当启用Laminar可观测性(`lmnr-api-key`输入提供)时，工作流捕获跟踪数据，以延迟评估审查有效性。

<a id="how-it-works-1"></a>

### 它是如何运作的

1. **审核期间**：智能体脚本捕获层流跟踪 ID 并将其存储为 GitHub 工件
2. **开启 PR 关闭/合并**：评估工作流程 (`pr-review-evaluation.yml`) 自动运行：
   - 从工件下载跟踪 ID
   - 获取所有 PR 评论以及与 GitHub 的最终差异
   - 在 Laminar 中创建评估跟踪并进行审查上下文
   - 可选择对原始评论跟踪进行评分

<a id="evaluation-metrics"></a>

### 评估指标

评估脚本提供：
- **评论参与度评分**：基于人类对智能体评论的反应的初步评分
- **评论分析**：信号处理的结构化数据（已解决哪些评论）
- **Final Diff 上下文**：实际代码变化进行比较

<a id="laminar-signal-integration"></a>

### 层流信号积分

配置层流信号来分析评估轨迹：

1. 创建一个名为 `pr_review_effectiveness` 的信号
2. 按标签过滤：`pr-review-evaluation`
3. 利用信号提示词分析：
   - 最终补丁中解决了哪些智能体条评论
   - 哪些评论得到了人类的回应
   - 总体评审效果评分

有关完整的实现细节，请参阅 [GitHub Issue #1953](https://github.com/OpenHands/software-agent-sdk/issues/1953)。
