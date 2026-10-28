---
name: verify-agent-server
description: >
  This skill should be used to "verify Agent Server APIs", "test the REST or
  WebSocket API like an agent would", "drive the agent-server", "check an API
  change against a real server", "create or update the agent-server feature
  map", or "run the weekly API audit". Ships control-agent-server (launch,
  doctor, api, ws, llm, conversations, fixtures, exec, assert, evidence, map) and the
  maintained map of every agent-facing feature.
triggers:
- /verify-agent-server
- agent-server feature map
---

<a id="verify-the-agent-server-through-its-real-api"></a>

# 通过真实的API验证Agent Server

证明 API 消费者观察到的内容，而不是处理程序返回或 CI 传递的内容。 消费者是智能体以及承载它们的程序：SDK的
`RemoteConversation`/`RemoteWorkspace`、TypeScript 客户端、Agent Canvas 和自动化。 三部分协同工作：

1. **`control-agent-server`** ([scripts/](scripts/)) 是控制杆。 它将此结账作为独立的实服务器（私有`HOME`，持久化目录，配置文件，会话密钥，机密密钥，端口）启动，并将每个API步骤转换为你可以重跑的命令：REST调用，WebSocket捕获，LLM-后端对话，测试夹具，SDK程序。
2. **功能图**（[references/feature-map/](references/feature-map/README.md)）列出了每种智能体-面行为的稳定ID，每个家庭拥有的路由，入口（REST、WebSocket、SDK和TypeScript客户端方法），精确`control-agent-server`食谱，可观察结果和陷阱。
3. **证据**：保存的请求/响应交换、WebSocket帧、Webhook交付和程序转录，还包括一个生存清理后存活的通过/失败/被阻止/未运行的账本。

此技能和地图都不会授权外部写入、超出您预算的付费模型或用户未要求的产品修复。

<a id="the-cli-comes-first"></a>

## CLI 排在第一位

将其放在 `PATH` 上并首先阅读其帮助：

```sh
export PATH="$PWD/.agents/skills/verify-agent-server/scripts:$PATH"
control-agent-server --help              # 然后：control-智能体-server <command> --help
```

要求：存储库根目录中的`make build`（或`uv sync --dev`）； 的
CLI 在存储库的 `.venv` 上运行，不需要任何其他东西。 测试夹具需要 `git`，bash 和终端工具需要 `tmux`，模型支持的配方需要 DeepSeek 键。 每个命令打印一个 JSON 对象； 退出 0 正常，1 操作失败，2 使用情况，3 环境。

在 PID 1 不收割子级的容器中，运行整个
`map run --fresh` 或在子收割器下测试命令，例如 `tini -s --`（Docker 的 `docker-init -s --` 也适用）。 对于手动运行，包装包含 launch、drive 和 stop 的 shell； 单独包装启动退出主管太早了。 否则，退出的后代可能仍然是僵尸，导致清理检查将其误认为是实时工作。 保留原始故障证据并报告此环境差异； 不要削弱清理主张。

如果面向智能体的路径无法使用 CLI 行驶，则为 ** 线束
间隙**：扩展`scripts/control_agent_server.py`（记录动词在其
`--help` 包含示例并在此文件中），现场证明，然后编写配方。 切勿使用未跟踪的一次性脚本来解决下一个智能体无法重新运行的间隙。 `api` 和 `ws` 到达每条路线，因此大多数间隙是关于等待、测试夹具或观察副作用，而不是关于调用端点。 其他智能体可能正在运行相同的脚本：编辑副本，运行其测试并
`map check`，然后一步将其移动到位。

<a id="launch--doctor--drive--evidence--cleanup"></a>

## 发射→医生→驾驶→证据→清理

```sh
export AGENT_SERVER_VERIFY_RUN=$(control-agent-server launch --new --print-run)
control-agent-server doctor                     # 只读; 开车前必须没问题
control-agent-server llm preset deepseek        # deepseek-flash（主动）+ deepseek-pro 从 $DEEPSEEK_API_KEY
CID=$(control-agent-server conversation start --prompt 'Create hello.txt containing hi' --wait --print-id)
control-agent-server conversation events "$CID" --kinds ObservationEvent --contains hello.txt
control-agent-server api GET "/api/conversations/$CID" --expect 200 --save F03.get/after-run
control-agent-server evidence add --feature F03.get --result pass --entry "GET /api/conversations/{id}" \
  --expected "execution_status finished" --actual "finished" --artifact evidence/F03.get/after-run.json
control-agent-server stop                       # 仅停止本次运行； 证据保留
```

