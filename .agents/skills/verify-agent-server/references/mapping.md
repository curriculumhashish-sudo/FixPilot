<a id="creating-and-extending-the-feature-map"></a>

# 创建和扩展特征图

该地图是为下一个智能体编写的，由从未见过服务器的人在冷酷和任务中期阅读。 每个条目都从 API 消费者的角度回答
view：该功能是什么，哪些路由和套接字携带该功能，哪些 SDK 和
TypeScript 客户端方法到达它，如何驱动它
`control-agent-server`，以及什么可观察的最终状态证明它有效。 从未执行过的菜谱是草稿，而不是条目。

<a id="0-build-or-check-the-lever-first"></a>

## 0. 首先构建或检查杠杆

在映射任何内容之前，请证明 CLI 可以端到端地承载一个特征：
`launch --new`, `doctor`，驱动一个映射的配方，保存与
`--save`、`evidence add`、`stop`，并确认`stop`后证据文件仍然存在。 如果任何步骤失败，请修复 CLI 或在写入条目之前报告环境拦截器：针对损坏的线束编写的地图会教导错误的步骤。

在映射过程中，每次你伸手去抓一个自定义脚本、一个 `curl`、一个 Python 插件或一个手动 `websocat` 来驱动或观察智能体路径时，停下来并添加一个动词或标志到 `scripts/control_agent_server.py` 而不是 (在 `--help` 中有示例)。 CLI 使地图可以重新运行。 如果动词已经存在，则使用它。

<a id="1-inventory-agent-facing-surfaces"></a>

## 1. 面向库存智能体的表面

从消费者可以调用的内容开始工作，并要求每个候选者有一个具体的源路径。 来源，大致按产量排序：

1. **路线**：`control-agent-server map routes`导入此结帐的应用程序并列出每条HTTP路线和WebSocket（`--module <router>`缩小范围）。 OpenAPI文档没有描述WebSockets或`include_in_schema=False`路线； 路由表可以。 它还以 Docker 运行时模式构建应用程序，并添加仅存在于该模式的路由（标记为 `config`）。 每条路线都归一个家庭所有，或者列在“未映射”下并附有原因。
2. **路由器和服务**：`openhands-agent-server/openhands/agent_server/*_router.py`以及它们调用的服务。 阅读`models.py`中的请求和响应模型以及它们引用的SDK模型：配方中的字段名称必须是真实的。
3. **WebSocket协议**：`sockets.py`，`session_socket.py`，
   `session_protocol.py`：auth（第一帧，已弃用查询参数，标头），重放（`resend_mode`，`after_timestamp`），双向帧，关闭代码。
4. **配置更改 API 行为**: `config.py` (`OH_*` variables): Webhookdeferred init, session keys, `max_concurrent_runs`, idle TTL, 保留，VS Code, 浏览器，CORS. 每个都可以通过以下方式到达
   `launch --config-json`、`--env` 或 `restart --config-json`。
5. **消费者**：SDK的`RemoteConversation`和`RemoteWorkspace`（`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`，
   `openhands-sdk/openhands/sdk/workspace/remote/`)、TypeScript 客户端 (`clients/typescript/src`) 和 `examples/02_remote_agent_server/`。 消费者方法是一个入口：将其列在族中。
6. **错误和边缘状态**：`HTTPException`详细信息、处理程序中的状态代码、`deprecated=True`路由及其删除版本。 这些是幸福之路从未出现过的状态。
7. **现有测试**（`tests/agent_server/`、`tests/cross/`）是请求形状和预期行为的参考，而不是证明。

`control-agent-server map coverage` 列出了没有家庭拥有的路线 (`unowned`)、没有配方驱动器拥有的路线 (`owned_but_not_driven`) 以及两次声明的路线。 将 `unowned` 驱动为零，或在索引的“未映射”部分列出每个排除及其原因。

<a id="2-group-into-families"></a>

## 2. 分组为家庭

每个面向智能体的作业（“对话生命周期”、“LLM 配置文件”、“Bash 命令”）一个文件，而不是每个路由器。 瞄准智能体可以在其中验证的文件
坐：通常有5到20个子功能； 分裂超过约30。 命名文件
`Fnn-short-slug.md` 并为家人提供 ID `Fnn`。 保持 ID 永远稳定：当路线或场地移动时，更新文本，而不是 ID； 当删除某个功能时，将其标记为`retired`并授予授权PR，而不是删除该行。

