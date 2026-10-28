<a id="the-daily-pass"></a>

# 每日通行证

[maintenance.md](maintenance.md)中的周传证明每个家庭都活着。 日票不行：34个家庭和900多个子功能需要比智能体天更长的时间，而且大部分地图从昨天开始就没有变化。 每日
pass answers a narrower question with the same rigor: **did anything that
自上一次通过后，合并了什么API的消费者看到什么？**它只驱动那些被质疑的特征，当没有合并时什么都不做。

这是[maintenance.md](maintenance.md)允许的增量传递，并且它移动相同的基线。

这不是一个调度器，而是个程序：从你每天运行的程序中运行它，除非被要求，不要创建自动化或对外发布，而是将你找到的内容交给人。

<a id="inputs-and-hand-off"></a>

## 输入和切换

一个预定的会话在没有昨天的记忆的新会话中开始，所以它需要的任何东西都存在于仓库中或在打开的PR上：

- `BASE` 是 `Maintenance baseline: main@<sha> (<date>)` 行
  [the map index](feature-map/README.md), the previous pass's `TARGET`.
  `control-agent-server map baseline` 读取它并说明有多少次提交
  `HEAD` 已经过去了； `map owners` 没有参数与它不同。 获取
  `main`并将其完整的SHA冻结为`TARGET`； 加深浅克隆直到
  `BASE` 存在（`map baseline` 返回 `commits_since: null`，直到存在）。
- **当`BASE`等于`TARGET`**时提前停止：没有合并，因此没有什么可以驱动。 一个例外是早期通过的 PR 仍然处于开放状态，其中有一些待处理的内容（失败 CI，未答复的审查）； 处理好并停止。
- 一次传递建议 `TARGET` 作为其 PR 中的下一个基线（`control-agent-server map baseline --set "$TARGET"`； SHA 必须打开
  `origin/main` 只有在步骤2完成之后：每户 `map owners` 都被驱动，每条 `BASE..TARGET` 的提交都被解决到 PR，以及下面的关闭问题行都被重新驱动。 合并PR接受基线。 如果在第2步被卡住或超时，PR的行仍然停留在那里，即使CLI有其他地图或maintenance.md的修正，报告中也会说它被卡住了/部分完成。 没有任何改变的传递也会留下它，因此下一个传递覆盖了更长的范围。 如果前一个通道的 PR 仍然打开，则下一个通道将在该分支上继续，并从那里的线路获取 `BASE`。
- 昨天的分类帐是一个可选输入：当之前的运行目录或其 `evidence/ledger.jsonl` 存在时（CI 工件，共享目录），
  pass it to `evidence report --baseline`; without it the report has no
  “自基线以来的变化”部分和判决取决于今天的失败和阻止的行。

与周票一样，记录 UTC 时间、型号和支出预算以及可用的密钥和功能 (`control-agent-server capabilities`)。 A
pass that runs out of time says so and names what it did not reach; it never
把剩下的默默地滚到明天。

<a id="steps-in-order"></a>

## 步骤，按顺序

按此顺序运行步骤，并在预算用完时停止。 一个在`BASE..TARGET`中没有接触过任何东西的家庭不会被驱动：它会等待周票。

1. **静态（分钟，无服务器）。** `control-agent-server map check` 和
   `map coverage`. 一个命名不再提供服务的端点的食谱，一个动词或标志 CLI 不再解析，或在任何服务器启动之前发现了一个不属于任何路由家族的路由。 今天晚些时候通过实时驾驶在地图中修复该问题，或报告该问题。