- **哪个运行。**命令使用 `--run DIR`（该行中的任何位置），否则
  `$AGENT_SERVER_VERIFY_RUN`否则，唯一存活的运行。 他们拒绝猜测，所以导出 `AGENT_SERVER_VERIFY_RUN` 在每个 shell 中，当其他智能体分享机器：一个智能体这会破坏他人的运行，从而破坏证据日志。 从未 `pkill -f` 或 `killall` 按照模式；
  `control-agent-server stop` 仅结束运行的进程组。
- **Launch**运行在自己的进程组中，从checkout开始，`python -m openhands.agent_server`cwd，`HOME`，`OH_PERSISTENCE_DIR`，配置文件(`OPENHANDS_AGENT_SERVER_CONFIG_PATH`)，tmux目录，工作树根，机密会话密钥(`OH_SESSION_API_KEYS_0`)和`OH_SECRET_KEY`密钥都是私有的。 调用者的`OH_*`、LLM和云变量不被继承； 使用 `--env K=V` 或 `--pass-env NAME` 传递菜谱所需的内容。 有用的变体：
  `--no-auth`（未经身份验证模式），`--deferred-init`（休眠直到
  `POST /api/init`)、`--webhook-sink`（连接到配置的录音 Webhook 接收器）、`--config-json '{...}'`（任何其他配置字段）、`--vscode`、
  `--preload-tools` 和 `--checkout PATH`（另一个工作树，用于基线）。 地图配方中的嵌套启动继承所选的结账； 明确的
  `--checkout` 覆盖它。
  `attach --url ... --key-env VAR` 驱动您未启动的服务器（Docker 映像、PyInstaller 二进制文件、远程沙箱）； `stop` 永远不会杀死它。 启动拒绝在可用空间少于 1 GB 的情况下启动：模型对话的运行可容纳 300 到 600 MB。
- **Doctor** 检查进程组，该运行是否拥有其端口，`/alive`，
  `/health`, `/ready`, `/server_info` (版本，以及) `build_git_sha` 是结账的 HEAD), 一个缺少的密钥被拒绝（401），运行的密钥被接受，一个过期的密钥被拒绝， OpenAPI 文档 WebSocket 第一帧认证（坏密钥以4001码关闭），日志中包含调用堆栈。 在每一次令人惊讶的失败之后、在归咎于产品之前，先运行它。
- **沿 `api METHOD PATH` 行驶 **（任何 REST 路线，包括 `OPTIONS` 和 `HEAD`； `--auth none|bad|previous|bearer|bearer-bad|init` 对于授权案例，
  `--expect` 状态，`--check FIELD OP VALUE` 和 `--check-header` 为正文和头，`--field` 链接值为 shell 变量，`--jar` 为 cookies，`--until-ok` 为 poll，`--save FEATURE/NAME` 为 evidence)
  `ws listen|start|read|stop`（任何WebSocket；
  `--auth first-frame|query|header|none|bad|bad-query|bad-header|previous|key`,
  `--expect-reject` 用于关闭代码，使用 `--query resend_mode=all` 重放，跨越其他命令的后台捕获，`--wait` 在 `read|stop` 上进行轮询，直到达到预期），
  `conversation start|wait|send|events`（基本智能体途径），
  `sink read` (什么 Webhook，如凭据接收的)，
  `state ls|cat|grep`（服务器已持久化和机密不在其中）、`config` 和 `capabilities` 以及 `exec -- <program>`（注入了 `AGENT_SERVER_URL` 和 `SESSION_API_KEY` 的 SDK 或 TypeScript 客户端程序）。 `logs --grep`使用机密已脱敏读取服务器日志。
