---
name: pr-design-doc
description: >
  For a non-trivial pull request, write a self-contained HTML design doc under the
  temporary `.pr/` directory and link a visibility-appropriate preview in the PR
  description, so maintainers grasp the proposal at a glance - code/API design, and the
  before/after of the change, grounded to real code. Use when opening or updating a
  non-trivial PR, or when the user says "add a design doc", "document this PR for
  reviewers", "show the before/after", "make the design reviewable", or "write the .pr/
  page".
triggers:
- /pr-design-doc
- /design-doc
license: MIT
metadata:
  tags: pull-request, design-doc, html, review, before-after, htmlpreview
---

<a id="pr-design-doc---a-reviewable-design-doc-for-a-non-trivial-pr"></a>

# PR-design-doc - 一个重要的可审查设计文档 PR

差异显示*逐行更改的内容*。 它没有显示*设计*：变化的形状、之前和之后的API，以及为什么采用这种方法。 审稿人慢慢地手工重建它。 稀缺资源是维护者的注意力和信任预算——而不是智能体的努力。 多花精力制作一个 **自包含的 HTML一页 **页面，该页面传达 **大图景 **和 **前后核心差异 **，每个论点
**可点击回到真实代码**，然后从PR描述中链接它。

这与“向我展示此更改”解释器相同，其目的是完成一项工作：使重要的 PR 易于审查。

<a id="when-to-use-it"></a>

## 何时使用它

- **打开或更新一个**非简单的PR：新的/更改的公共API，一个新的模块或子系统，核心逻辑的行为改变，迁移，或者任何一个审查者在几分钟内无法完全判断的内容。
- **跳过它**，因为琐碎的事情PR - 一个拼写错误、一个单行防护、一个依赖项冲突、一个文档调整、一个简单的错误修复。 设计文档增加了更多的审查内容。 运用判断力； 如果差异 * 是 * 解释，则不要添加页面。

<a id="the-pr-workflow"></a>

## `.pr/` 工作流程

将临时 **`.pr/`** 目录用于仅限 PR 的工件。 在依赖自动清理之前，请验证目标存储库是否已启用
`.github/workflows/pr-artifacts.yml` 工作流程，在 PR 合并到 `main` 后打开或更新清理 PR。

- 具有经过验证的清理工作流程的相同存储库或分支 PR：工作流程打开或更新清理 PR，以在合并后从 `main` 中删除 `.pr/`。
- 没有经过验证的清理工作流程的存储库：在合并之前手动删除 `.pr/`。

设计文档是临时审阅辅助工具，不得保留在 `main` 上。 在PR描述中保留关键设计概要：意图、重要前/后行为或API形状、兼容性、风险和代码引用。 使用提交固定的文档链接，以便清理不会中断访问。

<a id="workflow"></a>

## 工作流程

1. **检查并验证 PR 头。**不要从基础分支或不相关的签出编写或提交设计文档。 从干净的工作树开始，然后检查并检查 PR：
   ```bash
   gh pr view <n> --json title,body,url,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner,isCrossRepository,files,additions,deletions
   gh pr checkout <n>
   git rev-parse HEAD
   gh pr view <n> --json headRefOid --jq .headRefOid
   ```
   在继续之前，最后两个 SHAs 必须匹配。 如果他们不这样做，停止并修复结账。 计算与 SHA 合并的基础
   `git merge-base <baseRefOid> <headRefOid>`. 按区域对更改的文件进行分组，并保留合并库 SHA 和头 SHA 作为源链接。

2. **读取每个逻辑文件的两面。**比较
   `git show <merge-base-sha>:<path>` 带有已验证的头。 捕获
   **功能级别**行为差异 - 代码*做了*与*现在做了什么*。
   - 新文件→没有“之前”； 一个“之后”图加上它添加的角色上的线。
   - 已删除的文件→“之前”图+谁/什么接管。
   - 编辑后的文件 → 之前/之后对，突出显示增量。

3. **对每个文件进行分类。** *逻辑*改变（行为移动）→绘制之前/之后。 *机械*更改（重命名、常量、配置、导入移动）→一行`before → after`行，无图表。 不要通过进行机械编辑来淡化信号。

4. **如果更改是 API 更改，则以 API.** 开头显示签名/模式/类型
   **之前和之后**并排（函数签名，端点 + 载荷，配置字段，
   事件形状）。 明确指出兼容性影响：附加、破坏或标记后。

5. **查找跨文件故事。**如果一个调用链线程多个文件，则绘制一个
   **概述**之前/之后在顶部； 每个文件卡钻入。

6. **根据 [`references/html-craft.md`](references/html-craft.md) 构建页面** - 一个独立的、离线的、编辑性的 HTML 文件，其中包含手绘 SVG 的图形。 将其保存到存储库的 `.pr/` 目录 e.g。 `.pr/design.html`（或`.pr/<topic>.html`）。 在写入之前，拒绝`.pr`处或确切输出路径处的符号链接； 永远不要遵循工作树之外的分支控制符号链接。
   ```bash
   test ! -L .pr && test ! -L .pr/design.html
   mkdir -p .pr
   ```

