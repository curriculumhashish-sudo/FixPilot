---
name: feature-release-rollout
description: This skill should be used when the user asks to "rollout a feature", "complete feature release", "propagate SDK feature", "track feature support", "what's missing for feature X", or mentions checking CLI/GUI/docs/blog support for SDK features. Guides agents through the multi-repository feature release workflow from SDK to docs to marketing.
triggers:
- rollout feature
- feature release
- propagate feature
- feature support
- complete release
- docs for feature
- blog for feature
- CLI support
- GUI support
- what's missing
---

<a id="feature-release-rollout"></a>

# 功能发布推出

此技能指导整个 OpenHands 生态系统存储库的完整功能发布工作流程。

<a id="overview"></a>

## 概述

当一个功能在 SDK 中实现时，它可能需要通过多个存储库传播：

1. **SDK** (`OpenHands/software-agent-sdk`) — 核心功能实现
2. **CLI** (`OpenHands/OpenHands-CLI`) — 终端接口支持
3. **GUI**（`OpenHands/OpenHands`前端目录）——Web界面支持
4. **Docs** (`OpenHands/docs`) — 文档更新（sdk/文件夹）
5. **博客** (`OpenHands/growth-utils` blog-post/) — 营销和公告
6. **视频** - 教程内容（使用ElevenLabs + Remotion）

<a id="workflow"></a>

## 工作流程

<a id="phase-1-feature-discovery"></a>

### 第一阶段：功能发现

首先，确定要分析的内容 feature(s)。 用户可以指定：
- 发布标签 (e.g., `v1.9.0`)
- 具体功能名称
- PR 或提交引用
- 版本之间的比较

**对于发布标签：**
```bash
# 克隆 SDK（如果不存在）
git clone https://github.com/OpenHands/software-agent-sdk.git

# 查看发布说明
cd software-agent-sdk
git log --oneline v1.8.0..v1.9.0  # 版本之间的变化
git show v1.9.0 --stat             # 此版本中发生了什么变化
```

**具体功能：**
搜索 SDK 代码库、示例和变更日志以了解功能范围。

<a id="phase-2-repository-analysis"></a>

### 第 2 阶段：存储库分析

克隆所有相关存储库以分析当前支持：

```bash
# 克隆存储库（使用 GITHUB_TOKEN 进行身份验证访问）
git clone https://github.com/OpenHands/software-agent-sdk.git
git clone https://github.com/OpenHands/OpenHands-CLI.git
git clone https://github.com/OpenHands/OpenHands.git        # 前端中的前端/
git clone https://github.com/OpenHands/docs.git
git clone https://github.com/OpenHands/growth-utils.git
```

对于每个功能，检查支持状态：

| 存储库 | 检查位置 | 寻找什么 |
|------------|---------------|------------------|
| CLI | `openhands_cli/` | 功能标志、命令、TUI 小部件 |
| GUI | `OpenHands/frontend/src/` | React 组件，API 集成 |
| 文档 | `docs/sdk/` | 指南页面，API 参考，示例 |
| 博客 | `growth-utils/blog-post/posts/` | Announcement posts |

<a id="phase-3-assess-feature-importance"></a>

### 第 3 阶段：评估功能重要性

并非所有功能都值得全面推出。 评估每个功能：

**高影响力（建议全面推出）：**
- 新的面向用户的功能
- 不兼容变更或迁移
- 主要性能改进
- 新的集成或工具

**中等影响（文档+选择性支持）：**
- 新的 API 方法或参数
- 配置选项
- 开发者体验改进

**低影响（仅限文档或跳过）：**
- 内部重构
- 错误修复
- 小幅改进

**跳过推出：**
- 仅限内部更改
- 测试改进
- 构建/CI 更改
- 文档错别字

<a id="phase-4-create-proposal"></a>

### 第 4 阶段：创建提案

为用户生成结构化提案：

```markdown
## Feature Rollout Proposal: [Feature Name]

### Feature Summary
[Brief description of the feature and its value]

### Current Support Status
| Component | Status | Notes |
|-----------|--------|-------|
| SDK | ✅ Implemented | [version/PR] |
| CLI | ❌ Missing | [what's needed] |
| GUI | ⚠️ Partial | [what's implemented vs needed] |
| Docs | ❌ Missing | [suggested pages] |
| Blog | ❌ Not started | [whether warranted] |
| Video | ❌ Not started | [whether warranted] |

### Recommended Actions
1. **CLI**: [specific implementation needed]
2. **GUI**: [specific implementation needed]
3. **Docs**: [pages to create/update]
4. **Blog**: [recommended or not, with reasoning]
5. **Video**: [recommended or not, with reasoning]

### Assessment
- **Overall Priority**: [High/Medium/Low]
- **Effort Estimate**: [days/hours per component]
- **Dependencies**: [what must be done first]
```