2. **已更改（核心）。** `control-agent-server map owners --target "$TARGET"` 列出了 `Source:` 行拥有已更改路径的系列，以及
   `unowned_product_paths` 没有家人声称。 将每条无主路径映射到一个族或一个明确的非智能体面向的原因，如 maintenance.md §2 所示。 也区分合同：`map diff --base <BASE worktree>`添加、删除或新添加的路线已弃用，以及REST破损检查的PR注释模式更改。 然后驱动 ** 每个 ** 列出的系列重新运行 (`map run --file Fnn --fresh --record`)，以及每个入口系列列出的每个更改的行为 (REST、WebSocket、SDK、TypeScript 客户端)。 将共享模型（`openhands-sdk` 事件、设置、LLM 配置）扩展到每个系列，将它们序列化而不是采样。 将 `BASE..TARGET` 中的每个合并提交解析为其 PR 并保持意图 (`documented`,
   `undocumented`, `contradictory`） 与运行时结果分开，如 maintenance.md 第3节描述了。 差分通过有一个第二部分：每个标签写着“第二部分”的子弹 `known bug`或者其Gotchas链接了一个问题，当该问题关闭时，会重新驱动 `BASE` (检查每个关联问题的状态)，记录其行，并更新其标签或备注。 一个没有触及家庭的修复程序 landed without touching a family's `Source:` 路径只能这样显示。 所以，每一个都是开放的 `bug` 自从  `BASE` 它命名了一个映射的路由或特征：它被复制并附上注释，因此，任何不在通过的报告中的错误都会到达地图。 基于模型的食谱仅在运行 LLM 预算； 没有密钥时，它们是 `blocked` 缺少必要前提。

<a id="reading-the-result"></a>

## 读取结果

渲染 `control-agent-server evidence report --runs <every run of the pass>`，当该账本在手时使用 `--baseline <yesterday's run or ledger>`。 失败和阻塞的行排在第一位； “自基线以来的变化”部分（如果存在）是每日结论：

- **新失败**在一个家庭中，第 2 步推动了一条改变的道路：引入范围内的候选人。 在将其称为回归之前，在 `BASE` (`map run --file Fnn --only <ID> --fresh --checkout <BASE worktree>`) 上重新驱动相同的最小配方； 否则将其分类为在两者上复制、环境或线束间隙或来源未经确认。
- **在其他地方新失败**，或**新通过**但没有PR解释
  it：未记录的变更； 引用提交并询问。
- **未检查此运行**行的特征在所触及的范围内没有任何特征，而不是回归。
- 如果没有昨天的分类帐，请以同样的方式读取今天的失败行：在家庭步骤 2 上行驶更改路径的失败是重新行驶的候选者
  `BASE`; 在其他地方，这是一个需要分类的发现，从地图上获取该家庭最后已知的状态（`known bug`项目符号，一个链接的问题）。

将问题归类为技能：追踪漂移（修复，有实时证据），捕捉空隙（扩展 CLI，重新驱动），产品缺陷（保留证据，搜索问题，将其提交到拥有仓库，并在地图 PR 中用问题链接标记 `known bug`）。 修复被保留），被阻止（命名先决条件和路线）。 每次通过最多 PR 个经过验证的地图和 CLI 个修正，
from current `main` (or from the previous pass's branch while its PR is
open），携带移动后的基线并在报告中注明“delta”； 切勿一次性编辑产品代码。

<a id="several-agents"></a>

## 几个智能体

按家庭分片，而不是按子弹分片：每个智能体都有整个家庭，它自己的
`launch --new`（或`map run --fresh`），它自己的`AGENT_SERVER_VERIFY_RUN`，并且只写入它自己的分类帐。 一名协调员将账本与
`evidence report --runs` 并拥有交接权。 名称为 no run、revision 或入口的结果不算在内； 差距不是通过。

<a id="what-the-daily-pass-is-not"></a>

## 每日通行证不是什么

- 这不是完整的通过：它没有证明每一个子弹，基线只说这一天的更改已经覆盖，这就是为什么步骤2的未完成项永远不会移动。 当步骤2发现大部分地图受到影响（共享模型、依赖项增加如FastAPI、LiteLLM或MCP）时，说清楚并运行完整的流程。 每周或发布前仍需要进行一次完整的传递，因为依赖关系会在不触及路由器的情况下改变行为。
- 不是 CI：绿色测试运行或通过 `map check` 是判决的输入，而不是判决。
- 不是错误修复通道：产品错误在内部进行归档和映射，而不是修复
  pass.