**子功能**是一个具有自身通过/失败行为的可观察行为，例如“重启后会话保持暂停状态”或“未知ID返回404”。 ID 类似于 `F03.pause`：小写、连字符、在地图上唯一、以家庭 ID 为前缀。 取证前先整理好ID，并写下
首先将`## Sub-features`列表放入文件中：证据和账本行在其下归档（`evidence add`和`map check`拒绝未知ID），稍后重命名意味着重新证明。

同一操作的全局和对话范围的变体（例如
`/api/bash/...` 和 `/api/conversations/{id}/bash/...`) 属于拥有该业务的家族； 范围变体是第二个入口，当其行为不同时（它作用于哪个目录或容器），它具有自己的子功能。

<a id="3-write-each-entry"></a>

## 3. 写下每个条目

每个文件都以 H1 标题开头，其中有一段描述智能体可见行为，然后：

- 一 `Source:` 与反引号中的主要实现路径（路由器、服务、模型； `map owners` 使用这些前缀将更改的文件路由到系列，因此列出目录或文件，而不是符号），以及
- 来自固定词汇表的可选 `Needs:` 行命名机先决条件（`llm`、`tmux`、`git`、`node`、`uvx`、`docker`、`chromium`、
  `vscode`、`network` 用于出站 HTTPS 到 github.com 或提供商），因此
  `control-agent-server capabilities` 和 `map run --all` 可以区分受阻家庭和失败家庭。 只列出前置条件或大多数食谱需要的。 只有某些食谱需要的功能位于这些食谱自己的 `Needs:` 行上（见下文），
- 可选的 `Launch:` 行与 `launch --new` 标记系列需要（`` Launch: `--deferred-init` `` 或 `` Launch: `--Webhook-sink --config-JSON '{"max_concurrent_runs": 1}'` ``）；
  `map run --fresh` 和 `map run --all --fresh` 与他们一起发起家庭跑步活动，并且
- 一个 `Routes:` 行列出了这个家庭拥有的每条路线，每条路线都用反引号括起来，与 `map routes` 打印它完全相同（`GET /api/conversations/{conversation_id}`，
  `WS /sockets/events/{conversation_id}`），或 `Routes: none` 对于仅行为族（Webhook、SDK 泳道）。 `Routes:` 段落可以多行换行； 它以第一个空行结束。

然后是四个 H2 部分，按以下顺序：

1. `## Sub-features`：每个 ID 一颗子弹：
   `` - `F03.pause`: pausing a running conversation stops it and reports `已暂停`. ``
2. `## How to get to it (agent POV)`：每个入口，当消费者遇到
   it：REST路线，WebSocket，SDK方法
   (`RemoteConversation.pause()`)、TypeScript 客户端方法、配置字段或环境变量以及（仅适用于上下文）调用它的 Agent Canvas 表面。 注意每个食谱练习哪些入口。