<a id="phase-5-user-confirmation"></a>

### 第五阶段：用户确认

在继续之前等待明确的用户批准。 问：
- 要实施哪些组件
- 优先订购
- 对提案的任何修改

<a id="phase-6-implementation"></a>

### 第六阶段：实施

仅在用户确认后：

**创建 GitHub 问题：**
```bash
# 在相关仓库上创建问题
gh issue create --repo OpenHands/OpenHands-CLI \
  --title "Support [feature] in CLI" \
  --body "## Context\n[Feature description]\n\n## Implementation\n[Details]\n\n## Related\n- SDK: [link]\n- Docs: [link]"
```

**实施顺序：**
1. CLI/GUI支持（可并联）
2. 文档（取决于 1）
3. 博客文章（取决于 2）
4. 视频（取决于 3）

<a id="repository-specific-guidelines"></a>

## 存储库特定指南

### CLI (OpenHands/OpenHands-CLI)

- 检查`AGENTS.md`以获取开发指南
- 使用 `uv` 进行依赖管理
- 在提交之前运行 `make lint` 和 `make test`
- `openhands_cli/tui/` 中的 TUI 组件
- UI 更改的快照测试

<a id="gui-openhandsopenhands-frontend"></a>

### GUI（OpenHands/OpenHands前端）

- 前端位于 `frontend/` 目录中
- React/TypeScript 代码库
- 在前端运行 `npm run lint:fix && npm run build`/
- 遵循 TanStack 查询模式来获取数据
- `frontend/src/i18n/` 中的 i18n 翻译

<a id="docs-openhandsdocs"></a>

### 文档 (OpenHands/文档)

- `sdk/` 文件夹中的 SDK 文档
- 使用 Mintlify（`.mdx` 个文件）
- 代码块可以从 SDK 个示例自动生成同步
- 运行 `mint broken-links` 进行验证
- 关注`openhands/DOC_STYLE_GUIDE.md`

<a id="blog-openhandsgrowth-utils"></a>

### 博客 (OpenHands/growth-utils)

- 帖子 `blog-post/posts/YYYYMMDD-title.md`
- 资产在 `blog-post/assets/YYYYMMDD-title/`
- 前置元数据格式：
  ```yaml
  ---
  title: "Post Title"
  excerpt: "Brief description"
  coverImage: "/assets/blog/YYYYMMDD-title/cover.png"
  date: "YYYY-MM-DDTHH:MM:SS.000Z"
  authors:
    - name: Author Name
      picture: "/assets/blog/authors/author.png"
  ogImage:
    url: "/assets/blog/YYYYMMDD-title/cover.png"
  ---
  ```

<a id="example-feature-analysis"></a>

## 示例特征分析

**功能：浏览器会话录制 (SDK v1.8.0)**

1. **SDK**：✅ 在`openhands.tools.browser`中实现
2. **CLI**: ❌ 无重播/导出命令
3. **GUI**: ❌ 无录制查看器组件
4. **文档**：✅ 指南位于 `sdk/guides/browser-session-recording.mdx`
5. **博客**：❌可以为网页抓取用户突出显示
6. **视频**：考虑 2 分钟演示

**建议**：中等优先级。 文档已完成，CLI/GUI 紧迫性较低（高级功能），博客文章可选。

<a id="quick-commands"></a>

## 快速命令

```bash
# 检查 SDK 功能是否存在
grep -r "feature_name" software-agent-sdk/openhands/ --include="*.py"

# 检查 CLI 支持
grep -r "feature_name" OpenHands-CLI/openhands_cli/ --include="*.py"

# 检查 GUI 支持
grep -r "featureName" OpenHands/frontend/src/ --include="*.ts" --include="*.tsx"

# 检查文档覆盖范围
grep -r "feature" docs/sdk/ --include="*.mdx"

# 检查博客提及
grep -r "feature" growth-utils/blog-post/posts/ --include="*.md"
```

<a id="important-notes"></a>

## 重要提示

- 在创建问题或开始实施之前始终获得用户确认
- 考虑功能成熟度——新功能在全面推出之前可能会发生变化
- 问题描述中存储库之间的交叉引用 PR
- 对于不兼容变更，协调所有组件的发布时间