7. **在`.pr/`下提交，推送到已验证的PR头，并链接它。**确认推送远程解析为`headRepository.nameWithOwner`； 切勿将工件推送到基础存储库的默认分支。
   ```bash
   git add .pr/design.html
   git commit -m "docs(.pr): design doc for <PR topic>"
   git push <head-repo-remote> HEAD:<headRefName>
   git rev-parse HEAD
   ```
   使用生成的完整 SHA 作为 `<doc-commit-sha>` 在文档链接中。 当设计因实质性更改而受到影响时，刷新文档及其链接。 清理 commit 不需要新的链接。 在选择链接之前，先查询基础仓库的可见性。
   ```bash
   gh repo view <base-owner>/<base-repo> --json visibility,url
   ```
   - **公共仓库：** 在顶部添加一个 HTML 预览链接 PR 描述，指向了 **PR 获取文档所包含的头仓库和提交**:
     ```
     📄 Design doc: https://htmlpreview.github.io/?https://github.com/<fork-owner>/<repo>/blob/<doc-commit-sha>/.pr/design.html
     ```
   - **私有或内部仓库：**将受控访问的GitHubblob链接到同一文档提交，并包括本地下载/打开说明，或使用现有受控访问的资源服务。 切勿通过 htmlpreview 或其他公共主机发送文档。

<a id="what-the-page-contains"></a>

## 页面包含什么内容

1. **发生了什么变化（首先做出决定）** - 一段：意图、净效果以及审稿人为什么应该关心。 将影响最大的结论、风险或 API 兼容注释放入
   `★` 标注，最重要的更改 `path:line` 位于附近。 统计信息（`N 个文件·
   +A / −D`) 是上下文，而不是领先。 如果存在跨文件流，**概述
   SVG** 之前/之后放在这里。
2. **API before → after** （当 PR 更改接口时） - 签名/模式/类型并排，并声明兼容性判断。
3. **左栏/索引** - 按区域分组的更改文件，每个标记（🟢添加·🔴删除·✏️更改·⚙️机械）与+/−计数； 点击跳跃。
4. **按文件的卡片** - 每个逻辑文件：一个携带声明的标题，一个一行的摘要，描述其行为变化的**前后**对比图，`file:line`（橙色表示更改的节点），以及一个折叠的`<details>`差异。 机械文件有一个小`before → after`表格，没有图表。
5. **（可选）风险/后续措施** - 仅当基于您所阅读的内容时。

<a id="non-negotiable-principles"></a>

## 不容谈判的原则

1. ** 优化稀缺的评审员注意力。** 第一屏幕回答：PR 会做什么，是否风险，首先应该去哪里，以及支持该说法的证据。 以结论为主导，而不是你的过程。
2. **显示差异，而不是结果。** 对于任何逻辑或API更改，绘制**before**和**after**，并使*delta*视觉上突出（颜色 + 线样式）。 对比就是产品。
3. **把一切代码化，除了这个主张。** 每个盒子、节点和句子都命名了一个真实符号 `path:line`, 并尽可能链接到正确的源版本：合并基 SHA 在前置证据和已验证的主句 SHA 用于事后证据。 单击“此更改”即可获得确切的代码。
4. **手绘携带图。**更喜欢定制内联 SVG 作为争论之前/之后的内容； Mermaid 仅适用于快速辅助图。
5. **自包含且离线的。**一个HTML文件，内联CSS/SVG，没有外部脚本或资源，双击打开，且能在另一台机器上生存。
6. 仅限 **`.pr/`，并且是临时的。**该文档是审阅辅助工具，而不是项目文档。 保留在
   `.pr/` 仅当存储库的工作流程已得到验证时才依赖合并后清理； 否则在合并之前手动删除它。 不要将设计 HTML 移至
   `docs/` 或将其永久保留为 `main`。

<a id="anti-patterns"></a>

## 反模式

- ❌ 转储原始差异/文件树并将其称为“设计文档” - 不会在 PR 页面上添加任何内容。
- ❌ 空节点（“处理数据”、“处理请求”）——每个节点都是一个真实的符号+位置。
- ❌ 仅当某些内容发生变化时的后状态 - 审阅者需要 * 对比度 *。
- ❌ 关于一个琐碎的 PR 噪音的设计文档。 跳过它。
- ❌ 将 HTML 提交到 `.pr/` 之外（e.g. `docs/`），它将合并到`main`中。
- ❌ 通过 htmlpreview、GitHub Pages 或其他公共主机发布私有存储库设计文档。 使用工艺参考中的私有/本地预览路径。 验证私有页面访问控制后，仅与显式用户授权一起使用 GitHub 页面。