3. `## Driving it with control-agent-server`开始于 `Preconditions:` (run flags, LLM profile 测试夹具，更早的子弹) 作为子弹，然后用方括号标记那些与一个消费者行动及其命令配对的子弹 `sh` 在子弹内部有一个块，观察结果如下：

   ````markdown
   - **Pause (`F04.pause`).** Pause a running conversation.
     ```sh
     CID=$(control-agent-server conversation start --prompt 'Run: sleep 30' --print-id)
     control-agent-server conversation wait "$CID" --until running --timeout 60
     control-agent-server api POST "/api/conversations/$CID/pause" --expect 200 --save F04.pause/pause
     control-agent-server conversation wait "$CID" --until paused --timeout 30
     control-agent-server api GET "/api/conversations/$CID" --check execution_status eq paused
     ```
     The wait reports `paused` and a GET confirms it.
   ````

   该映射是可执行的： `control-agent-server map run --file F04` 运行每个
   `sh` 按家庭块顺序，一次性处理，携带壳变量（`CID=...`从子弹到子弹，任何命令退出非零都会失败。 所以，将每个期望编码到命令中： `--expect` 对于状态， `--check FIELD OP VALUE` 对于主体（`eq`, `ne`, `lt`, `ge`,
   `contains`, `matches`, `exists`, `missing`, `len-eq`, ...),
   `--expect-kind`/`--contains` 用于事件和帧，`--expect-min` 用于接收器传输，普通 `test` 用于文件。 散文陈述了读者应该看到的内容； 命令证明了这一点。 散文中的内联代码永远不会执行，因此预期值和部分命令可以保持内联。 下面的一个 `sh` 块
   首先执行`Preconditions:`。

   使用另一个项目符号的变量或文件的配方在项目符号中的自己的行上声明它们，就在其第一个 `sh` 块之前：
   `Requires:` 后面是反引号中的早期子功能 ID。 例如，对 `F33.conversation-streaming` 的依赖使得
   `--only F33.conversation-token-callbacks` 首先运行流式传输。 选择按照家族顺序传递地包括这些先决条件。 `map check` 拒绝依赖于没有命名更早的食谱的依赖项，同时标记一个在赋值之前读取变量的食谱（`map run` 在每个项目之间进行行首赋值，因此未选中的生产者会留下变量为空）。 文件和服务器状态（存储设置、汇流器的请求）不进行跟踪：手动声明这些依赖项，并在`--only`上进行检查。 `map run` 在启动服务器之前拒绝未知的选定 ID。 保持对成功生产其测试夹具的普通配方的依赖。

   一个需要机器能力的食谱就明说需要一个 `Needs:` 在下面的线段上 `Requires:` （与家族谱系相同的词汇）。 当这台机器缺少它时， `map run` 报告该食谱，以及所有需要该食谱的食谱 `blocked` 无需运行它们，驱动了  REST 家庭成员 `capabilities` 按家庭列出。

   每个项目符号都在其自己的进程组中运行，当项目符号结束时，进程组 `map run` 就会停止，因此普通的 `cmd &` 的生命周期与它的项目符号一样长。 一个后来用到的后台进程（一个测试夹具服务器，一个代理）从`control-agent-server helper start --name NAME -- CMD ...`开始运行，独立于会话，被注册到运行中，并在结束时
   `helper stop NAME` 或 `stop`。

   两个标签标记使地图保持诚实，而不会永远变成红色：
   **已知错误**和**已被阻止**。 一颗子弹，其粗体标签写着 **known
   错误**（例如
   `**Stale secrets after update (`F08.secrets-visible`), known bug #1234.**`) 遵循下面的已知错误合同。 标签为 **blocked** 的项目符号在散文中命名其先决条件，报告为 `blocked`，并且不会执行。 后面的项目符号从不依赖于这两种类型中设置的变量。

   **已知错误合约。**与兄弟姐妹保持这些规则一致
   验证技能（OpenHands/OpenHands中的verify-OpenHands，OpenHands/automation中的verify-automation），因此证明在每个中意味着相同的事情：

   - 该项目符号断言**正确**行为。 因为bug导致命令失败，其行尾带有`# bug: PREDICATE`，而谓词则指出了bug的自身症状：它产生的值或错误，而不是整个响应。
   - 三个结果。 `xfail`：标记的命令失败**且**其谓词成立（已记录的错误已重现）。 `xpass`：每条命令都通过，因此观察到了正确的行为； `map run` 失败，因此标记被删除。 `fail`：任何其他情况，包括标记命令的不同失败（401、404 或 503，其中 bug 为 500）、首先中断的排列步骤、超时、没有确认断言位置的提前退出，或者在系列先决条件或其 `Requires:` 闭包中的任何配方（它需要的配方和它们的配方）之后的通过在运行早期失败（`--keep-going`），因为它的排列从未运行。
   - 谓词是由 `&&` 连接的 `PATH OP [VALUE]` 子句，匹配如下
     `--check` 针对 JSON 对象，在标记行上打印最后一个 `control-agent-server` 调用：
     `# bug: status eq 500 && response.body.exception contains 'has no attribute'`. `api` 调用打印 `status`、`response.status`、`response.body` 及其 `checks`； 其他动词打印它们的结果或`error`/`hint`；
     `--quiet` 删除 `response.body`，因此匹配 `checks.N.actual` 或离开
     `--quiet` 下线。 配方计算的值（shell 变量、保存的 JSON 文件、程序的输出）经过
     `control-agent-server assert --value|--json|stdin --check ...`，以便谓词可以通过 `# bug: value.status eq 200` 指定它。
   - 谓词中的每个路径都必须出现在该输出中，`missing` 下除外； 存储的 `null` 视为存在。 所以
     当检查运行但没有发现任何内容时，`checks.0.actual eq null` 有效，绝不会在没有 `checks` 的错误对象上有效。 谓词仅由
     `missing` 子句被拒绝：将其锚定在 bug 的输出所包含的内容上 (`value.success eq true && value.id missing`)。
   - `exit N` (标记命令的退出状态) 是最后的手段，对于没有意义的症状，比如一个 TypeScript 编译失败的类型错误退出状态为 2。 它只是说该线路以这种方式失败了。
   - `xpass` 必须表示观察到正确的值，因此标记的命令肯定断言。 `map check` 拒绝 `if cmd; then false; fi`，
     `# bug` 行上的 `! cmd` 和 `test !`，因为不相关的错误
     `cmd` 将被视为修复； 使用动词自己的期望（`ws stop --expect-close`、`api --check`）或`assert`。
   - `map check` 拒绝缺失或格式错误的谓词，以及不调用 CLI 的行上的 `PATH OP` 谓词。
   - 一个修复程序通过基线重现(`xfail`)两次，修复程序通过(`xpass`)两次，使用相同的配方、标志和测试夹具（参见SKILL.md，“验证现有修复程序”）。

   包括只读每个变异的第二视角（a GET, a WebSocket 文件在磁盘上的帧，sink交付），需要注意的错误情况（404 对于未知 ID，422 对于坏体，401 无密钥，409 对于冲突），以及 `--save` 在证明结果的交易所。