- **安排，不要造假。**  `llm`, `fixture` 并调用设置方法 `api` 存在以满足预条件（配置的模式、一个 Git 仓库、一个技能、一个 stdio） MCP 服务器，一个 HTTP sink). 它们永远不会被视为消耗它们的功能的证据； 地图上标明了哪些步骤是证据。 不要修补服务器模拟对象服务器响应使进行实时检查通过。 唯一的替代方案是 `fixture llm-stub`: an OpenAI在环回上兼容的提供者，重播脚本步骤`reply`, `tool`, `status`, `hang`通过服务器的真实 LLM 客户端。 仅用于提供者行为，即一个真实模型无法按需生产的401、500、挂起或一个精确的工具调用例如
  `finish` 或有风险的命令）； 每条幸福的道路都运行在真实的模型上。 状态步骤可以包括提供者错误主体，例如
  `--step 'status:429:{"error":{"message":"Quota exceeded","type":"insufficient_quota","code":"insufficient_quota"}}'`，因此可以区分配额耗尽和瞬时速率限制。 一个使用了 HTTP 测试夹具服务器和代理的本地烹饪过程，现在运行在 `helper start --name NAME -- CMD` 而不是 `CMD &`：`map run` 在每个子弹的进程组结束时结束。
- **状态控制**达到状态，没有模拟对象，一条幸福的道路永远不会显示：
  `restart`（重启后相同状态：持久化，恢复，重新连接），
  `restart --hard`（SIGKILL：崩溃恢复）、`restart --rotate-key`（过时的会话密钥）、`launch --share-conversations-from RUN`（同一会话的第二个实例：租用和接管）、`restart --env K=V` 或
  `--config-json`（配置更改，例如 `max_concurrent_runs` 或空闲 TTL），
  `launch --deferred-init`、`launch --no-auth`、`conversation start --no-run` 和 `ws start` 在操作之前，以便实时捕获其事件。
- **证据**属于`<run>/evidence/<feature-id>/`和仅附加分类账`<run>/evidence/ledger.jsonl`。 没有任何内容被覆盖：重复的名称将保存为 `<name>-2.json`，因此请引用命令打印的路径；
  `evidence report` 呈现 [ 报告合同 ](references/report.md)。 CLI 编辑运行的密钥，`$DEEPSEEK_API_KEY` 和密码加密的值
  from output and evidence, including `--field` and `--print-header`. Only
  具有任一标志的 `api --unsafe-unredacted` 返回往返的原始机密值； 直接在变量中捕获这些内容并将其排除在报告之外。 证据仍然存在已脱敏。 密钥、日志和状态保留在 `<run>/private/` 中。 证据不会自动公开：在发布之前先阅读它。
- **清理**和`control-agent-server stop`（添加`--purge-private`以删除密钥，一旦检查证据，请说明和测试夹具）。 它仅向此运行启动的进程组发出信号（服务器、HTTP 接收器、后台捕获、帮助程序）并验证端口已关闭。

<a id="llm-budget"></a>

## LLM 预算

对于需要模型的所有内容，请使用 `deepseek-flash` (DeepSeek V4.1 Flash)； 仅当检查需要第二个配置文件或更强大的模型时才切换到 `deepseek-pro`。 保持提示词微小、确定和局限于对话的工作区（“创建 hello.txt，包含：hi”），并在工具观测结果和文件上进行断言，而不是在模型的用词上。 停止或删除菜谱不再需要的对话。 如果没有密钥，则运行每个无凭据的配方，并将依赖于模型的配方记录为 `blocked`，但缺少先决条件； 永远不要替换模拟对象并称其为通过。

对于批评者检查，请使用可用的、授权的 OpenHands (`openhands/…`) 或兼容的 OpenHands LLM 代理配置文件，无论用于通行证的主配置文件如何。 当 `verification.critic_api_key` 未设置时，SDK 会重用其 LLM 键。 之后恢复之前的配置文件。 不要仅仅因为主模型使用了另一个提供者就宣布批评家被屏蔽。 这并不授权新的凭据、额外的预算或将私人测试数据发送到其他服务； 在记录传球之前需要真实的得分事件。

<a id="choose-the-job"></a>

## 选择工作

- **验证更改或 PR**：将更改的路径映射到功能 ID
  `control-agent-server map owners --changed origin/main...HEAD`，驱动每个入口这些功能列表（REST、WebSocket、SDK、TypeScript 客户端），并使用 [ 报告合同 ](references/report.md) 进行报告。 行为改变也需要回归测试（通常在
  `tests/cross/test_remote_conversation_live_server.py`); 配方是活生生的证据，不能代替测试。