4. `## Gotchas`：浪费或无效化运行的陷阱：异步需要等待的转换，智能体之后才出现的字段，依赖配置、平台或已安装二进制文件的行为，以及已知的开放问题（链接它们） 它们是复制候选者，而不是豁免者）。

将命令视为字面意思：引号 JSON 使用单引号时，确保名称仅在运行时唯一（前缀） 测试夹具与 `qa-` 或 `QA_`），并在突变后恢复共享状态（删除机密除非下一个食谱依赖于它，否则（重新）激活默认配置。 每次运行时不同的值（对话 ID、事件 ID、命令 ID）被捕获到 shell 变量中
with `--print-id`, `--field` or `--print-path`, never pasted as literals:
`CID=$(control-agent-server conversation start ... --print-id)`.

驱动子弹必须在一个炮弹中运行一次，从上到下运行，因为下一个智能体将以这种方式运行它们：

- 按执行顺序将每个排列步骤放入 `Preconditions:` 中。 生命周期较短的先决条件（正在运行的对话）表示何时创建它：“就在暂停项目符号之前”。
- 项目符号从不依赖于后面的项目符号创建的状态，并且永远不会删除后面的项目符号需要的测试夹具。
- 将环境依赖的结果作为条件表达式（例如，“如果 `tmux` 安装了，...”）。 否则 503 与...”）并检查它们，而不是从内存中检查它们。
- 发生任何变化后，通过第二条路线读回存储的值； 返回 200 但未存储任何内容的写入是一个典型的 API 错误。
- 异步结果（运行完成、Webhook 刷新、后台 bash 命令）等待 `conversation wait`、`ws start`/`ws stop`, or `sink 读取
  --expect-min`, never with a bare `sleep`除非服务器自己的计时器是
  被测试的东西（这么说）。
- 断言确定性事实（状态代码、字段、智能体写入的文件、工具观测结果、事件类型），而不是模型的措辞。
- 机密检查断言服务器返回或存储的内容，而不是模型的内容
  说：模型拒绝回显机密。 比较命令内部
  （`control-agent-server api GET ... --check value eq "$EXPECTED"`，或
  `state cat ... --not-contains "$SECRET"` 用于存储在 REST）并且从不打印真正的密钥。

<a id="recipe-pitfalls-that-reviews-keep-finding"></a>

### 评论不断发现的食谱陷阱

- `! cmd` 在 `set -e` 下永远不会失败。 写入 `if cmd; then false; fi`，或使用 `--check`/`--expect` 断言（`map check` 对其进行标记）。
- 粗体标签必须独占一行； 包裹的 `- **...` 默默地将项目符号合并到前一个项目符号中（`map check` 对其进行标记）。
- 需要在相同服务器上有一个正向控制：展示检查可以通过（正确键进入，cookie加载文件），而不是展示错误输入被拒绝。
- 当服务器等待帧时，“保持开放”并不能证明任何事情。 发送如果行为错误将被拒绝的帧，并等待回复（`--until-kind`，`--expect-kind`）。
- 计时需要两个界限：只有下限的超时检查可以通过更长的超时（`--expect-max-ms` 或 `test $((SECONDS - T0)) -le N`）。
- 被拒绝的请求也必须不留下任何痕迹：401 (`--check-header set-cookie missing`) 上没有 `Set-Cookie`、没有新文件、没有事件。
- 突变是通过第二次读取来证明的，而不是通过它自己的反应来证明。
- 长时间或快速的等待使用 CLI 的等待 (`conversation wait`,
  `ws stop --wait`, `api --until-ok`, `sink read --expect-min`)，绝不是裸露的
  `sleep` 在断言之前。
- 大主体：`--quiet` 保持较小的输出，而 `--check` 仍然看到整个主体； `--raw-out` 保留字节。
- 当另一个命令探测服务器在后台运行时必须正在运行的请求（`control-agent-server api ... &`，然后是 `wait`）；
  `map check`解析它。 仅当配方运行时才会对 shell 变量 (`--expect-count "$N"`) 中的值进行类型检查。
- 模型可以通过消息或通过 `finish` 工具进行答复。 通过任一方式留下的内容来证明模型的转向：完成 token in
  `stats.usage_to_metrics`、智能体、`MessageEvent` 或 `ActionEvent`。
- 不要指向共享路径（`--env TMUX_TMPDIR=/tmp/x`，固定端口，工作区外部`$AGENT_SERVER_VERIFY_RUN`）：每个运行都有自己的，共享的会导致并行回放耦合。

<a id="4-prove-every-recipe-live"></a>

## 4. 现场证明每一个食谱

在新的 `launch --new` 上按顺序执行您编写的每个命令（或自上次意外以来您修改过的运行）。 在移交文件之前，从顶部再次运行整个文件，与所写的完全一样，使用
`control-agent-server map run --file Fnn --fresh --record`; 它用家族的 `Launch:` 旗帜发起新的奔跑，重播每一颗子弹，停止奔跑，并且必须从头到尾通过。 由模特支持的家族经营
`control-agent-server llm preset deepseek` 在 `sh` 块下
`Preconditions:`，因此新的重播只需要环境中的密钥即可。 需要第二个服务器的子弹在自己的服务器内发射
`sh` 块（`B=$(control-agent-server launch --new --print-run ...)`，则
`--run "$B"`) 并在子弹结束前停止。

对于每个子特征记录
`control-agent-server evidence add --feature <ID> --result pass|fail|blocked|not-run` 与入口、预期结果和实际结果以及保存的工件。

- 由于说明错误而失败的配方：修复说明并重新驾驶（地图漂移）。
- CLI 无法表达的配方：首先检查 `control-agent-server --help` 和子命令帮助，然后扩展 CLI 并重新驱动（线束间隙）。
- 由于服务器故障而失败的配方：保留预期结果，记录`fail`并提供证据并单独报告产品错误。
- 需要 Docker 服务、云账户、OAuth 提供者或 GitHub token、macOS 的食谱应标记为 `blocked`，在 `Preconditions:` 中注明必要条件，并尽可能详细地编写食谱。

`blocked`是最常见的错误判断。 在你写之前，尝试一下早期地图绘制者错过的更便宜的路线：

- 测试夹具可能已经存在：`control-agent-server fixture list`（git 存储库、技能、stdio MCP 服务器、HTTP 接收器）。
- 本地替代品通常会执行与外部服务相同的代码路径：本地 Git 仓库而不是 GitHub, stdio MCP 服务器而不是托管的，本地目录而不是市场 URL, an HTTP 将 sink 而不是自动化服务。
- 大多数服务器模式都需要启动标志：`--no-auth`、`--deferred-init`、
  `--config-json`, `restart --env`.
- 当路径“因为每个 X 都需要 Y 而被阻止”时，首先按其真实属性列出每个 X； 其中之一通常不需要 Y。
- 在放弃之前先翻译环境：重述行为，不要使用平台名词（例如，“一个 Docker 环境”可能仅意味着“一个非本地运行时”）。 “GitHub”可能仅表示“git Remote”），并在替代程序执行相同的代码路径时使用替代程序对其进行测试。 将此类项目符号标记为散文翻译； 当缺失的环境本身就是被测试的行为时，它就被真正阻止了。

<a id="5-check-the-map"></a>

## 5. 查看地图

```sh
control-agent-server map check --file F03   # 正在编写其他条目时的一个条目
control-agent-server map check              # 整个地图：结构、ID、索引、命令解析、路线存在
control-agent-server map coverage           # 没有家庭拥有或驾驶的路线
control-agent-server map ids                # 每个 ID 及其文件，用于索引表
```

`map check` 会解析 map 中的每一个 `control-agent-server ...` 命令，使用真正的参数解析器（因此，重命名的标志会失败检查），验证每一条 `Routes:` 行上的路由，以及对应用程序的路由表中的每一个 `api METHOD PATH` 调用进行检查。 拥有索引的任何人（[特征地图/README.md](feature-map/README.md)）将新文件添加到家庭表中，包括其入口、前置条件和ID计数，并列出“未映射”原因。 `map check --fix-counts` 重写了计数和总计。 当多个智能体地图族并行时，每个只编辑自己的文件并用`--file`检查它； 一名协调员随后更新索引。 然后将证据分类帐（`control-agent-server evidence report`）交给任何提出要求的人，首先失败并阻止行。