- ** 验证现有修复**（一个已打开的PR或已合并的提交，声称修复了`known bug`条目）：在基线上重复两次，修复也重复两次
  with the same flags and fixtures:
  `control-agent-server map run --file Fnn --only Fnn.x --fresh --repeat 2 --checkout <base worktree>` 必须在两次尝试中报告项目符号 `xfail`，并且两次尝试中都必须报告没有 `--checkout`（修复）`xpass` 的相同命令。 `xfail` 表示标记的命令失败，其 `# bug: PREDICATE` 文档失败（请参阅
  [the marker contract](references/mapping.md)); any other failure on the
  基线是 `fail`，因此证明不能 REST 不相关的错误。 然后将标记放入同一个 PR 中。 基线不复制两次意味着“不确定”，永远不会“固定”。 `--only` 拒绝未知 ID，并按系列顺序运行每个选定配方的传递 `Requires:` 先决条件。
- **创建或扩展地图**：遵循[参考/mapping.md](references/mapping.md)。
  `control-agent-server map coverage` 衡量没有家庭拥有或驾驶的路线。
- **重新证明地图**：每个家庭的食谱都被围起来`sh`块，其命令断言了自己的期望，所以
  `control-agent-server map run --file Fnn --fresh --record` 重现一个家庭在第一次运行时（带有家庭的`Launch:`标志），需要在第一个食谱之前通过`doctor`，并写入账本行，`control-agent-server map run --all --fresh --record` 重现整个地图。 只有失败的子弹才需要判断； `known bug` 项目符号报告预期的失败，直到错误得到修复。
- **运行每日通行证**：遵循[参考文献/daily.md](references/daily.md)：静态检查（`map check`，`map coverage`），家庭自
  地图索引的 `Maintenance baseline` 行 (`map baseline`; `map owners` 无参数的差异与它本身没有关系，也没有其他东西：在 `main` 范围内没有触及的家庭等待周票，以及一个没有新提交的票。 完成其改变的家庭的通行证建议
  `TARGET` 作为下一个基线，`map baseline --set "$TARGET"` 在其 PR 中； 当昨天的账本临近时，将账本与 `evidence report --baseline` 进行比较。
- **维护地图（定期或每周）**：关注
  [references/maintenance.md](references/maintenance.md): a frozen BASE/TARGET,
  路线差异、PR意图分类账、源波、每个家庭的一次实时传递，以及最多一个PR经过验证的更正。

<a id="triage-what-you-find"></a>

## 对您发现的内容进行分类

- **地图漂移**：地图描述了服务器在设计上不再执行的操作。 使用当前来源和现场证据修复条目。
- **线束间隙**：服务器可以工作，但CLI无法驱动或观察它。 修复CLI，重新驱动。
- **产品错误**：服务器损坏。 保留证据，查找现有问题，并单独报告：Agent Server、SDK 和 TypeScript 客户（`OpenHands/agent-sdk`），Agent Canvas 用户界面（`OpenHands/OpenHands`），调度和派送（`OpenHands/automation`）。 永远不要重写预期结果来祝福破坏的行为。
- **已阻止**：命名缺少的先决条件（密钥、帐户、Docker、二进制文件、操作系统）以及您尝试的路线。 遥不可及永远不是通行证。
  `control-agent-server capabilities` 表示该机器可以驱动什么以及哪些系列的 `Needs:` 未满足。 一个家庭的`Needs:`线将整个家庭门控在`--all`下； 配方自己的 `Needs:` 行仅阻止该配方和需要它的配方，因此该系列的 REST 仍然可以在没有它的机器上运行。

<a id="how-this-fits-with-the-tests"></a>

## 这如何与测试相符

单元测试 (`tests/agent_server/`), 在线实时服务器测试（`tests/cross/test_remote_conversation_live_server.py`), 压力测试， 该测试 REST 断开检查（与上一个版本进行 oasdiff）和  TypeScript 客户端的端点审计合同，孤立进行，使用脚本 LLMs. 该技能证明了组装的服务器是智能体使用它：一个真实的过程，真实持久化并重启，真实套接字和 Webhook, 并且是一个真实模型。 它不会取代其中任何一个。

请参阅 [references/adaptation.md](references/adaptation.md) 了解这些想法的来源以及故意遗漏的内容。
