<a id="full-agent-server-maintenance-intent-ledger"></a>

# 完整 Agent Server 维护：意图分类账

记录于 2026 年 10 月 23 日 UTC。 在 `5966c781ed014efc96c028a99bddd4ff78426741` 处分叉目标 `enyst/agent-sdk`； 接受的维护基线 `8ba966d1d3af49f08e04349c055009e1614b48d6` (2026-10-07)。 克隆并不浅。 该范围内的所有 130 次提交均通过上游 GitHub 提交到拉取 API 得到解决； 全部解析为相关的PR。 提交主题正则表达式未用作该关联的来源。

意图和运行时是独立的。 记录的列记录了每个合并的内容 PR 所说的内容； 它并不断言实施有效。 运行时在 [ 每个 PR 覆盖层 ](intent-runtime-overlay.md) 中单独协调； 它完成了家庭扫荡、特定名称特征结果、能力限制以及未运行的行的快照记录，而不将广泛的家庭通过视为整个 PR 的证明。 更改的源前缀针对共享设置、事件、LLM 配置、启动分辨率和终端使用者进行了扩展。 广泛的家族所有权是经过深思熟虑的； 需要完整的实时通行证。

已获取到所有关联的PR描述、完整更改文件列表、审查体、内联审查评论、问题讨论以及相关问题体/接受标准。 原始公共 API 记录位于 `intent-api/` 中； 连接的数据集是 `intent-commits.json`、`intent-prs.json` 和 `intent-linked-issues.json`。 分类账引用了相关的陈述意图并记录了下面的相关审查决定。 PR 描述没有改变。

REST 兼容性报告：其中 112 个 PR 有记录的 `agent-server-rest-api-breakage-report` 评论； 所有 112 人都说 PASSED。 其余18人在返回的讨论中没有这样的评论； 缺席不是兼容性通行证。 通过发布基线检查也不能证明当前的运行时行为。

<a id="deliberate-changes-that-require-map-reconciliation"></a>

## 需要地图协调的故意更改

- #5987 添加严格的插件获取预检和 `POST /api/plugins/fetch`； 源获取不得默默地使用过时的缓存修订。
- #5126 添加了服务器拥有的 `start_child_conversation` 工具和可插入启动器，这是工具/对话系列下的新行为。
- #5983 故意删除了之前在 #5409 中引入的未发布的内联 `agent_profile` 启动。 如果可能，存储的配置文件将被激活； 仅损坏的默认设置保持不变，没有活动配置文件和网关 409。 其请求的更改审查在合并之前已得到解决。
- #5981 添加个人资料公开技能选择和评论家关键回退方案； #4960 添加启动时附加技能。 共享启动路径和消费者需要覆盖。
- #5182 添加持久的 `SecurityAnalysisEvent` 记录。 事件排序，持久化并且两个客户端都是消费者。
- #5341 在已安装的 Canvas 应用程序上公开 `requested_ref`，保留更新客户端的固定安装引用。
- 许多先前的审计缺陷在此期间得到修复。 现有的 `known bug` 标记需要技能的两个基线 xfail/两个目标 xpass 证明才能移除； 单独解决问题或合并 PR 是不够的。

<a id="commit--pr-summary"></a>

## 提交/PR摘要

| 提交/PR | 改变路径 | 家庭 / 入口 | 预期结果：引用的 PR 证据 | 意图 | 运行时证据/限制 |
|---|---|---|---|---|---|
| `608a102c637d` / [#5467](https://github.com/OpenHands/software-agent-sdk/pull/5467) | `openhands-sdk/openhands/sdk/llm/utils/model_features.py`<br>`tests/sdk/llm/test_llm.py`<br>`tests/sdk/llm/test_model_features.py`<br>`tests/sdk/llm/test_vision_support.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - 将自动字符串-序列化器输入从裸的`"deepseek"`子字符串缩小到遗留的`"deepseek-v3.2"`家族，使得`DeepSeek-V3.2-Exp` / `deepseek-v3.2-reasoner`保持纯字符串内容，而v4、v4.1、`v4-flash-vision-exp`和`deepseek-chat`的id保持结构化（列表）内容。- 添加注册表回归覆盖以验证v4/v4.1 id 解析`force_string_serializer is False`，v3 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5467) |
| `91ac058a08fd` / [#5548](https://github.com/OpenHands/software-agent-sdk/pull/5548) | `.github/workflows/storage-scenario.yml`<br>`pyproject.toml`<br>`tests/agent_server/docker_runtime/STORAGE_SCENARIO.md`<br>`tests/agent_server/docker_runtime/test_storage_scenario.py` | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34 | - `tests/agent_server/docker_runtime/test_storage_scenario.py`：针对真实的 Docker 守护进程和智能体服务器映像进行五次测试。 服务器通过`OH_*`环境变量进行配置，就像CLI一样，并驱动真实的容器。 每个测试都会检查哪些内容必须保留以及哪些内容必须消失： 1. **仅可重建文件。**停止对话只会掉落 `~/.cache` 和 `~/.npm`； 超过磁盘预算th | 有记录的 | 具有能力限制的家庭扫荡； [特征证据和限制](intent-runtime-overlay.md#pr-5548) |
| `69e26889401f` / [#5538](https://github.com/OpenHands/software-agent-sdk/pull/5538) | `openhands-agent-server/openhands/agent_server/_secret_redaction.py`<br>`openhands-agent-server/openhands/agent_server/event_service.py`<br>`openhands-agent-server/openhands/agent_server/file_router.py`<br>`openhands-sdk/openhands/sdk/utils/files.py`<br>+3 条路径（完整列表如下） | F05, F06, F07, F08, F09, F10, F11, F12, F14, F18, F20, F21, F22, F31 | - `_create_zip_from_directory` 跳过在列出和读取之间引发 `FileNotFoundError` 的任何条目（文件或目录），并在读取之前跳过每个 `*.tmp` 文件； 每个替换的文件都像往常一样存档。 `atomic_write_text` 现在将其临时文件命名为 `.<name>.<random>.tmp` (`tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp")`)，并且会话租约之前已写入 `owner_lease.tmp` | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5538) |
| `0bb7b525c75f` / [#5547](https://github.com/OpenHands/software-agent-sdk/pull/5547) | `openhands-agent-server/openhands/agent_server/conversation_service.py`<br>`openhands-agent-server/openhands/agent_server/local_storage.py`<br>`tests/agent_server/test_local_storage.py` | F04, F05, F10, F12, F15, F31, F32 | - `delete_conversation` 现在在删除对话目录后呼叫 `remove_conversation_worktree(conversation_worktree_root, id)`。 - 它删除 `conversation_worktree_root/<id>/` 并在每个源存储库中运行 `git worktree prune`。 `openhands/<id>` 分支以及智能体的提交被保留。 - git 使用 `core.fsmonitor=false` 和 `--no-optional-locks` 运行，因为存储库配置是智能体-writab | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5547) |
| `97190b800444` / [#5342](https://github.com/OpenHands/software-agent-sdk/pull/5342) | `openhands-tools/openhands/tools/terminal/terminal/terminal_session.py`<br>`openhands-tools/openhands/tools/terminal/utils/command.py`<br>`tests/tools/terminal/test_terminal_parsing.py`<br>`tests/tools/terminal/test_terminal_session.py` | F13, F27, F33 | - 在完成结构化 `heredoc_end` 后，保留顶层脚本边界，使用现有的共享树-级 bash AST。- 保持普通以换行符分隔的命令和这里字符串分隔/拒绝。 不要修改不完整的输入回退方案，安全分析，确认政策，或用于执行的命令。添加基于表格的语法退化和实际tmux/subprocess终端会话覆盖 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5342) |
| `9f47d471ee6f` / [#5460](https://github.com/OpenHands/software-agent-sdk/pull/5460) | `openhands-sdk/openhands/sdk/llm/message.py`<br>`tests/sdk/llm/test_message.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - 当视觉功能激活时，即使强制使用字符串序列化，也保留消息的列表格式。- 仅包含文本的消息仍然使用强制要求的字符串形式，因此这些条目存在的原因得以保留。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5460) |
| `5c6e2589656a` / [#5582](https://github.com/OpenHands/software-agent-sdk/pull/5582) | `.github/workflows/server.yml`<br>`openhands-agent-server/openhands/agent_server/docker/Dockerfile`<br>`pyproject.toml`<br>`tests/cross/test_agent_server_build_metadata.py`<br>+1 条路径（完整列表如下） | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34 | - 将观察到的 Debian 快照从 2026 年 9 月 20 日推进到 2026 年 10 月 4 日 - 需要和锁 urllib3 2.8.0 以获取可用的安全修复程序 - 从 Python-slim 映像中删除 OpenVSCode，同时保留浏览器和 Docker 功能 - 明确报告在 Python-slim 中运行时禁用的 VS Code | 有记录的 | 具有能力限制的家庭扫荡； [特征证据和限制](intent-runtime-overlay.md#pr-5582) |
| `c980344bc78e` / [#5341](https://github.com/OpenHands/software-agent-sdk/pull/5341) | `openhands-agent-server/openhands/agent_server/canvas_extensions_router.py`<br>`tests/agent_server/test_canvas_extensions_router.py` | F28 | - 添加可选项 `requested_ref` to `InstalledCanvasExtensionResponse` 并填充它 `from_info`所以安装/列出/获取所有返回它。- 路由器测试安装 `github:org/repo` at `ref="v1"` (fetch patched) 断言 `requested_ref` 在安装和获取响应中 REST  API 合同更改与基础版本相比 OpenAPI  `d77ada7a030b` 对于公众 `/api/**` 路径。 ```diff --- base public OpenAPI +++ head public O | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5341)  |
| `16662b0bd2c1` / [#4784](https://github.com/OpenHands/software-agent-sdk/pull/4784) | `openhands-tools/openhands/tools/file_editor/utils/encoding.py`<br>`tests/tools/file_editor/utils/test_encoding.py` | F14, F27, F33 | - 返回 `utf-8` 当解码严格为采样字节时 UTF-8. - 保留 `utf-8-sig` 处理带有的文件 UTF-8 BOM. - 保持 `charset-normalizer` as the 回退方案非-UTF-8内容。- 在 `_recover_encoding`, try UTF-8 之前，因为字符正常化猜测 `get_encoding` 编辑器使用的路径不能切换有效 UTF将-8个文件转换为cp1251、cp1252或latin-1。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-4784) |
| `2804c1273b40` / [#5559](https://github.com/OpenHands/software-agent-sdk/pull/5559) | `openhands-agent-server/openhands/agent_server/api.py`<br>`tests/agent_server/test_api.py` | F01, F03, F05, F30, F31, F32 | - 智能体-服务器检查`$TMUX_TMPDIR/tmux-<uid>/openhands-<32 hex>`是否符合平台的套接字路径限制。 如果配置的或默认的目录太深，它会使用 `/tmp/openhands-agent-server-<pid>`。 - 当它覆盖了一个明确的 `TMUX_TMPDIR` 时，它会记录一个警告，并在关闭时恢复原始值。 - 短明确的 `TMUX_TMPDIR` 会像以前一样被完全尊重。 套接字命名和 i | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5559) |
| `9c4fd8c6664d` / [#4952](https://github.com/OpenHands/software-agent-sdk/pull/4952) | `openhands-agent-server/openhands/agent_server/profiles_router.py`<br>`tests/agent_server/test_profiles_router.py`<br>`tests/cross/test_remote_conversation_live_server.py` | F20 | - `GET /api/profiles/{name}` 和 `X-Expose-Secrets: plaintext` 的关联提供商应被解决。- 保存存储的凭据、活动默认值以及普通和加密编辑读取的现有未解决行为。- 覆盖加密提供商存储和凭据旋转，以及 HTTP 通过 `RemoteWorkspace.get_llm(profile_name=...)` 的实际选择。### REST API 合同变化与基础 OpenAPI `b66c7243 | 记录 | 家族扫除与已知缺陷` 相比。 [ 特征证据和限制](intent-runtime-overlay.md#pr-4952) |
| `d1bfda28da7f` / [#5619](https://github.com/OpenHands/software-agent-sdk/pull/5619) | `tests/agent_server/test_api.py` | 无需产品运行时间 | * 将默认路径选择测试与目录创建测试分开，避免在有关生产默认值的断言中使用随机测试夹具路径。 * 使用真正简短的最终目录进行真实的 TmuxPanePool 集成测试和寿命测试。 * 使用模拟规范路径添加确定性 macOS/Linux 套接字路径字节长度测试，无需全局猴子修补进程身份。 没有生产代码 | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5619) |
| `330441825052` / [#5616](https://github.com/OpenHands/software-agent-sdk/pull/5616) | `.github/scripts/update_npm_pin.py`<br>`.github/workflows/update-npm-pin.yml`<br>`openhands-agent-server/openhands/agent_server/docker/Dockerfile`<br>`tests/cross/test_agent_server_build_metadata.py`<br>+1 条路径（完整列表如下） | F01, F12, F16, F31 | - 升级共享的 npm pin 从 11.19.1 到 11.21.0，对于 ACP 和 canonical Node 运行时。- 添加一个每日/手动更新器，选择至少七天前的稳定、非已弃用同一版本。 切勿降级或编辑不明确的引脚。 - 使用现有机器人 PAT 打开草稿更新 PR，以便运行普通 PR CI。 无需自动合并，无需强制推送，无需重写人工审核； 一次一个待处理的 npm 更新， | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5616) |
| `cd17bd89d52e` / [#5673](https://github.com/OpenHands/software-agent-sdk/pull/5673) | `openhands-sdk/openhands/sdk/llm/utils/openhands_provider.py`<br>`openhands-sdk/openhands/sdk/llm/utils/verified_models.py`<br>`tests/sdk/llm/test_llm.py`<br>`tests/sdk/llm/test_model_list.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - `litellm_call_kwargs` 现在解析来自一个小表的路由 SDK 前缀：`openhands/` → `litellm_proxy/` + OpenHands 代理（不变），以及 `digitalocean/` → `openai/` + `https://inference.do-ai.run/v1`。 用户提供的 `base_url` 仍然获胜。- `VERIFIED_MODELS["digitalocean"]` 提供了一个简短的精选 DO 模型 ID 列表（来自 `GET /v1/models`），因此 DigitalOcean 出现在验证部分 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5673) |
| `9e76fe72b43f` / [#5182](https://github.com/OpenHands/software-agent-sdk/pull/5182) | `.github/agent-server-openapi-weak-schema-allowlist.json`<br>`openhands-sdk/openhands/sdk/agent/agent.py`<br>`openhands-sdk/openhands/sdk/agent/response_dispatch.py`<br>`openhands-sdk/openhands/sdk/event/__init__.py`<br>+5 条路径（完整列表如下） | F06, F07, F08, F32, F33, F34 | - **异步审计屏蔽**：在释放会话状态锁时解决工作人员中的惰性机密，然后重新检查注册表稳定性并在应用确认策略之前发出屏蔽审计。 回归覆盖范围使用真正的环回HTTP机密服务并在查找期间注册另一个机密。 - **`SecurityAnalysisEvent`** (`event/security.py`): `source="environment"`，而不是 `LLMConvertible`，所以模型 n | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5182) |
| `dd1af943cb49` / [#5683](https://github.com/OpenHands/software-agent-sdk/pull/5683) | `.github/workflows/stale.yml`<br>`MAINTAINERS` | 无需产品运行时间 | - 删除`.github/workflows/stale.yml`。 - 删除未使用的`MAINTAINERS`名册。 | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5683) |
| `bfc1ae71b0e0` / [#5670](https://github.com/OpenHands/software-agent-sdk/pull/5670) | `openhands-tools/openhands/tools/file_editor/editor.py`<br>`tests/tools/file_editor/test_basic_operations.py` | F14, F27, F33 | - 将实际文本行的数量用 `splitlines()` 而不是编号换行符代替。- 对于空文件，不要添加伪造的输出行。- 通过公共文件编辑路径覆盖未终止、单终止、空白结尾行和空文件。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5670) |
| `6d51e7262fc2` / [#5579](https://github.com/OpenHands/software-agent-sdk/pull/5579) | `clients/typescript/endpoint-audit.config.json`<br>`clients/typescript/src/__tests__/api-clients.test.ts`<br>`clients/typescript/src/client/acp-client.ts`<br>`clients/typescript/src/clients.ts`<br>+20路径（完整列表如下） | F01, F03, F04, F05, F06, F07, F09, F12, F18, F19, F20, F21, F22, F23, F24, F30, F31, F32, F33, F34 | - **`POST /api/acp/models`**（新`acp_router.py`）采用`agent_settings`加上相同的`secrets`地图作为对话开始（`LookupSecret`引用存储的机密工作）。 返回 `ACPModelDiscovery`: `current_model_id`（服务器的默认值），`available_models`，`agent_name`/`agent_version`，`supports_runtime_model_switch`，和 `error`（`ACPAuthRequired` / `ACPStartupTimeout` / `ACPSpawnError` / `ACPIni | 所述 | 家族扫除能力限制）； [特征证据和限制](intent-runtime-overlay.md#pr-5579) |
| `e8ad54729e43` / [#5671](https://github.com/OpenHands/software-agent-sdk/pull/5671) | `tests/integration/README.md`<br>`tests/integration/tests/c02_hard_context_reset.py` | 无需产品运行时间 | - 无需依赖模型生成事件计数，使 c02 的硬复位触发器变得确定性 - 验证实际复位语义：保留系统提示词，忘记所有其他先前历史，插入总结之后，然后产生一个系统首 LLM 请求 - 验证继续执行和一个随后的正常上下文压缩，该请求保留硬复位总结； 调整集成 README ### REST API 合同变更  | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5671) |
| `1d471742ea7b` / [#5609](https://github.com/OpenHands/software-agent-sdk/pull/5609) | `clients/typescript/package-lock.json`<br>`clients/typescript/package.json`<br>`clients/typescript/src/generated/agent-server-schema.ts`<br>`openhands-agent-server/pyproject.toml`<br>+5 条路径（完整列表如下） | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34 | ## 发布 v1.54.0 此 PR 准备版本 **1.54.0** 的发布。 **启动者：** @neubig ### 发布清单 - [x] 版本设置为 1.54.0 — 四个 Python 软件包和 TypeScript 客户端已同步。 - [x] 修复任何弃用截止日期（如果存在）- [弃用在当前头 298227f40](https://github.com/OpenHands/software-agent-sdk/actions/runs/37801967286) 上传递的截止日期。 - [ ] 集成测试通过（t | 有记录的 | 具有能力限制的家庭扫荡； [特征证据和限制](intent-runtime-overlay.md#pr-5609) |
| `c1c8c1c27824` / [#5682](https://github.com/OpenHands/software-agent-sdk/pull/5682) | `openhands-agent-server/openhands/agent_server/settings_router.py`<br>`tests/agent_server/test_settings_router.py`<br>`tests/cross/test_remote_conversation_live_server.py` | F18, F19, F32 | - 拒绝空值和已脱敏-placeholder values with HTTP 422之前持久化- 留下现有机密当无效的更新插入被拒绝时，值和描述保持不变机密 and existing-机密通过路由器和实时服务器测试的行为。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5682) |
| `9929c14e7d2f` / [#5614](https://github.com/OpenHands/software-agent-sdk/pull/5614) | `.github/workflows/integration-runner.yml`<br>`tests/integration/README.md` | 无需产品运行时间 | - 使用 V4.1 Flash 替换默认的 DeepSeek 型号 ID、显示名称和 litellm_proxy 型号映射。 - 更新集成覆盖文档； 其他模型和上下文压缩器默认值不变。 | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5614) |
| `1cfba2117e92` / [#5675](https://github.com/OpenHands/software-agent-sdk/pull/5675) |  | 无需产品运行时间 | 将1,000次调用指令替换为两个独立的Python终端命令，每个命令打印2,000次短语的重复。将token阈值提高到6,000，并保持种子上下文小，以确保单个工具结果在每个CI模型上以显著差距清除。将`keep_first=2`设置为使用户指令在第一上下文压缩命令后存活，而第二命令仍然运行。将迭代上限从10 t提高到100 t | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5675) |
| `e2bac66be26e` / [#5291](https://github.com/OpenHands/software-agent-sdk/pull/5291) | `openhands-sdk/openhands/sdk/llm/utils/model_features.py`<br>`tests/sdk/llm/test_model_features.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - 将 `"openai.gpt-"` 添加到 `SUPPORTS_STOP_WORDS_FALSE_MODELS`，位于 o1/o3/grok-4 旁边。 - 测试：五个必须删除停用词的 Bedrock ID，一个保留停用词的 Claude-on-Bedrock ID。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5291) |
| `c4b93299cf2b` / [#5661](https://github.com/OpenHands/software-agent-sdk/pull/5661) | `openhands-agent-server/openhands/agent_server/api.py`<br>`openhands-agent-server/openhands/agent_server/init_router.py`<br>`tests/agent_server/test_init_router.py` | F01, F03, F05, F30, F31, F32 | - `require_initialized` takes an `HTTPConnection`所以相同的依赖在  HTTP 和 WebSocket routes. HTTP 请求仍然返回 503 状态码。 WebSockets get `WebSocketException(1013 Try Again Later)`在握手被接受之前关闭套接字 `HTTPException` 从一个 WebSocket 依赖项将到达应用的 HTTP 异常处理器，它读取 `request.method` and fails.) - The | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5661) |
| `c96875fe3d03` / [#5703](https://github.com/OpenHands/software-agent-sdk/pull/5703) | `openhands-sdk/openhands/sdk/llm/utils/AGENTS.md`<br>`openhands-sdk/openhands/sdk/llm/utils/unverified_models.py`<br>`openhands-sdk/openhands/sdk/llm/utils/verified_models.py`<br>`tests/agent_server/test_llm_router.py`<br>+3 条路径（完整列表如下） | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - 包括经过筛选和验证的资料 OpenRouter routes in SDK 与他们的模型发现 `openrouter/` 前缀，独立于 LiteLLM成本地图。- 运行 HTTP 带有固定目录的过滤，以及排除和包含的过滤 OpenRouter entries 保留只保留目录的路由、排序、去重和提供者隔离。- 替换为实时目录模型和能力声明 SDK 合同检查，正确的编目指导 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5703) |
| `f824a949af7f` / [#5700](https://github.com/OpenHands/software-agent-sdk/pull/5700) | `openhands-agent-server/openhands/agent_server/api.py`<br>`tests/agent_server/test_init_router.py`<br>`tests/cross/test_remote_conversation_live_server.py` | F01, F03, F05, F30, F31, F32 | 在身份验证和`/api/*`、`/v1/*`和工作区-文件路由上运行延迟初始化门。将该门应用于所有Canvas后端入口，包括会话、HTTP代理和WebSocket路由。添加确定性过渡-竞争覆盖以及一个真实的Uvicorn/wsproto生命周期回归。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5700) |
| `4cc058275c5a` / [#4838](https://github.com/OpenHands/software-agent-sdk/pull/4838) | `openhands-sdk/openhands/sdk/mcp/client.py`<br>`tests/sdk/mcp/test_create_mcp_tool.py` | F19 | 重置已完成的 FastMCP 在现有会话下锁在重新连接之前。- 添加一个真实的 HTTP  回归测试并注入一个504响应，然后验证下一个工具调用成功。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-4838) |
| `3934349da2db` / [#5436](https://github.com/OpenHands/software-agent-sdk/pull/5436) | `openhands-sdk/openhands/sdk/llm/auth/openai.py`<br>`tests/agent_server/test_llm_router.py`<br>`tests/sdk/llm/auth/test_openai.py` | F04, F06, F07, F09, F20, F22, F23, F24, F30, F33, F34 | - 将 `gpt-6.1-sol`、`gpt-6-sol` 和 `gpt-6-luna` 添加到 ChatGPT 订阅白名单。 - 将订阅模型与 Codex ACP 模型目录分开。 当前`main`已经解耦这些表面，所以PR不再宣称拒绝的ACP适配器接受的模型。- 验证Agent Server订阅模型端点暴露完整的允许列表。- 为订阅LLM的构造覆盖参数化  | 有记录的 | 具有能力限制的家庭扫荡； [特征证据和限制](intent-runtime-overlay.md#pr-5436) |
| `3dcb27b227aa` / [#5715](https://github.com/OpenHands/software-agent-sdk/pull/5715) | `openhands-tools/openhands/tools/terminal/constants.py`<br>`openhands-tools/openhands/tools/terminal/terminal/terminal_session.py`<br>`tests/tools/terminal/test_terminal_session.py` | F13, F27, F33 | - 污染间隔从 `MIN_POLL_INTERVAL` 开始（0.02 秒），随着命令运行时间的增长 `elapsed / 4` 增长到 `POLL_INTERVAL`（0.5 秒）。- 一个命令在几毫秒内被注意到。- 如果命令运行超过 2 秒，每隔 0.5 秒就进行一次检查，如之前。- 没有命令的运行时间超过它现在的运行时间。- 新测试：第一个检查是 `POLL_INTERVAL` 的一半，间隔永远不会缩小，一个 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5715) |
| `c0471362d340` / [#5689](https://github.com/OpenHands/software-agent-sdk/pull/5689) | `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` | F28 | 在报告退出的后端为不健康之前，先收割拥有进程组。 保留TERM到KILL的优雅重启，而由已退出的领导者遗留下来的后代则立即终止。 - 在直接重启之前回收已退出的运行时，使其进程组保持存活期间阻止强制安装和数据删除。 - 添加子进程覆盖以支持状态、直接停止和直接重启 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5689) |
| `3385a486997e` / [#5587](https://github.com/OpenHands/software-agent-sdk/pull/5587) | `openhands-sdk/openhands/sdk/llm/utils/model_features.py`<br>`tests/sdk/llm/test_llm.py`<br>`tests/sdk/llm/test_model_features.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - 将 `claude-haiku-5-5` 添加到 `PROMPT_CACHE_MODELS`。 - 使用裸、Anthropic 和 LiteLLM 代理名称测试两个模型的回退方案识别和真实消息格式。 - 检查启用和禁用缓存的自动缓存标记。 公共 APIs 和缓存策略保持不变。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5587) |
| `e696f72c260b` / [#5659](https://github.com/OpenHands/software-agent-sdk/pull/5659) | `openhands-agent-server/openhands/agent_server/config.py`<br>`openhands-agent-server/openhands/agent_server/init_router.py`<br>`openhands-agent-server/openhands/agent_server/sockets.py`<br>`tests/agent_server/test_config.py`<br>+3 条路径（完整列表如下） | F01, F02, F03, F06, F07, F13, F29, F31, F32 | - `Config` 获取 `session_api_keys`  验证器这会丢空字符串，所以环境槽 env slots JSON 配置和显式构造在一处进行规范化。 `[""]` becomes `[]`, `[key, ""]` becomes `[key]`. 这符合旧版 `SESSION_API_KEY=""`, which `_default_session_api_keys` 已经处理为无键。- 两者都 WebSocket auth paths（遗留的查询/头部认证和第一帧认证）拒绝空呈现的密钥  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5659) |
| `e3a26821f8f7` / [#5657](https://github.com/OpenHands/software-agent-sdk/pull/5657) | `openhands-sdk/openhands/sdk/llm/utils/telemetry.py`<br>`openhands-sdk/openhands/sdk/utils/redact.py`<br>`tests/sdk/llm/test_llm_log_completions_integration.py`<br>`tests/sdk/utils/test_redact.py` | F04, F06, F07, F09, F19, F20, F22, F23, F30, F33, F34 | - `Telemetry.on_request` 复制日志 `extra_headers` 和 `headers` 在调用提供者之前，并将它们通过现有的 `sanitize_dict` helper (`openhands/sdk/utils/redact.py`），因此在调用过程中所做的在地更改无法到达日志凭据-like 标头被记录为 `<redacted>`. - 成功调用 (`log_llm_call`) 和失败的`on_error`) 从这个日志中记录上下文，和服务器的日志 e | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5657) |
| `acca181af1f3` / [#5621](https://github.com/OpenHands/software-agent-sdk/pull/5621) | `.agents/skills/verify-agent-server/SKILL.md`<br>`.agents/skills/verify-agent-server/references/adaptation.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F01-server-status.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md`<br>+42 条路径（完整列表如下） | 无需产品运行时间 | - `.agents/skills/verify-agent-server/` 下的贡献者技能：控件 CLI (`control-agent-server`)、可执行功能图（34 个系列，每个系列一个文件）和维护杠杆。 - **`control-agent-server`**从结帐启动隔离服务器（私有HOME、持久化、密钥、端口），使用断言驱动任何REST路由或WebSocket，安排测试夹具（git存储库、技能、插件、MCP服务器、Webhook | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5621) |
| `d97eb76f6082` / [#5724](https://github.com/OpenHands/software-agent-sdk/pull/5724) | `openhands-sdk/openhands/sdk/security/_shell_ast.py`<br>`openhands-sdk/openhands/sdk/security/defense_in_depth/pattern.py`<br>`openhands-sdk/openhands/sdk/security/defense_in_depth/policy_rails.py`<br>`openhands-sdk/openhands/sdk/security/defense_in_depth/shell_semantics.py`<br>+3 条路径（完整列表如下） | F08 | - 用共享的树-树Sitter Bash解析器解析每个原始可执行段。- 重用共享命令视图，用于命令词和指向自己的参数。- 解析引号包围的命令名称、路径、支持的包装器、描述流和字面嵌套或管道的shell源。- 返回 `UNKNOWN` 当相关管道输出、重定向、消费者或继承输入无法解决时。- 处理 `command -v/-V` 如上所述 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5724) |
| `7bd668c9ab74` / [#5660](https://github.com/OpenHands/software-agent-sdk/pull/5660) | `openhands-agent-server/openhands/agent_server/config.py`<br>`openhands-agent-server/openhands/agent_server/init_router.py`<br>`tests/agent_server/test_config.py`<br>`tests/agent_server/test_init_router.py` | F01, F02, F03, F29, F31, F32 | - A `field_validator` 在 `Config.secret_key` 将一个空白值（空值或仅包含空白字符）视为未设置，返回 `_default_secret_key()`, 相同的回退方案当变量不存在时使用。 第一个会话密钥在设置时使用； 否则就没有密码并记录现有警告。 这涵盖了环境变量， JSON 配置文件和直接 `Config(...)` 建设 `/api/init` applies `secret_k  | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5660)  |
| `c1dfd9c52cd3` / [#5520](https://github.com/OpenHands/software-agent-sdk/pull/5520) | `openhands-sdk/openhands/sdk/subagent/scope.py`<br>`openhands-sdk/openhands/sdk/tool/tool.py`<br>`openhands-tools/openhands/tools/task_tracker/definition.py`<br>`tests/tools/task/test_sub_agent_scope.py` | F27, F33 | - **新`ToolDefinition.conversation_local`类标志**（默认`False`）。 它标记了只读写其自身对话状态的工具。- **`SubAgentScope.missing_from` 忽略了本地对话工具。** 它是任务工具列表后的唯一检查，`TaskManager` 开始检查和两个工作流工具，因此它们一起改变。- **`TaskTrackerTool` 设置标志。- ** 其他工具是如此 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5520) |
| `d6165a51cb15` / [#5744](https://github.com/OpenHands/software-agent-sdk/pull/5744) | `openhands-sdk/openhands/sdk/profiles/seed.py`<br>`tests/sdk/profiles/test_resolver.py` | F21 | 将现有拒绝列表复制到种子配置文件中。 内联技能仍然不会成为积极的参考，未知的禁用名称仍然无害。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5744) |
| `4011cb5d4fd5` / [#5409](https://github.com/OpenHands/software-agent-sdk/pull/5409) | `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>`openhands-agent-server/openhands/agent_server/docker_runtime/routers.py`<br>`openhands-agent-server/openhands/agent_server/launch.py`<br>+16 条路径（完整列表如下） | F01, F04, F05, F06, F07, F10, F12, F16, F18, F19, F20, F21, F22, F27, F29, F30, F31, F32, F33, F34 | - `StartConversationRequest.agent_profile` 启动未保存的配置文件。 它的解析与存储的一模一样，从未保存，并记录为`launched_agent_profile.inline`。 它与其他智能体来源是相互排斥的。 - `AgentLaunchAdditions.llm_profile_ref` 使用另一个 LLM 配置文件启动 OpenHands 配置文件，而不修改该配置文件。 其记载于`launched_agent_profile.llm_profile_ref`。 I | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5409) |
| `27308a4b3f23` / [#4960](https://github.com/OpenHands/software-agent-sdk/pull/4960) | `openhands-sdk/openhands/sdk/conversation/request.py`<br>`openhands-sdk/openhands/sdk/launch/finalize.py`<br>`tests/agent_server/docker_runtime/test_mediation.py`<br>`tests/agent_server/test_agent_launch_additions.py` | F04, F06, F21, F30, F33, F34 | - `AgentLaunchAdditions.skills: list[Skill] \| None` — 部署提供的技能，在已经进行部署上下文的通道上，在 `system_message_suffix_append` 之后的 `finalize` 中应用。 - `finalize` 通过两个规则将它们按名称合并，以防止其成为后门： - ** 已解决的智能体赢得冲突 ** - 它的技能来自配置文件和服务器自己的来源，越权威 v | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-4960) |
| `733f06edac35` / [#5727](https://github.com/OpenHands/software-agent-sdk/pull/5727) | `.agents/skills/verify-agent-server/SKILL.md`<br>`.agents/skills/verify-agent-server/references/adaptation.md`<br>`.agents/skills/verify-agent-server/references/daily.md`<br>`.agents/skills/verify-agent-server/references/feature-map/README.md`<br>+3 条路径（完整列表如下） | 无需产品运行时间 | - 新的 `references/daily.md`，链接自 `SKILL.md`、`maintenance.md` 和 `adaptation.md`。 - `map baseline [--set]`读取或移动基线； `map check` 会验证它，现在使用 `main@<sha> (<date>)`。- 无参数调用 `map owners` 会与基线比较，并列出功能族。- `evidence report --baseline` 列出新增失败、新增通过、未检查和存在冲突的行。 账本通过尝试 ti 进行比较 | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5727) |
| `dfd8fe8fb39e` / [#5728](https://github.com/OpenHands/software-agent-sdk/pull/5728) | `.agents/skills/verify-agent-server/SKILL.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F03-deferred-init.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`<br>+34路径（完整列表如下） | 无需产品运行时间 | - **标记合约。**现在，每个标记都命名了 bug 自己的症状：`# bug: PREDICATE`，由 `PATH OP [VALUE]` 子句和 `&&` 连接组成。 它们像 `--check` 一样与该行上最后一个 `control-agent-server` 调用打印的 JSON 进行匹配。 `exit N` 仅作为最后手段保留。 这里 `F08.secrets-bad-value` 之前和之后：```sh # 之前控制-智能体-服务器 API POST "/api/conversations/$KID/secrets" | 文档化 | 无需产品运行环境] [特征证据和限制](intent-runtime-overlay.md#pr-5728) |
| `a430c778bd8a` / [#5754](https://github.com/OpenHands/software-agent-sdk/pull/5754) | `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`<br>`openhands-sdk/openhands/sdk/subagent/AGENTS.md`<br>`openhands-sdk/openhands/sdk/subagent/registry.py`<br>`tests/sdk/subagent/test_subagent_registry.py` | F27 | - `register_file_agents` 和 `register_plugin_agents` 现在通过一个辅助工具 `_register_definition` 来注册每个定义，该工具捕获 `ValueError` 从 `agent_definition_to_factory`，记录 `Skipping <file-based\|plugin> agent '<name>' from <source>: <error>`，跳过该定义并继续注册其他定义。 有效技能分辨率不变。 - `openhands-sdk/openhands/sdk/subagent/AGENTS.md` 州 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5754) |
| `6a298a48fcdb` / [#5759](https://github.com/OpenHands/software-agent-sdk/pull/5759) | `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`<br>`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` | F28 | - `status()` 现在也重新探查一个正在运行的进程 `unhealthy` 只有因为探针失败（不是那种退出或未能启动的探针），才设置了 `ready` 当探针成功时 `start()` 在同一个版本的生产过程中返回刷新的状态，而不是缓存的状态单元测试有实际的后端子进程 （慢探针，仍然慢，恢复，然后又通过） `start`); the `F28.status-probe-lat | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5759)  |
| `6e7a8532ef44` / [#4814](https://github.com/OpenHands/software-agent-sdk/pull/4814) | `examples/01_standalone_sdk/48_conversation_fork.py`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>`openhands-sdk/openhands/sdk/conversation/base.py`<br>`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`<br>+3 条路径（完整列表如下） | F04, F05, F08, F09, F10, F12, F31, F32, F33 | - 保留 `title` 关键字以实现兼容性，但将弃用保留在本地，并停止添加或覆盖标签。 `LocalConversation` 不存储标题。 - 保留智能体-server 和 `RemoteConversation` 标题到 `StoredConversation.title`，并在省略标签时保持分叉元数据标签与状态一致。 - 合并当前 `main` (`c0471362d340ade1e334595ba98417108b415e88`)，保留其并发-fork 生命周期 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-4814) |
| `c3ecd82c7807` / [#5478](https://github.com/OpenHands/software-agent-sdk/pull/5478) | `openhands-sdk/openhands/sdk/llm/utils/verified_models.py`<br>`tests/sdk/llm/test_model_list.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - 将 `gpt-6.1-sol` 添加到 `VERIFIED_OPENAI_MODELS`、`VERIFIED_OPENROUTER_MODELS` (`openai/gpt-6.1-sol`) 和 `VERIFIED_OPENHANDS_MODELS`。 - 将`claude-sonnet-5-5`添加到`VERIFIED_ANTHROPIC_MODELS`、`VERIFIED_OPENROUTER_MODELS`（`anthropic/claude-sonnet-5.5`）和`VERIFIED_OPENHANDS_MODELS`。 - 将`gemini-4-argon`添加到`VERIFIED_GEMINI_MODELS`和`VERIFIED_OPENROUTER_MODELS`（`google/gemini-4-argon`）； 未在 th 下浮出水面 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5478) |
| `7f7f05209200` / [#4926](https://github.com/OpenHands/software-agent-sdk/pull/4926) | `AGENTS.md`<br>`clients/typescript/src/models/acp.ts`<br>`openhands-sdk/openhands/sdk/settings/acp_providers.py` | F04, F09, F18, F19, F20, F21, F22, F23, F30, F33, F34 | 澄清以下  Python 和 TypeScript  注册表他们携带元数据，而不是部署策略。 - 详细说明单向 `SURFACED_ACP_PROVIDERS ⊆ ACP_PROVIDERS`  不变量并拒绝互补的隐藏提供商列表。- 记录交叉引用合同 `AGENTS.md`; 修改 #4841 和 #4833 以匹配最新的更正。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-4926) |
| `d332f8156f12` / [#5981](https://github.com/OpenHands/software-agent-sdk/pull/5981) | `openhands-agent-server/openhands/agent_server/launch.py`<br>`openhands-agent-server/openhands/agent_server/server_details_router.py`<br>`openhands-agent-server/openhands/agent_server/skills_service.py`<br>`openhands-sdk/openhands/sdk/launch/preview.py`<br>+13 条路径（完整列表如下） | F01, F04, F21, F25, F27, F29, F30, F33, F34 | - `OpenHandsAgentProfile.public_skills`: `null` 保留所有公共目录技能，就像今天一样； `[]`保留None； 列表仅保留这些名称，未知名称将被忽略。 用户和项目技能不受影响，并且 `disabled_skills` 仍然适用于一切。 - `LaunchStores.public_skill_names` 告诉解析器哪些目录技能是公共的。 智能体-服务器从与目录相同的加载器中派生它，因此 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5981) |
| `0bd5cc2d322d` / [#5747](https://github.com/OpenHands/software-agent-sdk/pull/5747) | `openhands-agent-server/openhands/agent_server/sub_agents_router.py`<br>`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`<br>`openhands-sdk/openhands/sdk/profiles/resolver.py`<br>`openhands-sdk/openhands/sdk/subagent/AGENTS.md`<br>+10路径（完整列表如下） | F05, F08, F09, F10, F21, F27, F33 | - **`inherit_mcp_config(parent, sub_agent)`** (`openhands.sdk.subagent.scope`) 返回构建的子智能体与 `parent.agent.mcp_config` 完全相同。 这是代理对话的*已解决*配置：插件服务器已经合并，`${VAR}` 机密已经展开，工具过滤器和头保持不变。 声明的子服务器被丢弃，从不合并，并且 INFO 记录了它们（只命名，不配置）。TaskManage | | 家族扫描，包含已知缺陷。 [特征证据和限制](intent-runtime-overlay.md#pr-5747) |
| `4bb57df68465` / [#5926](https://github.com/OpenHands/software-agent-sdk/pull/5926) | `.agents/skills/verify-agent-server/references/feature-map/F24-openai-subscription.md`<br>`openhands-agent-server/openhands/agent_server/llm_router.py`<br>`tests/agent_server/test_llm_router.py` | F23, F24 | - `get_openai_subscription_status` 现在在 `refresh_if_needed()` 周围捕获 `httpx.HTTPError` 和 `RuntimeError`，因此无法访问的 OpenAI 读取为 `200 connected: false`，就像拒绝的刷新一样。 凭据文件未受影响，因此一旦网络恢复，状态就会刷新。 - `tests/agent_server/test_llm_router.py` 中的单元测试用于提升 `httpx.ConnectError` 的刷新。 - 地图：“F24.status-离线 | 记录的 | 系列具有能力限制的扫描”； [特征证据和限制](intent-runtime-overlay.md#pr-5926) |
| `1a0fd91ad03d` / [#5923](https://github.com/OpenHands/software-agent-sdk/pull/5923) | `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`<br>`openhands-agent-server/openhands/agent_server/canvas_extensions_bridge_router.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_bridge_routes.py` | F29 | - `canvas_extensions_bridge_router.py`：根 HTTP 和 WebSocket 路由有自己的处理程序，不带 `path` 参数并始终代理到 `/`； 子路径处理程序现在需要 `path`（始终从 URL 绑定）。 `bridge.py` 未受影响。 - 新的重点测试 `tests/agent_server/canvas_extensions/test_canvas_extension_bridge_routes.py` 检查每个路由形式通过哪个上游路径到达网桥，对于 HTTP ( | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5923) |
| `1c34a84ccea3` / [#5920](https://github.com/OpenHands/software-agent-sdk/pull/5920) | `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`<br>`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`<br>`openhands-agent-server/openhands/agent_server/canvas_extensions/bridge.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`<br>+1 条路径（完整列表如下） | F28, F29 | - `CanvasExtensionBackendManager.ready_endpoint` 仅在后端进程退出后返回 `None`，因此 HTTP 代理、WebSocket 代理桥和 `proxy_app_backend_http` 驱动程序在没有状态轮询的情况下会回答 503 不可用。- `502 Canvas App backend unreachable` 将连接失败重命名为 F29。- `F29.backend-crash-detected` 表：`# bug` 标记被丢弃。 它的散文和陷阱线现在描述了固定的行为 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5920) |
| `2ec5b9ed4a67` / [#5944](https://github.com/OpenHands/software-agent-sdk/pull/5944) | `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`<br>`openhands-agent-server/openhands/agent_server/skills_service.py`<br>`openhands-sdk/openhands/sdk/git/cached_repo.py`<br>`openhands-sdk/openhands/sdk/skills/utils.py`<br>+2 条路径（完整列表如下） | F15, F25 | - 添加选项开关 `strict` flag to `try_cached_clone_or_update` (threaded through `_update_repository`) 和 `update_skills_repository`当设置为失败的 fetch，或在请求的 ref 之后失败的 checkout 时，返回 `None` 而不是陈旧的路径。 默认（`strict=False`) 为每个其他调用者保留回退到缓存的行为 `sync_public_skills` uses `strict=True`因此路由器报告了状态： | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5944)  |
| `9c0b99ec0077` / [#5725](https://github.com/OpenHands/software-agent-sdk/pull/5725) | `.github/workflows/pip-revendoring-retirement.yml`<br>`openhands-agent-server/openhands/agent_server/docker/Dockerfile`<br>`tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py` | F01, F12, F16, F31 | - 添加 `pip-revendored` 构建阶段。 它获取 pip 26.2.1 的标记源（使用 `ADD --checksum` 检查），将 `vendor.txt` 切换到 urllib3 2.8.0 和 msgpack 1.2.1，并运行 pip 自己的 `vendoring sync`。 这将应用 pip 的导入重写及其 `tools/vendoring/patches`（包括三个 urllib3 补丁）并重新生成 `bom.cdx.json`。 然后阶段会构建一个 pip 轮。 使用 GitHub 源存档是因为 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5725) |
| `95cb37b7f04f` / [#5986](https://github.com/OpenHands/software-agent-sdk/pull/5986) | `openhands-sdk/openhands/sdk/git/utils.py`<br>`tests/sdk/extensions/test_fetch.py` | F14, F15 | - `normalize_git_url` 不保留 DevOps 副本 URLs (任何包含 `/_git/`: dev.azure.com, `*.visualstudio.com`, Azure DevOps 服务器) 的 `.git` 后缀。 它仍然会删除尾部斜杠。 其他主机不变。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5986) |
| `4dc42d3a2b65` / [#5929](https://github.com/OpenHands/software-agent-sdk/pull/5929) | `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`<br>`openhands-agent-server/openhands/agent_server/__main__.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_bridge.py`<br>`tests/agent_server/test_preload_modules.py` | F02, F27 | - `__main__.py`：通过一个小的 `_load_server_config()` 帮助器（与 `_auth_enabled` 共享）解析智能体-服务器配置一次，并将 `proxy_headers=_trust_forwarded_headers()` 传递给 uvicorn 的 `Config`。 桥接代理代码没有更改。 - 测试：`test_preload_modules.py` 检查每个标志设置的 `proxy_headers` 值 `main()` 是否通过； `canvas_extensions/test_canvas_extension_bridge.py` 运行桥梁  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5929) |
| `98c97e6f18ce` / [#5909](https://github.com/OpenHands/software-agent-sdk/pull/5909) | `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md`<br>`openhands-agent-server/openhands/agent_server/plugins_router.py`<br>`openhands-agent-server/openhands/agent_server/skills_router.py`<br>+3 条路径（完整列表如下） | F25, F26, F28 | - `openhands.sdk.extensions.fetch`：GitHub 简写在 `owner/repo` 之后采用可选路径，`fetch_with_resolution` 使用该路径作为 `repo_path`。 现有的包含检查仍然适用，因此`github:o/r/../..`被拒绝。- 安装源描述：技能描述删除了树URL示例，显示了一个gitURL，而不是`repo_path`。 现在两种描述都说速记可以命名为拍拍 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5909) |
| `d60b176ce32b` / [#5945](https://github.com/OpenHands/software-agent-sdk/pull/5945) | `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`<br>`openhands-agent-server/openhands/agent_server/api.py`<br>`tests/agent_server/test_api.py` | F01, F03, F05, F30, F31, F32 | - 关闭时，`api_lifespan` 会删除每个服务器的 tmux 目录，但仅限于此进程创建的目录。 尽最大努力进行删除：将故障记录为警告并继续关闭。 用户提供的 `TMUX_TMPDIR` 或已存在的默认目录永远不会被删除。 环境恢复不变。 - 测试：生命周期测试断言退出后该目录已消失。 新测试涵盖以下情况： - 用户 - | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5945) |
| `1045bdffdb8d` / [#5918](https://github.com/OpenHands/software-agent-sdk/pull/5918) | `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`<br>`openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py`<br>`tests/agent_server/docker_runtime/test_proxy.py` | F12, F29 | - `proxy_http` (`docker_runtime/proxy.py`）客户端发送了任何内容时，现在发送了空体 `Content-Length` nor `Transfer-Encoding`重新添加客户端的 `Content-Length` while still 流式传输 body (httpx then does not chunk)，并保持 chunked 客户端 body chunked。 A `body=` 替换为字节，因此 httpx 设置了它的 `Content-Length`- 新参数化单元测试 in `tests/agent_server/docker_runtime/test  | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5918)  |
| `4e32a3adb052` / [#5907](https://github.com/OpenHands/software-agent-sdk/pull/5907) | `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md`<br>`openhands-agent-server/openhands/agent_server/vscode_service.py`<br>`tests/agent_server/test_vscode_service.py` | F16 | - `VSCodeService.get_vscode_url` 返回 `None` 除非服务器运行。 `get_vscode_service()` 播种了 token 从 `session_api_keys[0]` 之前 `start()` 运行，所以  token 独自并不意味着服务器就在那里 `start()` 也铸造了 token 在端口检查之前单元测试不运行的案例， 与之间有  token, and a failed `start()` (端口被占用) 无路可走 URL; 现有的 URL-shape 测试现在标记为 se | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5907) |
| `f67cba804501` / [#5787](https://github.com/OpenHands/software-agent-sdk/pull/5787) | `.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md`<br>`openhands-agent-server/openhands/agent_server/auth_router.py`<br>`tests/agent_server/test_workspace_cookie_auth.py` | F02 | - `_request_is_secure_context` 仅从括号中的主机或具有一个冒号的主机去掉 `:port` 后缀，因此裸 IPv6 主机名保持完整。- 测试：`Host: [::1]` 和 `Host: [::1]:8000` 生成 `Secure; Partitioned`。 带括号的 `X-Forwarded-Host: [::1]:8000` 继续工作。 - 地图：`F02.workspace-session-ipv6-loopback` 失去了 `# bug` 标记和“已知错误”标签； 它的散文现在陈述了预期的 b | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5787) |
| `91b89bdc6f33` / [#5774](https://github.com/OpenHands/software-agent-sdk/pull/5774) | `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`<br>`openhands-agent-server/openhands/agent_server/api.py`<br>`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` | F01, F03, F05, F28, F30, F31, F32 | - `CanvasExtensionBackendManager` 现在为每个启动的后端写一个小记录 `backends/run/<pgid>.json`进程组，领导者的启动时间（`/proc/<pid>/stat`), 和服务器自己的进程 ID 和启动时间。 `_terminate_runtime` 停止分组后删除记录。- 新 `reap_orphans()`, called from the API 在路由被服务之前的生命期。 对于服务器不再运行的每个记录，  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5774) |
| `dc897208faae` / [#5891](https://github.com/OpenHands/software-agent-sdk/pull/5891) | `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`<br>`openhands-sdk/openhands/sdk/git/git_diff.py`<br>`openhands-sdk/openhands/sdk/git/utils.py`<br>`tests/sdk/git/test_git_diff.py` | F14, F15 | - `run_git_command` 获得关键字参数 `strip: bool = True`. 所有现有的呼叫者都保留了脱敏输出 `get_git_diff` 读取 `git show` blob with `strip=False` 并且按照它已经对修改后的部分进行的那样进行规范化，因此，未修改的文件具有相同的边。 CRLF 文件行为不变。- Map: the `F15.diff-whitespace` 子弹丢弃了 `# bug` 标记为“marker”和“known bug”标签，以及注释和Gotchas  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5891) |
| `923ff2de5fd6` / [#5903](https://github.com/OpenHands/software-agent-sdk/pull/5903) | `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`<br>`openhands-agent-server/openhands/agent_server/skills_service.py`<br>`tests/agent_server/test_skills_service.py` | F25 | - `sync_public_skills` 成功时清除市场目录缓存（新的 `_invalidate_catalog_cache` 帮助程序）； 失败的同步保留了它。 - `service_get_marketplace_catalog` 仅缓存非空结果，与 `plugins_service` 已使用的规则相同。 - 单元测试对于两者； `F25.marketplace-stale-cache` 地图项目符号失去了其已知错误标记，其散文和陷阱行现在描述了固定行为。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5903) |
| `7bb4be18ca42` / [#5905](https://github.com/OpenHands/software-agent-sdk/pull/5905) | `.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md`<br>`openhands-sdk/openhands/sdk/extensions/installation/manager.py`<br>`tests/sdk/plugin/test_installed_plugins.py` | F25, F26, F28 | - `InstallationManager.install` 现在加载了一个未从远程源获取的远程源 `repo_path` 从一个临时副本（没有 ） `.git`) 以仓库命名的`extract_repo_name`, 该助手命名缓存目录)，因此一个从目录中推断名称的加载器会看到 `<repo>`对于本地目录。 本地源和 `repo_path` 如之前一样，安装在位。 安装的文件仍然是从 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5905) |
| `4804aa0be06f` / [#5921](https://github.com/OpenHands/software-agent-sdk/pull/5921) | `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`<br>`openhands-agent-server/openhands/agent_server/sub_agents_router.py`<br>`tests/agent_server/test_sub_agents_router.py` | F27 | - `get_sub_agents` 通过 `enable_browser=configured_browser_available(config) is not False` 到 `discover_builtin_agents`。 该函数已经过滤了`web-researcher`； 只是从来没有被告知这样做。 - `tests/agent_server/test_sub_agents_router.py` 中的单元测试（在 `enable_browser` 上参数化）。 - 地图：`F27.subagents-browser-disabled` 现在会以 `enable_browser: false` 本身重新启动。 之前，它依赖于较早的bu | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5921) |
| `75105bd40936` / [#5931](https://github.com/OpenHands/software-agent-sdk/pull/5931) | `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`<br>`openhands-agent-server/openhands/agent_server/file_router.py`<br>`tests/agent_server/test_file_router.py`<br>`tests/agent_server/test_runtime_router.py` | F14 | - `_upload_file` 现在将 `IsADirectoryError` 映射到 400 `Path is a directory`，将 `FileExistsError` / `NotADirectoryError`（当父级是文件时 `mkdir(parents=True)` 引发）映射到 400 `A parent of the path is not a directory`。 其他所有失败仍返回 500。 对话范围的路由 `POST /api/conversations/{id}/file/upload` 安装相同的处理程序。 - 测试：对全球航线公司进行参数化测试 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5931) |
| `8efff8d3cf1a` / [#5924](https://github.com/OpenHands/software-agent-sdk/pull/5924) | `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`<br>`openhands-agent-server/openhands/agent_server/server_details_router.py`<br>`tests/agent_server/test_server_details_router.py` | F01, F29 | - `build_server_info` 采用 `browser_available` 且 `get_server_info` 通过 `configured_browser_available(config)`，与目录路由应用相同的决策； `None`（本地运行时，启用浏览器）保留 Chromium 探针。 - 单元测试为 `enable_browser=False` 路线，`build_server_info` 为 `None`/`True`/`False`. - 地图：`F27.server-info-browser-disabled` 删除其 `# bug` 标记，声明“Req | 记录了具有已知缺陷的 | 系列扫描”； 证据和限制[ ](intent-runtime-overlay.md#pr-5924) |
| `818c161b5344` / [#5983](https://github.com/OpenHands/software-agent-sdk/pull/5983) | `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>`openhands-agent-server/openhands/agent_server/docker_runtime/routers.py`<br>`openhands-agent-server/openhands/agent_server/launch.py`<br>+11 条路径（完整列表如下） | F04, F05, F06, F10, F12, F16, F18, F19, F20, F21, F22, F27, F30, F31, F32, F33, F34 | - **内联启动源已删除。** `StartConversationRequest.agent_profile` 和 `LaunchedAgentProfile.inline` 以及它们在启动时的处理、Docker 转发和存储的请求都消失了。 唯一智能体来源为 `agent_profile` 的请求现在会失败验证，并显示“必须提供 `agent`、`agent_settings` 或 `agent_profile_id` 之一”。 在另一个来源旁边，`agent_profile` 像任何 u 一样被忽略 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5983) |
| `f0206428306d` / [#5589](https://github.com/OpenHands/software-agent-sdk/pull/5589) | `openhands-agent-server/openhands/agent_server/api.py`<br>`openhands-tools/openhands/tools/terminal/constants.py`<br>`openhands-tools/openhands/tools/terminal/terminal/tmux_pane_pool.py`<br>`openhands-tools/openhands/tools/terminal/terminal/tmux_terminal.py`<br>+3 条路径（完整列表如下） | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34 | 记录每个套接字所有者的创建过程 tmux 用户选项 (`@openhands_socket_owner_pid`) from `TmuxTerminal` / `TmuxPanePool` 初始化 `_cleanup_stale_tmux_sessions()` 现在重新占有了一个 `openhands-<32 hex>` 仅在记录的拥有者进程消失时才使用 socket `_is_pid_alive` 从 `conversation_lease`). [legacy] `openhands` socket 仍然总是被回收，且没有回收的 socket | 有记录的 | 具有能力限制的家庭扫荡； [特征证据和限制](intent-runtime-overlay.md#pr-5589) |
| `11d82b2c267a` / [#6003](https://github.com/OpenHands/software-agent-sdk/pull/6003) | `openhands-tools/openhands/tools/task_tracker/definition.py`<br>`tests/tools/task_tracker/__init__.py`<br>`tests/tools/task_tracker/test_task_tracker_status.py` | F27, F33 | - 任务状态在验证之前标准化：忽略大小写、空格和连字符，`pending` 和 `to do` 表示 `todo`，`completed` 和 `complete` 表示 `done`。 - 其他值，例如 `blocked` 或 `cancelled`，仍然被拒绝并出现相同的错误。 - 模型显示的模式和保存的任务列表仍然仅使用 `todo`、`in_progress` 和 `done`。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-6003) |
| `8ad5845e46fc` / [#5990](https://github.com/OpenHands/software-agent-sdk/pull/5990) | `openhands-sdk/openhands/sdk/plugin/format/agent_plugins.py`<br>`tests/sdk/plugin/test_agent_plugins_format.py` | F09, F26 | - 仅当根 `plugin.json` 声明 `$schema` 时，或者当它不可读或不是 JSON 对象时，才会选择智能体插件格式。 一个未修复或不支持的智能体插件标志仍然被声称和拒绝，因此它永远不会在目录名下被默默加载。-一个没有`$schema`的根`plugin.json`会通过Claude代码布局加载插件的`skills/`目录。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5990) |
| `b187e88eb018` / [#5984](https://github.com/OpenHands/software-agent-sdk/pull/5984) | `openhands-sdk/openhands/sdk/profiles/resolver.py` | F21 | - 两个功能都是`@deprecated(deprecated_in="1.55.0", removed_in="1.60.0")`。 这就是 5 短跑道 `check_deprecations.py` 所需要的。 - 每个弃用指定其替代者：`openhands.sdk.launch.resolve` 代表第一个，`openhands.sdk.launch.preview_launch` 代表试运行。 - 没有行为改变。 模块文档字符串现在说明了该模块的用途并指出了替换项。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5984) |
| `fd387b58dc7b` / [#6007](https://github.com/OpenHands/software-agent-sdk/pull/6007) | `clients/typescript/package-lock.json`<br>`clients/typescript/package.json`<br>`clients/typescript/src/generated/agent-server-schema.ts`<br>`openhands-agent-server/pyproject.toml`<br>+4路径（完整列表如下） | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34 | ## 版本 1.55.0 这个 PR 准备了版本 **1.55.0 **。 **Started by:** @simonrosenberg ### 发布清单 - [x] 版本设置为 1.55.0 - [ ] 修复任何弃用截止日期（如果存在） - [ ] 集成测试通过（标记为`integration-test`) - [ ] 行为测试通过（标记为 `behavior-test`） - [ ] 示例测试通过（标记为 `test-examples`） - [ ] 安全扫描通过（标记为 `se | 记录的 |具有能力限制的家庭扫荡； [特征证据和限制](intent-runtime-overlay.md#pr-6007) |
| `f5f849f5ab51` / [#5991](https://github.com/OpenHands/software-agent-sdk/pull/5991) | `openhands-agent-server/openhands/agent_server/docker/Dockerfile`<br>`tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py` | F01, F12, F16, F31 | - `pip-revendored`阶段从pip的`vendor.txt`中删除`setuptools==70.3.0`，并在`vendoring sync`之前删除pip的`pkg_resources.patch`。 重建的 pip 及其 `bom.cdx.json` 不包含 setuptools。 - 退休守卫还检查上游 pip 是否仍然捆绑 `pkg_resources`。 它要求仅在上游修复了 urllib3 和 msgpack 后才删除该阶段。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5991) |
| `d5995133d942` / [#5753](https://github.com/OpenHands/software-agent-sdk/pull/5753) | `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`<br>`openhands-sdk/openhands/sdk/git/git_changes.py`<br>`tests/agent_server/test_git_router.py`<br>`tests/sdk/git/test_git_changes.py` | F15 | `get_git_changes` (`openhands-sdk/openhands/sdk/git/git_changes.py`): 当请求的目录不是仓库，而是位于其下方一级的仓库时，从不基础更改开始列出它们（按路径排序，如之前）。 如果该目录及其下面的任何目录都不是有效的存储库，则仍会引发原始 `GitRepositoryError`，因此 Agent Server 仍然  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5753) |
| `cb266703c5c7` / [#5696](https://github.com/OpenHands/software-agent-sdk/pull/5696) | `openhands-agent-server/openhands/agent_server/file_router.py`<br>`tests/agent_server/test_file_router.py` | F14 | - `download_trajectory` 现在解析来自 `request.app.state.config` 的对话目录，`dependencies.py`、`tool_router.py` 和 `server_details_router.py` 已使用请求时配置模式。 - 现有的轨迹测试安装请求时配置，而不是修补模块级查找。 - 回归测试端到端地驱动真正的延迟初始化应用程序：使用 `deferred_init=True` 启动，`| 记录了具有已知缺陷的 | 系列扫描； [ 特征证据和限制](intent-runtime-overlay.md#pr-5696) |
| `db9c54b71c8c` / [#5987](https://github.com/OpenHands/software-agent-sdk/pull/5987) | `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`<br>`openhands-agent-server/openhands/agent_server/plugins_router.py`<br>`openhands-agent-server/openhands/agent_server/plugins_service.py`<br>`openhands-sdk/openhands/sdk/plugin/__init__.py`<br>+8 条路径（完整列表如下） | F09, F21, F26, F30 | - 将 `preflight_plugin(...)`、`PluginSourceError` 和 `CheckedPlugin` 添加到 `openhands.sdk.plugin`，并具有严格的机密扩展、结构化错误代码、临时结帐清理和原始清单/技能/命令元数据。 - 通过现有的 `/plugins` 路由器添加了 `POST /api/plugins/fetch`，以获取插件并将其固定到不可变的 commit-SHA 缓存路径中，而无需安装或启用它。 - 添加了固定缓存重用 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5987) |
| `5fa4dea24c52` / [#6021](https://github.com/OpenHands/software-agent-sdk/pull/6021) | `clients/typescript/package-lock.json`<br>`clients/typescript/package.json`<br>`clients/typescript/src/generated/agent-server-schema.ts`<br>`openhands-agent-server/pyproject.toml`<br>+4路径（完整列表如下） | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34 | ## 版本 1.55.1 这个 PR 准备了版本 **1.55.1** 的发布。 **Started by:** @malhotra5 ### 发布清单 - [x] 版本设置为 1.55.1 - [ ] 修复任何弃用截止日期（如果存在） - [ ] 集成测试通过（标记为`integration-test`) - [ ] 行为测试通过（标记为 `behavior-test`） - [ ] 示例测试通过（标记为 `test-examples`） - [ ] 安全扫描通过（标记为“安全 | 记录” |系列具有能力限制的扫描； [特征证据和限制](intent-runtime-overlay.md#pr-6021) |
| `12e967664c23` / [#5998](https://github.com/OpenHands/software-agent-sdk/pull/5998) | `.agents/skills/pr-design-doc/SKILL.md`<br>`.agents/skills/pr-design-doc/references/html-craft.md`<br>`.github/PULL_REQUEST_TEMPLATE.md`<br>`.github/workflows/pr-artifacts.yml`<br>+3 条路径（完整列表如下） | 无需产品运行时间 | - 删除审批清理，合并后使用现有的清理 PR，以移除 `.pr/` 从 `main` 的同一仓库和分支 PR。- 更新 artifact notice、贡献者指南、 PR 模板和设计文档指导，描述合并后自动移除 `main`。- 只对 `rel-` 版本 PR 的已提交树包含根 `.pr` 元素的现有预提交作业失败。 | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-5998) |
| `6530325e9dd0` / [#6009](https://github.com/OpenHands/software-agent-sdk/pull/6009) | `openhands-sdk/openhands/sdk/marketplace/registry.py`<br>`openhands-sdk/openhands/sdk/marketplace/types.py`<br>`tests/agent_server/test_skills_service.py`<br>`tests/sdk/conversation/test_local_conversation_plugins.py`<br>+1 条路径（完整列表如下） | F09, F25, F26 | - 当注册的源没有市场应用元数据时， 注册表读作一个普通的技能文件夹，新版本 `Marketplace.from_skills_dir`. 每个 `<name>/SKILL.md` 文件夹在 `skills/` 和 `.skills/` 成为独立的技能。 如果两个文件夹都不存在，就使用源路径直接存在的技能文件夹 `repo_path` 它可以指向技能文件夹本身 Markdown 文件从不被读取，所以仓库无法使用 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-6009) |
| `4a5f5a09096a` / [#5955](https://github.com/OpenHands/software-agent-sdk/pull/5955) | `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md`<br>`openhands-agent-server/openhands/agent_server/event_service.py`<br>`openhands-agent-server/openhands/agent_server/openai/service.py`<br>`tests/agent_server/test_run_admission.py` | F05, F06, F07, F08, F09, F10, F11, F12, F30, F31 | - `EventService.reserve_run_slot()` 会提前声称运行容量（或在对话已经持有自己的运行许可或仍有运行任务在处理时，返回 `None`，因此运行中的对话不会被拒绝）。 `send_message` 采用可选的 `run_slot` 并将其传递给 `run()`。 - `_run_agent`（网关）在`send_message`之前保留并在之后释放其句柄。 - 地图：`F30.chat-reuse-run-li | 记录了具有已知缺陷的 | 系列清理； [特征证据和限制](intent-runtime-overlay.md#pr-5955) |
| `304ea67a7993` / [#5842](https://github.com/OpenHands/software-agent-sdk/pull/5842) | `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`<br>`openhands-agent-server/openhands/agent_server/bash_service.py`<br>`tests/agent_server/test_bash_service.py` | F13 | - `_search_bash_events_sync` (`bash_service.py`) 现在过滤掉事件，同时填充页面 `limit` 只计算返回的事件。 `next_page_id` 命名下一个通过过滤器的事件，因此页面永远不会跟随一个空页面。- 两单元测试：`order__gt` 在两个页面之间分页，且没有游标。- The `F13.order-gt-paging` 子弹不再携带 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5842) |
| `60c6f62133e0` / [#5780](https://github.com/OpenHands/software-agent-sdk/pull/5780) | `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md`<br>`openhands-agent-server/openhands/agent_server/event_service.py`<br>`tests/agent_server/test_event_service.py` | F05, F06, F07, F08, F09, F10, F11, F12, F31 | - `event_service.py`记录运行失败的情况 ERROR 在消息中，而不是通过 ，使用纯文本的堆栈跟踪 `exc_info`因此，循环中没有处理器渲染丰富的堆栈跟踪。- 测试：有一个新的单元测试检查记录是否  ERROR, 没有 `exc_info` 它承载整个链条。 现有的日志测试已更新。 `F05.run-error-responsive` 丢失了已知错误标记。 现在描述子弹散文和陷阱行 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5780) |
| `a6c7bf5591f6` / [#5779](https://github.com/OpenHands/software-agent-sdk/pull/5779) | `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`<br>`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`<br>`tests/agent_server/test_switch_llm_survives_reload.py`<br>`tests/sdk/conversation/test_switch_model.py` | F05, F08, F09, F10 | - `LocalConversation.switch_llm` 仅在配置 (`model_dump(mode="json")` 机密显示) 等于发布的配置 (LLM 注册) 时才重用。 否则，它会用上一个注册表条目替换上一个LLM，并将已经记录在`usage_id`下的`stats.usage_to_metrics[usage_id]`的计费对象。 `switch_profile`、`classify_and_switch_llm`的“|详细记录了|的家庭缺陷扫除”重连。 [特征证据和限制](intent-runtime-overlay.md#pr-5779) |
| `8ba8ccbeb1a5` / [#5772](https://github.com/OpenHands/software-agent-sdk/pull/5772) | `.agents/skills/verify-agent-server/references/feature-map/F11-goals.md`<br>`openhands-agent-server/openhands/agent_server/event_service.py`<br>`tests/agent_server/test_goal_loop.py` | F05, F06, F07, F08, F09, F10, F11, F12, F31 | - `EventService.start()` 现在在现有的过时的 `RUNNING` 执行状态协调旁边协调一个过时的目标状态：如果最后一个已持久化 `goal` 状态仍然是 `active`，它会附加一个具有相同 `objective`、`iteration` 和 `max_iterations` 的 `active: false, status: "interrupted"` 状态（判决已清除，就像所有其他 `interrupted` 状态一样）。 它是由加载状态驱动的，因此它涵盖了优雅的恢复 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5772) |
| `c87fddb623f0` / [#5769](https://github.com/OpenHands/software-agent-sdk/pull/5769) | `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`<br>`clients/typescript/README.md`<br>`clients/typescript/src/__tests__/package-import.test.ts`<br>`clients/typescript/src/__tests__/websocket-callback-client.test.ts`<br>+3 条路径（完整列表如下） | F13, F34 | - 新内部助手 `src/events/global-websocket.ts`它返回 `globalThis.WebSocket` 当被调用并持有共享错误消息。 现在，两个客户端在连接时都会调用它。 所有模块加载检测和 `require('ws')` 代码已删除，构建过程已结束 `dist/` 没有 `require` 或 `ws` import. - Tests: the 回调客户端测试桩 `globalThis.WebSocket` 而不是一个假的 `window`. 新测试涵盖了构造函数 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5769) |
| `76055f697a5e` / [#5768](https://github.com/OpenHands/software-agent-sdk/pull/5768) | `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md`<br>`openhands-agent-server/openhands/agent_server/profiles_router.py`<br>`tests/agent_server/test_profiles_router.py` | F20 | - ping 使用 LLM 的副本，其中包含 `num_retries: 0`，不包含 `fallback_strategy`，并且 `timeout` = min(15 s, posted timeout)。 posted config本身没有改变。- 5号的 SDK 的 `is_quota_exhaustion_error` 类别被 `valid: false` 识别为耗尽预算/配额，返回已脱敏提供商消息。 一个简单的429仍然`valid: true`。 - 验证-智能体-服务器映射：F20.validate-未检测到|已知缺陷的|家庭扫描。 [特征证据和限制](intent-runtime-overlay.md#pr-5768) |
| `c73ec79e3fd1` / [#5778](https://github.com/OpenHands/software-agent-sdk/pull/5778) | `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`<br>`clients/typescript/src/__tests__/remote-workspace-execute.test.ts`<br>`clients/typescript/src/workspace/remote-workspace.ts`<br>+2 条路径（完整列表如下） | F13, F14, F15, F16, F34 | - `bash_router.py`: 路由读取命令的 `BashOutput` 事件的每一页（按照 `next_page_id`），按 `order` 排序，分别将标准输出和标准错误输出合并，最后返回合并后的文本及其退出代码。 响应仍然是一`BashOutput`； 小输出不变。 - `clients/typescript`: `RemoteWorkspace.executeCommand` 将缺失的退出代码映射到 `-1` 而不是 `0`。 - 验证ag | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5778) |
| `bf9b6057b00e` / [#6036](https://github.com/OpenHands/software-agent-sdk/pull/6036) | `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` | 无需产品运行时间 | - 只跳过需要支持的 Linux 后端 artifacts 的测试。- 添加一个不包含回归的测试，覆盖 `unsupported` 状态、准备和启动。 | 有记录的 | 无需产品运行时； [特征证据和限制](intent-runtime-overlay.md#pr-6036) |
| `6235a41b5b84` / [#5951](https://github.com/OpenHands/software-agent-sdk/pull/5951) | `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`<br>`openhands-agent-server/openhands/agent_server/config.py`<br>`openhands-agent-server/openhands/agent_server/env_parser.py`<br>`tests/agent_server/test_config.py` | F01, F02, F03, F29, F31, F32 | - `env_parser.merge` 获得仅关键字 `none_overrides` 标志（默认 `False`，因此环境解析器内的合并不变）； 在它被设置后，后期的 `None` 会替换早期的，而 `MISSING` 仍然保留。- `load_config` 将环境覆盖到文件中，`none_overrides=True`。 环境数据中不存在没有 `OH_*` 变量的字段，因此文件值保持不变。 - | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5951) |
| `8869bcd914af` / [#5840](https://github.com/OpenHands/software-agent-sdk/pull/5840) | `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`<br>`openhands-agent-server/openhands/agent_server/dependencies.py`<br>`tests/agent_server/test_runtime_router.py` | F02, F03, F06, F13, F16, F30 | `get_bash_event_service` 当在受控请求中缺少运行时状态时，验证引发路径参数自身的错误 (`RequestValidationError`, loc `["path", "runtime_conversation_id"]`)，这样响应与其他受控路由返回的 422 响应体 FastAPI 相同。 有效id不变； 全球 `/api/bash/...` 路由未变。- 单元测试包含所有 7 个受管的 bash 路由，使用 `not-a-uuid | 记录 | 家族扫描，包含已知缺陷。 [特征证据和限制](intent-runtime-overlay.md#pr-5840) |
| `cab7bb4b2947` / [#5901](https://github.com/OpenHands/software-agent-sdk/pull/5901) | `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`<br>`openhands-sdk/openhands/sdk/skills/installed.py`<br>`tests/sdk/skills/test_installed_skills.py` | F25 | - `_load_skill_from_dir` (`openhands-sdk/openhands/sdk/skills/installed.py`)，技能安装路径使用的加载程序，将 `yaml.YAMLError` 转换为 `SkillValidationError`，匹配 `skill.py` 中的目录加载已经处理 YAML 错误的方式。 路由器无需更改：它已经将 `SkillValidationError` 映射到 422。 - 单元测试在 `tests/sdk/skills/test_installed_skills.py`：`install_skill` 提高了 SkillValidationErr | 记录的 | 家族扫描与缺陷。 [特征证据和限制](intent-runtime-overlay.md#pr-5901) |
| `acf55bcd2672` / [#5885](https://github.com/OpenHands/software-agent-sdk/pull/5885) | `.agents/skills/verify-agent-server/references/feature-map/F23-llm-catalog-and-connections.md`<br>`openhands-sdk/openhands/sdk/llm/utils/unverified_models.py`<br>`tests/sdk/llm/test_model_list.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - `get_supported_llm_models` 现在会丢弃 LiteLLM 的模型成本映射文件（`litellm_provider` `bedrock` `bedrock_converse` `bedrock_mantle`），除了 `bedrock` 前缀的 id，而不是添加更多的字符串启发式。 当凭据配置时，从 AWS 列出的 Bedrock 模型 `bedrock/<modelId>` 不会被修改。 这同样适用于SDK的UNVERIFIED_MODELS_EXCLUDING_BEDROCK|已记录的|缺陷家族扫描。 证据和限制[ ](intent-runtime-overlay.md#pr-5885) |
| `3adf42f6377b` / [#5884](https://github.com/OpenHands/software-agent-sdk/pull/5884) | `.agents/skills/verify-agent-server/references/feature-map/F22-meta-profiles.md`<br>`openhands-sdk/openhands/sdk/llm/meta_profile_store.py`<br>`tests/sdk/llm/test_meta_profile_store.py` | F04, F06, F07, F09, F20, F22, F23, F30, F33, F34 | - `default_meta_profile_dir()` (`openhands-sdk/openhands/sdk/llm/meta_profile_store.py`) 现在返回 `get_user_persistence_dir() / "meta-profiles"`，因此 `~` 被扩展，并且相对值与每个其他商店完全相同地锚定。 它在调用时仍然被评估，因此路由器、`launch.py`和裸`MetaProfileStore()`将其原样接收。- 新单元测试的`OH_PERSISTENCE_DIR='~/state'`。- F22.persist |文档了|的缺陷家族扫瞄。 [特征证据和限制](intent-runtime-overlay.md#pr-5884) |
| `e5a1602e3bbc` / [#5867](https://github.com/OpenHands/software-agent-sdk/pull/5867) | `.agents/skills/verify-agent-server/references/feature-map/F19-mcp.md`<br>`openhands-agent-server/openhands/agent_server/mcp_router.py`<br>`tests/agent_server/test_mcp_router.py` | F19 | - `_validate_callback_url` 将 `ValueError` 从 `.port` 转变为 `400 Unexpected OAuth callback URL`，并将 `ValueError` 从 `urlparse` 本身转变为 e.g。 `http://[::1/callback`，未闭合的 IPv6 括号）进入 `400 Invalid OAuth callback URL`。 有效的 URLs 和现有的检查保持不变。 `tests/agent_server/test_mcp_router.py`（端口99999，端口`abc`，畸形的IPv6）：任务仍在等待  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5867) |
| `7abcd3bab78f` / [#5916](https://github.com/OpenHands/software-agent-sdk/pull/5916) | `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`<br>`openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py`<br>`tests/agent_server/docker_runtime/test_proxy.py` | F12, F29 | - `proxy_http` (`docker_runtime/proxy.py`) 从它返回的响应中删除上游 `date` 和 `server` 标头，因此 uvicorn 的一对是唯一的。 `_filter_headers` 和请求头转发没有改变，`proxy_http` 与 Docker 运行时会话代理共享，该代理的内部 Agent Server 也会发送 `date`/`server`，因此那里也会消除同样的重复 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5916) |
| `079d410db4fe` / [#5826](https://github.com/OpenHands/software-agent-sdk/pull/5826) | `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md`<br>`openhands-agent-server/openhands/agent_server/event_service.py`<br>`tests/agent_server/test_conversation_response.py` | F05, F06, F07, F08, F09, F10, F11, F12, F31 | - `EventService._get_agent_final_response_sync` 现在将 `state.active_branch()` 传递到 `get_agent_final_response`。 这涵盖了 REST 路由和 OpenAI 兼容网关 (`openai/service.py`)，它们都经过 `EventService.get_agent_final_response`。 SDK 自己的调用者（任务管理器、委托、智能体挂钩）读取从未导航的新子对话，因此它们没有改变； TypeScript 客户 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5826) |
| `9ad70fedddc4` / [#5812](https://github.com/OpenHands/software-agent-sdk/pull/5812) | `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`<br>`clients/typescript/src/client/conversation-client.ts`<br>`clients/typescript/src/conversation/remote-conversation.ts` | F34 | - 重写两者 `switchAcpModel`  文档字符串通过实现实况会话切换 `session/set_model`; 在第一次运行之前，服务器回答 200 并存储第一个会话的模型； 非-ACP 对话返回 400 错误 `# bug` marker from the `F09.ts-client-acp-docs` 添加一个针对新措辞的正向检查，并更新 F09 警告行。- 不需要代码更改。 的 Python  文档字符串请输出简体中文译文 | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5812)  |
| `f676088d7a46` / [#5802](https://github.com/OpenHands/software-agent-sdk/pull/5802) | `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`<br>`openhands-agent-server/openhands/agent_server/models.py`<br>`tests/agent_server/test_conversation_router.py` | F04, F08, F10, F11, F12, F13 | - `UpdateConversationRequest` 获取 `title` 字段验证器，该字段在修剪后拒绝一个空标题，因此路由在服务运行之前就回答了 `422`，并且存储的标题保持不变。 非空白标题未更改（服务仍会删除它们； `max_length=200`仍然适用）。 - 新的路由器测试 `test_update_conversation_whitespace_only_title_rejected`（空格和制表符/换行符）断言 `422` 并且 se | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5802) |
| `478a6f9caebc` / [#5864](https://github.com/OpenHands/software-agent-sdk/pull/5864) | `.agents/skills/verify-agent-server/references/feature-map/F17-workspaces-registry.md`<br>`openhands-agent-server/openhands/agent_server/persistence/store.py`<br>`tests/agent_server/test_workspaces_router.py` | F03, F17, F18, F31 | - 当 `update_fn` 返回给定的文档时，`FileWorkspacesStore.update` 跳过 `save`； 每个路由的 `apply` 已经返回其输入不变，以进行无操作，因此不需要更改路由器。 实际添加和删除仍然写入（并且仍然在只读存储上回答 500）。 - `tests/agent_server/test_workspaces_router.py` 中的两个单元测试：拒绝删除新目录不会留下任何文件； `save` 失败了，  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5864) |
| `07e6e059afd8` / [#5851](https://github.com/OpenHands/software-agent-sdk/pull/5851) | `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md`<br>`openhands-agent-server/openhands/agent_server/settings_router.py`<br>`tests/agent_server/test_settings_router.py` | F18, F19, F32 | - 文档字符串和 `get_secret_value`、`delete_secret` 现在都说 `422 if name format is invalid`。 状态码未改变。`PUT /api/settings/secrets`已经说成422了， https://github.com/OpenHands/software-agent-sdk/pull/5682. 已经说了。- 新的参数化测试检查，针对GET、DELETE和PUT，检查无效名称会返回422，而路由的`/openapi.json`描述会返回422而不是400。- 丢弃了F18.secret |已记录的|家族扫查有已知缺陷的文档。 [特征证据和限制](intent-runtime-overlay.md#pr-5851) |
| `fd96074269ce` / [#5874](https://github.com/OpenHands/software-agent-sdk/pull/5874) | `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md`<br>`openhands-agent-server/openhands/agent_server/agent_profiles_router.py`<br>`tests/agent_server/test_agent_profiles_router.py` | F21, F30 | - 仅文档字符串：描述实际报告的内容。 无行为改变。- `test_seed_skips_ghost_llm_profile_for_bare_defaults` 现在也标记了 `errors` 的条目，以及在 `dangling_llm_profile_ref` 的材料化体中不存在。- 验证-智能体-服务器映射：在 `F21.dangling-llm-report` 上移除已知缺陷标志，并将其语句重写为预期行为。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5874) |
| `8d2c996de5bf` / [#5966](https://github.com/OpenHands/software-agent-sdk/pull/5966) | `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`<br>`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`<br>`tests/sdk/conversation/remote/test_remote_events_list.py` | F33 | - `RemoteEventsList.create_default_callback()` 跳过 `StreamingDeltaEvent`； 用户回调和视觉化器仍然接收每个 delta。- 单元测试：默认回调会将 deltas 从缓存事件中剔除。- Map：从 `F33.conversation-streaming-state` 中移除 `# bug` 标记，并重写其文本和 Gotchas 行以反映预期行为。 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5966) |
| `57c71706e83c` / [#5917](https://github.com/OpenHands/software-agent-sdk/pull/5917) | `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`<br>`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`<br>`tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` | F28 | - `CanvasExtensionBackendManager.prepare` 将提取中的存档格式错误 (`tarfile.TarError`、`gzip.BadGzipFile`、`EOFError`、`zlib.error`) 转换为 `ValueError("backend artifact is not a valid gzip tar archive")`，因此路由会回答 409。 临时提取目录仍然被删除，没有写入批准。- 单元测试对于纯字节、gzip 但不是 tar 和截断的 gzip 产物（man） | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5917) |
| `1396fa7ff651` / [#5898](https://github.com/OpenHands/software-agent-sdk/pull/5898) | `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md`<br>`openhands-agent-server/openhands/agent_server/settings_router.py`<br>`tests/agent_server/test_settings_router.py` | F18, F19, F32 | - `list_secrets` 现在读取 `store_errors()` 内的范围配置文件，因此路由像智能体-配置文件路由一样回答 400 / 503； 未知的 ID 仍会回答 404，有效的 ID 仍会在列表范围内。 - `tests/agent_server/test_settings_router.py` 中的两个单元测试（可卸载配置文件 -> 400，锁超时 -> 503）。 - 特征图 `F18.secret-scope-profile-errors`：`# bug` 标记被删除，散文和陷阱线重新编写 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5898) |
| `75dec1d3ef1c` / [#5875](https://github.com/OpenHands/software-agent-sdk/pull/5875) | `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`<br>`openhands-agent-server/openhands/agent_server/bash_service.py`<br>`tests/agent_server/test_bash_service.py` | F13 | - `BashEventService._timestamp_to_str` 现在将知道的日期时间转换为 UTC 在格式化之前，匹配  UTC 文件名前缀（事件时间戳来自 ) `utc_now()`). 仍然读取粗略的上下限 UTC- 专注单元测试：`+02:00` [bounds on both] `timestamp__gte` 和 `timestamp__lt`加上朴素的情况。- 特征映射： `F13.timestamp-offset` 子弹失去了 `known bug` label 和 `# bug` marker, its prose a | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5875) |
| `5f2185ed6333` / [#5957](https://github.com/OpenHands/software-agent-sdk/pull/5957) | `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`<br>`clients/typescript/src/__tests__/agent-server-contract-types.test.ts`<br>`clients/typescript/src/__tests__/remote-workspace-git.test.ts`<br>`clients/typescript/src/index.ts`<br>+1 条路径（完整列表如下） | F34 | - `GitChange.status` (`clients/typescript/src/models/workspace.ts`) 现在是生成合约的 `GitChangeStatus`，因此它不会再次从服务器漂移； `GitChangeStatus`也是从主入口导出的。 - 测试：`agent-server-contract-types.test.ts` 中的类型级检查（导出的状态等于生成的状态，也通过 `RemoteWorkspace.gitChanges`）以及 `remote-工作区-gi | 中的运行时测试，记录了具有已知缺陷的 | 系列扫描； [ 特征证据和限制](intent-runtime-overlay.md#pr-5957) |
| `47c50f7e5c68` / [#6038](https://github.com/OpenHands/software-agent-sdk/pull/6038) | `openhands-tools/openhands/tools/terminal/terminal/tmux_terminal.py`<br>`tests/agent_server/test_api.py`<br>`tests/tools/terminal/test_tmux_pane_pool.py` | F13, F27, F31, F33 | - 使用Agent Server的canonical-byte-length方法选择一个显式的短`/tmp` tmux套接字路径，当原始路径超出平台的Unix-socket限制时，不修改进程级`TMUX_TMPDIR`。- 保持套接字创建锁定与选择的套接字路径一起。- 在一个过长的目录下执行真实的独立和池化终端会话。 给共享套接字 Agent Server 测试短 t | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-6038) |
| `f621dab57be8` / [#5973](https://github.com/OpenHands/software-agent-sdk/pull/5973) | `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`<br>`openhands-agent-server/openhands/agent_server/api.py`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>`openhands-agent-server/openhands/agent_server/event_service.py`<br>+3 条路径（完整列表如下） | F01, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F30, F31, F32 | - `EventService.save_meta(stored=None)` 现在使用新的 `StoredConversation`，写在租约保护下，然后制作出来 `self.stored` 只有写成功后，持久化首先，正如问题所指出的。 `update_conversation`, `AutoTitleSubscriber` 和 `update_secrets` 构建一个 `model_copy` 并传递它。 `update_conversation` 应用了 `ConversationState.tags` 仅在保存后更新ConversationOwne  | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5973)  |
| `8cfff960ff3b` / [#5956](https://github.com/OpenHands/software-agent-sdk/pull/5956) | `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`<br>`clients/typescript/src/__tests__/api-clients.test.ts`<br>`clients/typescript/src/client/conversation-client.ts`<br>`clients/typescript/src/conversation/conversation-manager.ts` | F34 | - `ConversationManager.updateConversation` 和 `ConversationClient.updateConversation` 将 PATCH 输入为 `Success`，并通过 `getConversation` 读回对话来解决。 - 两种方法的新单元测试； 现有的 `ConversationClient` 包装测试占了额外的 `GET`。 - 地图：`F34.manager-update-result` 失去了 `# bug` 标记和“已知错误”标签； 散文和陷阱线现在描述  | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5956) |
| `804498a61126` / [#5968](https://github.com/OpenHands/software-agent-sdk/pull/5968) | `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md`<br>`openhands-agent-server/openhands/agent_server/openai/service.py`<br>`tests/agent_server/test_openai_gateway_reused_wait.py` | F30 | - `_wait_for_reused_conversation_completion` 现在也返回 `paused` 和 `waiting_for_confirmation`。 它保持相同的守卫（上次的运行被看到 `running`，或者新的事件到达），因此，之前的状态不会提前结束等待。 `_raise_for_terminal_error` 然后返回 409 `Agent run ended with status: <status>`，这是新对话得到的相同答案。- 新单元测试 `tests/agent_server/ | 记录了 | 家族扫描-包含已知缺陷的扫描。 [ 特征证据和限制](intent-runtime-overlay.md#pr-5968) |
| `b301ee008178` / [#5965](https://github.com/OpenHands/software-agent-sdk/pull/5965) | `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`<br>`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`<br>`tests/sdk/conversation/remote/test_remote_conversation.py` | F33 | - `RemoteConversation.__init__` 接受 `token_callbacks`（作为最后一个命名参数添加，因此位置调用者不受影响）并将其传递给 `_initialize_connection`。 - 当给出 token 回调时，一个小事件回调将套接字中的每个 `StreamingDeltaEvent` 转换为 `LLMStreamChunk` (`choices[0].delta.content` / `reasoning_content`)，与本地对话的 token 回调接收的类型相同 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5965) |
| `4fedb7e2b524` / [#5877](https://github.com/OpenHands/software-agent-sdk/pull/5877) | `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md`<br>`clients/typescript/config/public-type-budget.json`<br>`clients/typescript/src/__tests__/agent-server-contract-types.test.ts`<br>`clients/typescript/src/__tests__/api-clients.test.ts`<br>+2 条路径（完整列表如下） | F34 | - `clients/typescript/src/models/agent-profile.ts`：声明服务器的Pydantic模型发送的字段（`openhands-sdk/openhands/sdk/profiles/agent_profile.py`，`resolver.py`），并删除`skills`和`resolved_mcp_servers`。 `AgentProfileSaveInput`因此不再提供`skills`。 - `agent-server-contract-types.test.ts` 断言 `keyof` 四种导出类型及其生成的合约计数之间相等 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5877) |
| `8ee5cba234d1` / [#5868](https://github.com/OpenHands/software-agent-sdk/pull/5868) | `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md`<br>`openhands-agent-server/openhands/agent_server/profiles_router.py`<br>`openhands-sdk/openhands/sdk/llm/llm_profile_store.py`<br>`openhands-sdk/openhands/sdk/profiles/profile_refs.py`<br>+2 条路径（完整列表如下） | F04, F06, F07, F09, F20, F21, F22, F23, F30, F33, F34 | - 在`llm_profile_store.py`中添加`canonical_profile_name()`（由`_get_profile_path`使用）。 `profile_refs.py`中的`_scan_referrers`/`_rewrite_refs`比较并写入规范密钥。 - `profiles_router.py`: `_set_active_profile_if_matches` 比较规范密钥并存储规范新名称，激活记录规范名称。 - 功能图：删除 `F20.json-alias-guard` 已知错误标记，断言 409 a | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5868) |
| `e785defbf652` / [#5953](https://github.com/OpenHands/software-agent-sdk/pull/5953) | `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>`tests/agent_server/test_webhook_subscriber.py` | F04, F05, F10, F12, F31, F32 | - `WebhookSubscriber._post_events` 在排空启动时排队的内容后重新检查缓冲区，并在缓冲区再次满时继续发布（计数或 `max_batch_bytes`）。 还有一个请求正在处理中； 失败的 POST 仍然重新排队并将 REST 留给刷新计时器。 一旦队列耗尽，在 POST 期间启动的刷新计时器将被取消（而不是当 `_post_events` 在该计时器内运行时）。 `__call__` 不变 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5953) |
| `14f821bb2af5` / [#5848](https://github.com/OpenHands/software-agent-sdk/pull/5848) | `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`<br>`openhands-sdk/openhands/sdk/git/git_changes.py`<br>`tests/sdk/git/test_git_changes.py` | F15 | - `get_changes_in_repo` (`openhands-sdk/openhands/sdk/git/git_changes.py`) passes `--relative` to `git diff --name-status`因此，修订记录仅限于和相对于请求的目录，就像 `git ls-files --others`. 仓库根目录不受影响`--relative` 从顶层来看，这是一个无操作（no-op）。- 测试： `get_changes_in_repo` 在 `src/` 在其中包含更改（修改、删除、未更改）的仓库（修改、删除、未更改） | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5848) |
| `9af99982a125` / [#5967](https://github.com/OpenHands/software-agent-sdk/pull/5967) | `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`<br>`openhands-agent-server/openhands/agent_server/telemetry/subscriber.py`<br>`tests/agent_server/telemetry/test_telemetry_subscriber.py` | F32 | - `TelemetrySubscriber` 现在记录带有统计数据的每个状态更新的使用情况：`key="stats"` 更新 `EventService` 在每次 LLM 调用后发布，以及 `full_state` 快照。 每个终端排放（`finished` 失败状态，`interrupted` 回退方案从 `close()`）汇总了最新的总和。 原始数据从未发送，订阅者始终为总和且非阻塞。- 新单元测试：`测试 | | 家族扫描，已知缺陷。` [特征证据和限制](intent-runtime-overlay.md#pr-5967) |
| `7d459bcb1111` / [#5964](https://github.com/OpenHands/software-agent-sdk/pull/5964) | `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`<br>`openhands-agent-server/openhands/agent_server/config.py`<br>`tests/agent_server/telemetry/test_telemetry_disabled_by_default.py` | F01, F02, F03, F29, F31, F32 | - 将 `TelemetrySpec.salt` 描述重写为与代码匹配：salt，否则机密键（默认为第一个会话 API 键，因此重启后可以链接引用），否则一个随机的进程级键。 没有行为改变。 README的`OH_TELEMETRY_SALT`行已经说了这件事。- 添加一个单元测试，将描述与`build_telemetry_sink`的行为联系起来（[refs]等于`pseudonymize(id.bytes | documented | family-sweep-with-known-defects`）。 [ 特征证据和限制](intent-runtime-overlay.md#pr-5964) |
| `615759cc3497` / [#5958](https://github.com/OpenHands/software-agent-sdk/pull/5958) | `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`<br>`openhands-agent-server/openhands/agent_server/conversation_router.py`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>+2 条路径（完整列表如下） | F04, F05, F08, F09, F10, F11, F12, F31, F32 | - `_create_conversation` 记住的那些 `tool_module_qualnames` 模块未导入成功。 once the 智能体如果 ，则智能体使用了这些工具之一，否则无法解决，就会引发 `UnavailableAgentTool`该端点被映射到  `422`. 一个工具的模块智能体它仍然只是一个警告。 `F33.custom-tool-module-unimportable` 丢弃了已知错误标记，并现在宣称 `4 | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5958)  |
| `eac3ee16cc98` / [#5859](https://github.com/OpenHands/software-agent-sdk/pull/5859) | `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md`<br>`openhands-agent-server/openhands/agent_server/vscode_service.py`<br>`tests/agent_server/test_vscode_service.py` | F16 | - `VSCodeService.get_vscode_url` 使用 `urlencode(..., quote_via=quote, safe="/")` 构建查询，因此 `folder`（和 `tkn`）准确解码； `/` 保持可读，因此 `folder=/workspace` 不变。 - 单元测试用于往返（`&`、`#`、`?`、`%`、`+`、空格）和精确的编码形式。 - 特征图：`F16.vscode-folder-encoding` 失去了 `# bug` 标记和“已知错误”标签，其散文现在说明了预期 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5859) |
| `af05c8b46a8a` / [#5856](https://github.com/OpenHands/software-agent-sdk/pull/5856) | `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`<br>`openhands-agent-server/openhands/agent_server/file_router.py`<br>`openhands-agent-server/openhands/agent_server/models.py`<br>`tests/agent_server/test_file_router.py` | F04, F08, F10, F11, F12, F13, F14 | - `_upload_file` 计算流到磁盘的字节数并将其返回为 `file_size`； 两个上传路由共享它。 - `tests/agent_server/test_file_router.py` 断言小上传、分块 (>8 KiB) 上传和覆盖的大小。 - `F14.upload-size` 地图项目符号删除了其 `# bug` 标记和“已知错误”标签，现在还检查原始 REST 响应的 `file_size`，其散文和陷阱行描述了 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5856) |
| `501d27323cf3` / [#5853](https://github.com/OpenHands/software-agent-sdk/pull/5853) | `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`<br>`openhands-agent-server/openhands/agent_server/file_router.py`<br>`tests/agent_server/test_file_router.py` | F14 | 按排序 `(name.lower(), name)`订单仍保持不区分大小写的模式，现在大小写相同的双胞胎具有稳定的顺序 `next_page_id` 现在是下一个条目的确切名称。 A `page_id` 该端点不匹配任何精确名称时，会回退到旧的不区分大小写的匹配，因此一个来自较旧服务器的下划线光标仍然会回到其入口单元测试翻页 `Foo`/`foo`, 并从小写光标处继续。 The ```F14.sub  | 有记录的 | 具有已知缺陷的家庭清扫； [证据和限制](intent-runtime-overlay.md#pr-5853)  |
| `e98b95654fdf` / [#5819](https://github.com/OpenHands/software-agent-sdk/pull/5819) | `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md`<br>`openhands-agent-server/openhands/agent_server/conversation_router.py`<br>`tests/agent_server/test_conversation_router.py` | F04, F05, F08, F09, F10, F11, F12 | - `conversation_router.ask_agent`：映射服务的`None`（仅在会话丢失时返回； `EventService.ask_agent` 将 `str`) 返回到 `404 "Conversation not found"`，与 `condense` 给出的答案相同。 - 用于未知 ID 情况的路由器单元测试。 - verify-智能体-server 映射：删除 `F10.ask-agent-unknown` 已知错误标记，检查 404 详细信息，并在路由响应中列出 404。 `RemoteConversat | 记录了具有已知缺陷的 | 系列扫描； [特征证据和限制](intent-runtime-overlay.md#pr-5819) |
| `7f41284acefd` / [#5811](https://github.com/OpenHands/software-agent-sdk/pull/5811) | `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`<br>`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`<br>`tests/sdk/conversation/test_switch_model.py` | F05, F08, F09, F10 | - `LocalConversation.switch_acp_model` 现在拒绝实时/预运行分支之前的空或仅空白模型（`ValueError`，与 `set_acp_model` 相同的消息），因此没有任何内容已持久化。 智能体-服务器路由已经将`ValueError`映射到400； TypeScript客户端仅转发请求，因此没有任何变化。 - 单元测试用于 `tests/sdk/conversation/test_switch_model.py` 中的预运行空白案例（`""` 和 `" "`） | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5811) |
| `9d07c6d55d1b` / [#5795](https://github.com/OpenHands/software-agent-sdk/pull/5795) | `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`<br>`openhands-agent-server/openhands/agent_server/conversation_router.py`<br>`tests/agent_server/test_conversation_router.py` | F04, F05, F08, F09, F10, F11, F12 | - 将限制声明为 `ids: Annotated[list[UUID], Query(max_length=99)]` 并删除断言。现在，100+ 个 ID 会返回 422 错误（"列表应最多有 99 个项目"），服务未被调用，OpenAPI 显示 `maxItems: 99`，这遵循了搜索 `le=100` 上声明的 `limit`（ https://github.com/OpenHands/software-agent-sdk/issues/5114 ）。- 路由测试现在断言 422 错误，它以前断言 `AssertionError`，99 个 ID | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5795) |
| `75abe1eb3f5f` / [#5773](https://github.com/OpenHands/software-agent-sdk/pull/5773) | `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F06-conversation-events.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F08-confirmation-security-secrets.md`<br>`.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`<br>+3 条路径（完整列表如下） | F05, F06, F07, F08, F09, F10, F11, F12, F31 | - `EventService._event_matches_filters`（由`search_events`和`count_events`共享）现在接受裸类名或完全限定的类路径。 未知或部分名称仍然会给出空白页面/`0`，并且`kind`仍然与其他过滤器结合。 模式或 TypeScript 客户端的有线格式没有变化。 - `tests/agent_server/test_event_service.py` 中的单元测试覆盖 s 的缩写 | 有记录的 | 具有已知缺陷的家庭清扫； [特征证据和限制](intent-runtime-overlay.md#pr-5773) |
| `1fbfd37f6fb2` / [#5783](https://github.com/OpenHands/software-agent-sdk/pull/5783) | `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`<br>`clients/typescript/src/__tests__/conversation-create-options.test.ts`<br>`clients/typescript/src/conversation/base.ts`<br>`clients/typescript/src/conversation/conversation-manager.ts`<br>+1 条路径（完整列表如下） | F34 | - `ConversationManager.createConversation` passes `maxIterations` and `stuckDetection` to `RemoteConversation.start()`. - `RemoteConversation` keeps both constructor options and uses them as 回退方案 in `start()`; `0`/omitted的处理方式 `maxIterations` (`\|\| 500`) 未改变。 此外，修复了`BaseConversationOptions.maxIterations`（默认值为500）上的“default: 50”过时的文档注释。- 新增“conversation-cr |”文档|家族扫除带有已知缺陷的扫除。 证据和限制[ ](intent-runtime-overlay.md#pr-5783) |
| `5966c781ed01` / [#5126](https://github.com/OpenHands/software-agent-sdk/pull/5126) | `openhands-agent-server/openhands/agent_server/api.py`<br>`openhands-agent-server/openhands/agent_server/config.py`<br>`openhands-agent-server/openhands/agent_server/conversation_router.py`<br>`openhands-agent-server/openhands/agent_server/conversation_service.py`<br>+12条路径（完整列表如下） | F01, F02, F03, F04, F05, F06, F08, F09, F10, F11, F12, F13, F27, F29, F30, F31, F32, F33, F34 | - `POST /api/conversations/{conversation_id}/children`，由 `ConversationService.start_child_conversation` 支持。 就像叉子一样，子进程会复制父进程的存储配置（机密，客户端工具、插件、钩子、标签、确认和安全设置），并使用智能体解析。但它从一个空的历史开始，收到`task`作为其第一个用户消息，并记录`parent_conversation_id`。隔离="工作树 | 记录了 | 家族扫除，带有已知缺陷。 [特征证据和限制](intent-runtime-overlay.md#pr-5126) |

<a id="per-pr-evidence"></a>

## 每PR证据

<a id="5467-fixllm-stop-string-serializing-vision-capable-deepseek-v4-models"></a>

### ＃5467：fix(llm)：停止字符串序列化具有视觉功能的DeepSeek v4模型

- 提交：`608a102c637d8d8a999f49d7b04846524bd8bd1c` (2026-10-06T22:17:37-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5467).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5467)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - 从裸露的 `"deepseek"` 缩小自动字符串 - 序列化器条目
>   遗留 `"deepseek-v3.2"` 系列的子字符串，因此 `DeepSeek-V3.2-Exp` /
>   `deepseek-v3.2-reasoner` 保留仅字符串内容，而 v4、v4.1、
>   `v4-flash-vision-exp` 和 `deepseek-chat` ids 保留结构化（列表）内容。
> - 添加功能注册表回归覆盖范围，断言 v4/v4.1 id 解析
>   `force_string_serializer is False` 而 v3.2 系列保留 `True`。
> - 添加格式化的载荷回归测试，证明视觉活跃
>   `openhands/deepseek-v4.1-flash` 保留一个 `image_url` 部分。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/model_features.py`
- `tests/sdk/llm/test_llm.py`
- `tests/sdk/llm/test_model_features.py`
- `tests/sdk/llm/test_vision_support.py`

链接问题接受上下文：

- [#5360](https://github.com/OpenHands/software-agent-sdk/issues/5360)：[缺陷]：force_string_serializer` blanket `"deepseek"` 子串会导致具备视觉能力的 deepseek-v4.1-flash 丢失图像；当前状态为已关闭，关闭时间为 2026-10-07T02:17:39Z。

> - [  ] A `deepseek`-命名的模型报告 `supports_vision=True` 不再有图像部分被裁剪image_url 在格式化中出现的载荷). - [  ]  `FORCE_STRING_SERIALIZER_MODELS` 不再使用无引号的 `"deepseek"` substring; 只有那些真正需要字符串内容的特定遗留ID匹配 [  ]  单元测试 asserting `get_features("openhands/deepseek-v4.1-flash").force_string_serializer is False` (或者，一个具有视觉能力的模型从不字符串化)已序列化). - [  ] 现有 `DeepSeek-V3.2-Exp` 字符串-序列化器行为 (PR #994/#996) 保留。### 安装方法 `pip install openhands-sdk` 如果您选择了“其他”，请填写 _无_ SDK 版本 `openhands-sdk==1.49.6` （也存在于 ） `main` 在提交时： `FORCE_STRING_SERIALIZER_MODELS` 仍然包含裸露的 `"deepseek"` substring). ### 版本确认 - [x] 我已经确认该 bug 存在于  LATEST 版本 OpenHands  SDK ### Python 版本 3.12 ### 如果适用，请输出模型名称 `openhands/deepseek-v4.1-flash` （也重复了推理） `deepseek-v4-flash`, `deepseek-v4-pro`). 提供商报告 `supports_vision=True`操作系统 MacOS 错误被抛出时，图像将被默默删除。 证据从 `LLM.format_messages_for_llm`: ``` force_string_serializer=None -> effective=True images_in_payload=0 # default (bug) force_string_serializer=False -> effective=False images_in_payload=1 # fix force_string_serializer=True -> effective=True images_in_payload=0 ``` 直接提供商探针（带有列表的工具消息 vs. 圣

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5467#pullrequestreview-5402967894)_这篇评论是由AI发布的智能体 (OpenHands## 项目范围与摘要匹配此仓库。 该变化仅限于  SDK  LLM feature 注册表 (`openhands-sdk/openhands/sdk/llm/utils/model_features.py`), which `AGENTS.md` 标识为模型/提供者能力调整的家园，并且实现了由关联问题的初步审核所规定的最小化限制（替换为裸） `"deepseek"` 包含子字符串的 `"deepseek-v3.2"`. ## 验证 - **修复是正确的。** 在当前的主干上， `openhands/deepseek-v4.1-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-v4-flash-vision-exp`, and `deepseek-chat` 全部解决 `force_string_serializer=False`, while `DeepSeek-V3.2-Exp` 和 `deepseek-v3.2-reasoner` remain `True`. 在视觉功能激活时，格式化v4.1-flash 载荷保持其 `image_url` 与报告的根 CA 匹配的部分
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5467#pullrequestreview-5436847998)：谢谢您的修复！

<a id="5548-testagent-server-real-docker-scenario-for-storage-reclaim"></a>

### ＃5548：test(agent-server)：存储回收的真实Docker场景

- 提交：`91ac058a08fd6365286fc8c5628f35a5f41ff300` (2026-10-07T12:51:16+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5548).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5548)。 Families: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34.

陈述意图：

> - `tests/agent_server/docker_runtime/test_storage_scenario.py`：针对真实的 Docker 守护进程和智能体服务器映像进行五次测试。 服务器通过`OH_*`环境变量进行配置，就像CLI一样，并驱动真实的容器。 每个测试都会检查什么必须生存以及什么必须消失：
>   1. **仅可重建文件。**停止对话只会掉落 `~/.cache` 和 `~/.npm`； 在磁盘预算上通过后，丢弃了`node_modules/`、`.venv/`、`build/`以及嵌套检查出的`node_modules/`，保留了shell历史、配置、跟踪文件、未跟踪的笔记、一个被忽略的`.env`，一个被忽略的`vendor/`中的克隆，以及`.git`。 正在运行的对话逐个文件都没有改变。
>   2. **sandbox中植入的链接被移除，从不被访问。**: `~/.npm`和一个指向忽略的`build/`中的链接，指向主机路径，以及`~/.cache`（相对地）指向运行时自己的工作区。 链接和`build/`去； 所有目标都存活下来。
>   3. **来电者提供的工作区永远不会被丢弃**，即使超出预算。
>   4. **回收的对话恢复并运行**（读取工作区文件 

更改的路径：

- `.github/workflows/storage-scenario.yml`
- `pyproject.toml`
- `tests/agent_server/docker_runtime/STORAGE_SCENARIO.md`
- `tests/agent_server/docker_runtime/test_storage_scenario.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5548#issuecomment-6015363913)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews COMMENTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5548#pullrequestreview-5438953842)_这篇评论是由AI发布的智能体 (OpenHands)._ 范围：这是在正确仓库中进行的测试/CI/文档更改智能体- 服务器存储回收，因此没有所有权或架构 concern. 我在头部检查了什么 `6435a40`- 新增 `docker_live` 默认情况下，标记会被选中`pyproject.toml`  `addopts`), 与现有匹配 `stress`/`acp_live` 模式，以及新的 `Storage scenario` 工作流在相关路径更改时运行。 的 `Storage scenario` 检查通过了单元测试对于同一个模块，仍然可以通过。 `uv run pytest tests/agent_server/docker_runtime/` -> 108通过，5未通过。- 在这个分支上，有一个检查失败 `Agent Server`, 是 `Build & Push (golang-arm64)` job failing on a  `wget` openvscode-server (`exit code: 8`— 一个无关的、已存在的图像构建失败，不是由这个引起的 PR. 一种材料
- [评论； APPROVED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5548#pullrequestreview-5441057382)：智能体（OpenHands）发布的评论。范围：拥有仓库中的测试/CI/仅文档更改（智能体-服务器存储回收）。 没有所有权或架构关注。 我验证了 `1baaae41`（分支合并 `main`）：- PR 与 `main` 的差异是 4 个文件（工作流，`pyproject.toml`，场景测试，场景文档）； 主分支合并本身不是更改集的一部分。 - `pyproject.toml` 默认取消选择新的 `docker_live` 标记，与现有的 `stress`/`acp_live` 模式匹配； 新的`Storage scenario`工作流通过了这个头（运行37607965606）。- 在被触摸的包中，单元测试的焦点通过：`uv run pytest tests/agent_server/docker_runtime/` -> 108通过，5被选中（5个新docker_live测试，如预期）。- 当使用Docker或镜像时，`docker_live`的测试可以干净地跳过
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5548#discussion_r4204168947)这种植入了 `build` 因为硬链接从不被选择，所以测试无法验证一个伪装的忽略目录链接是否被移除。 证据（在本证据中验证过） 工作区与真正的选择器相对）：- `openhands/agent_server/storage/selectors.py`  `git_ignored_dirs()` 丢弃任何候选者 `not path.is_symlink()`, and the preceding `git ls-files --others --ignored --exclude-standard --directory` 它甚至没有列出一个指向忽略目录的符号链接 `ignored_dirs()` 在工作区完全按照这个测试构建的`build/` 忽略 `build` -> host dir, plus a nested `sub/node_modules`) 返回只有一部分 `['sub/node_modules']` — `build` 不存在。 因为最终的断言只检查了链接 *目标* survives (`(outside / name / "precious")`如果软链被删除，测试就会通过。 因此它不涵盖

<a id="5538-fixagent-server-tolerate-state-saves-while-zipping-a-trajectory"></a>

### ＃5538：fix(agent-server)：在压缩轨迹时容忍状态保存

- 提交：`69e26889401fe69157fff536e6a69049e6644cb3` (2026-10-07T18:46:12+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5538).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5538)。 族：F05、F06、F07、F08、F09、F10、F11、F12、F14、F18、F20、F21、F22、F31。

陈述意图：

> - `_create_zip_from_directory` 跳过在列出和读取之间引发 `FileNotFoundError` 的任何条目（文件或目录），并在读取之前跳过每个 `*.tmp` 文件； 每个替换的文件都像往常一样存档。 `atomic_write_text` 现在将其临时文件命名为 `.<name>.<random>.tmp` (`tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp")`)，并且会话租约在将其重命名为 `owner_lease.json` 之前已经写入了 `owner_lease.tmp`，因此该规则涵盖了两者。 它位于 `is_temp_file()` 中，位于 `openhands.sdk.utils.files` 中的编写器旁边，并且测试将其与编写器实际创建的临时文件进行检查。 其他点文件，例如 `.env.template`，已存档。 副作用：每个 `atomic_write_text` 临时文件现在都以 `.tmp` 结尾，无论它写入何处。 存储库中的任何内容都不依赖于旧名称，并且事件存储仍然忽略这些文件，因为它们以点开头。
> - 每个 `.json`/`.jsonl` 文件被读取一次，并且这些字节都被检查机密并存档。 `redacted_file_bytes(path)` 被一分为二：`should_redact(path)` 是 p 的一个地方

更改的路径：

- `openhands-agent-server/openhands/agent_server/_secret_redaction.py`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `openhands-agent-server/openhands/agent_server/file_router.py`
- `openhands-sdk/openhands/sdk/utils/files.py`
- `tests/agent_server/test_event_service.py`
- `tests/agent_server/test_file_router.py`
- `tests/sdk/utils/test_files.py`

链接问题接受上下文：

- [#5537](https://github.com/OpenHands/software-agent-sdk/issues/5537): [Bug]: 在构建zip时替换状态文件时，下载轨迹返回500 — 当前状态已关闭，关闭于2026-10-07T16:46:14Z。

> - 当列出的文件或目录在读取之前被重命名或删除时，[ ] `download-trajectory` 返回 200。 - [ ] 未完成 `atomic_write_text` 临时文件未添加到轨迹 zip 中。 - [ ] 每个存档的 JSON 文件都保存检查过机密的字节，即使在构建 zip 时文件被替换也是如此。 - [ ] `meta.json` 以原子方式保存，因此下载永远不会存档部分写入的副本（请参阅证据）。 ### 安装方法源码签出（`uv sync`），Agent Server从`python -m openhands.agent_server`开始。 CI 使用为 #5531 构建的智能体-服务器映像。 ### 如果您选择“其他”，请注明_无响应_ ### SDK 版本 1.53.0。 在 `main` 的 `cb7eaba` 处找到，并在 `6f8c38d` 的当前 `main` 上再次检查，其中 `file_router.py`、`_secret_redaction.py` 和 `event_service.py` 未更改。 上面的数字和代码示例来自`6f8c38d`。 ### 版本确认 - [x] 我已确认 OpenHands SDK 的 LATEST 版本上存在此错误 ### Python 版本 3.13（本地 3.13.14，CI 3.13.15） ### 型号名称（如果适用）_无响应_ ### 操作系统 Linux ### 来自 CI 的日志和错误消息（“TypeScript 客户端集成测试 /集成测试”，运行 37385593191 尝试 1，作业 112017951574，#5531，位于 `7aff7ee`； 重新运行通过）。 Agent Server 记录：``` GET /api/file/download-trajectory/83012474-5e40-421c-a7e9-4163fb38e3c7 [error_id=22f9e76ca40a49ebb5f63550626a5f50] 上未处理的异常回溯（最近一次调用）：... 文件“/agent-server/.venv/lib/python3.13/site-packages/openhands/agent_server/file_

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5538#issuecomment-6009377263)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5538#pullrequestreview-5439082159)_这篇评论是由AI发布的智能体 (OpenHands)._ fix(agent-server)已审查的头：在压缩轨迹时容忍状态保存 `c9f9868d3c53530d431c7fb4f401085613a6a96c` 匹配了请求的头部； base `main`). 范围门：这是一个 Agent Server 行为修正，无 REST 合同变更且无 `clients/typescript` 更改，因此应该在这个仓库中进行验证 **CI 在头部：** 除了 ，所有检查都通过了 `unresolved-review-threads`这是仓库的合并前卫生检查门。 因为它只有在评论者打开时才会失败 `Final[str]` / `is_temp_file` nit 线程 from @VascoSch92 尚未解决，不是因为代码缺陷。 `agent-server-tests`, `cross-tests`, `integration-test`, `pre-commit`, `REST API (OpenAPI)`, `windows-tests`，打包任务都为绿色 **聚焦测试在
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4191932773)：使用contextlib.Suppress
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4192145476)：我是AI 智能体（Claude Code），帮助Engel Nyst(@enyst)进行项目工作。 在 6f6176c94 中完成：循环现在使用 `contextlib.suppress(FileNotFoundError)`。 测试 (214) 和预提交通过。 --- _由 [Claude Code](https://claude.ai/code) 生成_
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4192159065)：后缀检查两次：一次在 file_router.py:179 (REDACTED_SUFFIXES) 处，另一次在 redacted_json_bytes (_secret_redaction.py:76) 内。 我只会保留其中一项检查，因此文件获取已脱敏的规则位于一处。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4192169685)：可选：`save_meta` 是异步，但 `atomic_write_text` 现在直接在事件循环上进行 mkstemp + fsync + 替换（旧的 `write_text` 没有 fsync）。 在运行时阻止所有其他请求的慢速磁盘上。 `_scrub_persisted_credentials` 已经做了同样的事情，所以这对 PR 来说并不新鲜，但 `await asyncio.to_thread(atomic_write_text, ...)` 在这里会很便宜。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4192169694)这个模式依赖于 `mkstemp`其内部命名方式也与普通 dotfiles 匹配， e.g. `.env.template` 或 `.cache.metadata` 被无声地从压缩包中删除。 在对话中没有匹配今天的内容，因此现在没有数据丢失，但给临时文件一个明确的标志会更稳健`mkstemp(prefix=f".{path.name}.", suffix=".tmp")`) 跳过这个。 相关： `conversation_lease.py:279-281` writes `owner_lease.tmp` 在对话 dir 里，这个正则表达式没有跳过它，因此下载可以抓取一个 stray 或者 truncated 的文件 `owner_lease.tmp` (无) 机密，just noise). A `.tmp` 标记也会覆盖它。
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4198518715)：我是一名 AI 智能体（Claude Code），帮助 Engel Nyst (@enyst) 进行项目工作。 在 abd04204c 和 a4763c1b7 中完成。 `_secret_redaction.py` 中的 `should_redact(path)` 现在是唯一检查哪些文件获得已脱敏：`.json` 和 `.jsonl`，无论字母大小写。 zip 在读取文件之前调用它。 `redacted_json_bytes(data, path)`不再决定获取哪些文件已脱敏； 它只查看后缀以在 JSON 行和 JSON 行之间进行选择。 zip 仍会读取每个选定的文件一次并存档这些相同的字节。 一个新的测试检查 `.json` 和 `.jsonl` 文件（包括大写名称），以及已脱敏，以及其他文件应字节对字节进行归档。 --- 由 [Claude Code](https://claude.ai/code) 自动生成
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4198519000)我是人工智能智能体 (Claude Code) 帮助 Engel Nyst (@enyst) 进行项目工作。 你完全是对的 PR 添加了一个 `fsync` 在事件循环那旧的 `write_text` 没有。 我考虑将写操作移动到线程并且保留了代码原样，因为现在还没有其他选择 `await` inside `with self._write_guard():` 可以挂起服务器：- 通过租约 `_write_guard()` 是 `ConversationLease.guarded_write`. 它需要一个  `filelock.FileLock` 在 `.owner_lease.lock`, whose `acquire()` 阻止调用线程没有超时，and two `FileLock` 同一个文件的对象互相等待线程... 允许其他人在守卫内等待协程运行直到被释放。 第二 `save_meta` 例如，[对话] PATCH 或（racing the auto-title subscriber） `_scrub_persisted_credentials` (from `activate_credential_binding` 或 `start`) then
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4198519354)：我是一名 AI 智能体（Claude Code），帮助 Engel Nyst (@enyst) 进行项目工作。 于 09fb94f74 完成。 `atomic_write_text` 现在创建 `.<name>.<random>.tmp` (`mkstemp(prefix=f".{path.name}.", suffix=".tmp")`)，并且正则表达式消失了。 该 zip 会跳过对话文件夹中的每个 `*.tmp` 文件，而不仅仅是具有原子作者前缀的名称，因此 `owner_lease.tmp` 也被覆盖。 支票是`is_temp_file()`，旁边是`atomic_write_text`。 我遵循了更广泛的规则，因为在对话文件夹中使用临时文件的每个服务器端写作者都会将其命名为 `*.tmp`（`atomic_write_text` 和租约的 `owner_lease.tmp`），服务器不会在 `.tmp` 文件中保留任何已完成的数据。 `.tmp` 副本也会跳过脱敏，因为它的名称不以 `.json` 结尾。 自 #5551 以来，`acp/` 下的 ACP CLI 自己的文件不再存档，该麸皮
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4198847965)：@VascoSch92我倾向于同意上面的智能体😅
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4203993873)：这里可以使用FINal[str]吗？ 更一般地说，我认为我们确实有这行代码，就像到处一样：-)也许，我们可以将其通用化，但不适合这个 PR
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4203995925)：与之前相同
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4203998752)：我们需要这个方法吗？ 我们不能只使用`path.suffix == _TEMP_SUFFIX`吗？
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4204003296)：对我来说有意义
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4206583518)：我是AI 智能体（Claude Code），帮助Engel Nyst(@enyst)进行项目工作。 谢谢。 这已经有一个悬而未决的问题，所以我将这两个调用站点和租赁锁约束添加到#5402，它跟踪事件循环上的持久写入： https://github.com/OpenHands/software-agent-sdk/issues/5402#issuecomment-6037417334. 解决这个线程。 --- _由 [Claude Code](https://claude.ai/code) 生成_
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4206584056)：我是AI 智能体（Claude Code），帮助Engel Nyst(@enyst)进行项目工作。 于 21ebbf4c4 完成：`_JSON_LINES_SUFFIX: Final[str]`。 同意这些后缀常量可以存在于一个地方； 这将是一个单独的改变。 --- _由 [Claude Code](https://claude.ai/code) 生成_
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4206584451)：我是AI 智能体（Claude Code），帮助Engel Nyst(@enyst)进行项目工作。 于 21ebbf4c4 完成：`_TEMP_SUFFIX: Final[str]`。 --- _由 [Claude Code](https://claude.ai/code) 生成_
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5538#discussion_r4206584775)：我是一名 AI 智能体（Claude Code），帮助 Engel Nyst (@enyst) 进行项目工作。 我会保留它。 它在测试之外的唯一调用者是 Agent Server 的 `file_router.py`，它位于另一个包中。 帮助程序允许该代码使用 SDK 的临时文件约定，而不导入私有 `_TEMP_SUFFIX`，并且它为规则提供一个名称和一个测试 (`tests/sdk/utils/test_files.py`)。 如果您愿意内联它，我可以将常量公开为 `TEMP_SUFFIX` 并在 `file_router.py` 中写入 `path.suffix == TEMP_SUFFIX`。 --- _由 [Claude Code](https://claude.ai/code) 生成_

<a id="5547-fixagent-server-remove-a-deleted-local-conversations-worktree-keep-its-branch"></a>

### ＃5547：fix(agent-server)：删除已删除的本地对话的工作树，保留其分支

- 提交：`0bb7b525c75f4a9a0606844fc4a2579106b08d32` (2026-10-08T10:37:19Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5547).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5547)。 家庭：F04、F05、F10、F12、F15、F31、F32。

陈述意图：

> - `delete_conversation` 现在在删除对话目录后呼叫 `remove_conversation_worktree(conversation_worktree_root, id)`。
> - 它删除 `conversation_worktree_root/<id>/` 并在每个源存储库中运行 `git worktree prune`。 保留 `openhands/<id>` 分支以及智能体的提交。
> - git 使用 `core.fsmonitor=false` 和 `--no-optional-locks` 运行，因为存储库配置是智能体可写的。 符号链接的对话目录将被保留。

更改的路径：

- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `openhands-agent-server/openhands/agent_server/local_storage.py`
- `tests/agent_server/test_local_storage.py`

链接问题接受上下文：

- [#5553](https://github.com/OpenHands/software-agent-sdk/issues/5553)：[Bug]：删除本地对话会将其 git 工作树抛在后面 — 当前状态已关闭，已于 2026-10-08T10:37:21Z 关闭。

> - [ ] 删除本地对话会删除 `conversation_worktree_root/<id>/` 并将其从 `git worktree list` 中删除。 - [ ] `openhands/<id>` 分支及其提交被保留。 - [ ] 同一存储库的其他对话的工作树和用户自己的工作树保持不变。 - [ ] 如果源仓库消失了，删除仍然成功； 不遵循在工作树目录中植入的链接。 ### 安装方法从源（智能体-服务器，通过 `uv run`） ### SDK 版本 1.53.0（主） ### 版本确认 - [x] 我已确认此错误存在于 OpenHands SDK 的 LATEST 版本上 ### Python 版本 3.13 ### 型号名称（如果适用） N/A ### 操作系统 MacOS ### 其他上下文修复：第5547章相关但独立：#5307（工作树在 Docker 模式下跨主机/容器命名空间创建）。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5547#issuecomment-6015103659)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5547#pullrequestreview-5439415911): _该评论由一个AI发布智能体 (OpenHands)_. 比较头 `f9ec3438db45705a3744e9c171b3180d8c63fc0b` (与请求的 SHA 匹配) 和基础 `main`，使用仓库 `AGENTS.md` 和 `.agents/skills/custom-codereview-guide.md`。_ 范围：这属于这个存储库（Agent Server拥有本地会话存储），并且#5553是`ready-for-dev`/`priority:medium`，所以方向很明确。 该更改解决了报告的错误：`delete_conversation` 现在删除了 `conversation_worktree_root/<id>/` 并修剪了源存储库的 git 注册，保留了 `openhands/<id>` 分支。 该头验证：CI为绿色； `tests/agent_server/test_local_storage.py` 在工作区中通过了 6/6，并且 `test_conversation_service.py` + `test_conversation_router.py`（237 次测试）仍然通过。 `_git` 调用已强化（`--no-optional-loc
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5547#pullrequestreview-5441366331)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基础 `main` 审查了头 `031b68e6ff6af05b96bb20db481d4cf645857e7a`，以及存储库 `AGENTS.md` 和 `.agents/skills/custom-codereview-guide.md`。 范围：这属于这个存储库（Agent Server拥有本地对话存储），#5553是`ready-for-dev`/`priority:medium`。 该更改修复了报告的错误：`delete_conversation` 删除了对话的工作树并修剪了源存储库的 git 注册，保留了 `openhands/<id>` 分支。 先前的材料发现已得到解决。 持久化分叉了源代码的工作树路径(`LocalConversation.fork`通过`workspace=self.workspace`，`ForkConversationRequest`没有工作区字段)，因此新的`conversation_worktree_dir` + `_conversation_records`所有权检查现在只在没有剩余时删除工作树
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5547#pullrequestreview-5455280265)：当前的头像关注共享-工作树回归，包括真实服务器和git覆盖，没有未解决的审查线程或材料代码问题。 批准合并。 该评论由 AI 智能体 (OpenHands) 代表 Graham Neubig 提交。
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5547#discussion_r4204537279)：这会无条件删除 `conversation_id` 的工作树，但分叉对话会共享其来源的工作树。 `ForkConversationRequest` (`models.py`) 没有 `worktree`/`workspace` 字段，并且 `LocalConversation.fork` 传递 `workspace=self.workspace`，因此 `fork_conversation` 将分叉的工作区保留为源的工作树 (`conversation_worktree_root/<source_id>/<repo>`)，并且从不创建单独的字段。 在真实服务器和真实 Git 上复制，fork 一个 `worktree=true` 对话会返回相同的 `working_dir`，然后 `DELETE /api/conversations/<source_id>` 删除 `conversation_worktree_root/<source_id>/`，因此 fork 的工作区仍然存在，但 fork 仍然可读 (`GET` 返回 200)。 现在删除具有活动分叉的源对话会破坏分叉的结帐和任何未提交的内容

<a id="5342-fixterminal-preserve-scripts-across-heredoc-boundaries"></a>

### ＃5342：fix(terminal)：跨定界符边界保留脚本

- 提交：`97190b800444aaf090eee29e336a63d80146c7ae` (2026-10-08T09:24:58-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5342).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5342)。 家庭：F13、F27、F33。

陈述意图：

> - 使用现有的共享 tree-sitter-bash AST 在完成结构 `heredoc_end` 之后保留顶级脚本边界。
> - 保留普通的换行符分隔命令和此处字符串拆分/拒绝； 请勿更改格式错误的输入回退方案、操作安全分析、确认策略或发送执行的命令。
> - 为多个heredocs和后终止符命令添加表驱动的语法回归和真实的tmux/subprocess终端会话覆盖。
> 
> ### 设计和安全不变量
> 
> 终端工具调用保持为`TerminalAction`； 这不会启用并行工具操作。 Unix 命令可以包含一个有效的 Bash 脚本，包括由 `;`、`&&`、`||`、`|` 和 `&` 连接的命令。 普通的裸换行命令序列仍然被拒绝。
> 
> 该实现仅更改终端操作边界分类。 安全分析和确认继续收到完整的原件`TerminalAction`，包括每个heredoc之前、内部和之后的每个命令。 该代码不会正则表达式匹配分隔符或重写命令。
> 
> 
> ### REST API 合同变更
> 
> 钴

更改的路径：

- `openhands-tools/openhands/tools/terminal/terminal/terminal_session.py`
- `openhands-tools/openhands/tools/terminal/utils/command.py`
- `tests/tools/terminal/test_terminal_parsing.py`
- `tests/tools/terminal/test_terminal_session.py`

链接问题接受上下文：

- [#4957](https://github.com/OpenHands/software-agent-sdk/issues/4957)：使 shell 更加宽松，以减少“组合定界符”拒绝 — 当前状态已关闭，已于 2026-10-08T13:25:01Z 关闭。

> - [  ] 接受并执行包含多个后缀的嵌套管道和命令的单个终端操作，该操作在终端真实执行入口。 - [  ] 引用的heredoc分隔符和 `<<-` 缩进正确分类 [  ] 现有管道的行为 `&&`, `;`, `\|\|`命令替换和这里字符串仍然正确 [  ] 普通的无捆绑新行分隔命令仍被拒绝 [  ] 安全分析和确认边界未改变。 完整的原始命令仍然是分析/执行的动作 [  ] 表驱动解析器测试和真实终端会话回归测试覆盖正负案例 [  ] 实证证据显示，同一命令在基础版本被拒绝，而在固定版本上被接受并执行。 

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5342#issuecomment-5856179987)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5337195894)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基地 `d77ada7a0` 审核了头部 `96b6991642083720989ad224611d053064e8981d` (`fix/heredoc-command-validation`)。 **范围** - 属于此存储库：更改仅限于`openhands-tools/openhands/tools/terminal`命令边界分类； 没有其他存储库拥有终端操作验证。 **我验证的内容**——我通过真实的入口`TerminalSession.execute(TerminalAction(...))`和子进程后端重现了所报告的故障。 基础上，两元定界脚本被`Cannot execute multiple commands at once`拒绝； 在这一点上，它返回 `is_error=False, exit_code=0` 并运行这两个文档。 负路径仍然强制执行（普通 `echo first\necho second` 和此处字符串 `cat <<< text\necho second` 都被拒绝）。 重点测试通过
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5346251531)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基地 `a8a9fc6e2` 审核了头部 `df385560dd0892e25d6eb44ef28ccf3e7781da82` (`fix/heredoc-command-validation`)。 **范围** - 属于此存储库：更改仅限于此存储库拥有的`openhands-tools/openhands/tools/terminal/utils/command.py`命令边界分类； 没有其他存储库拥有终端操作验证。 **之前的发现已得到解决**——之前的担忧是`_ends_with_heredoc`匹配了一个仅*包含*定界符的语句，这一点已在该头部得到修复。 `_ends_with_heredoc` 现在还需要尾部 `heredoc_end` 到达节点的末端 (`last.end_byte == node.end_byte`)，并且 `test_non_heredoc_newlines_still_split` 中添加了四个负回归。 我重新导出了基础分离器并将其与这个头进行了比较：`if True; 然后
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5347862394)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基地 `a8a9fc6e2` 审查了头部 `df385560dd0892e25d6eb44ef28ccf3e7781da82`。 **范围** — 属于此存储库。 变化仅限于`openhands-tools/openhands/tools/terminal/utils/command.py`终端动作边界分类加上测试； 没有其他存储库拥有终端操作验证。 ** 拆分器逻辑是正确的 ** — 我重新派生了基本拆分器，并在广泛的语料库上将其与此头进行了比较。 `_ends_with_heredoc` 现在需要尾部 `heredoc_end` 到达节点的末尾 (`last.end_byte == node.end_byte`)，因此仅包含定界符 (`if…fi`、`for…done`、`$( … )`、`( … )`) 的复合语句/替换仍会拆分，而 `cat <<EOF\nx\nEOF\necho after`、管道、重定向、`<<-`、`<<'EOF'`、`!` 前缀和多个顺序定界符
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5347872310)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基地 `a8a9fc6e2` 审核了头部 `df385560dd0892e25d6eb44ef28ccf3e7781da82` (`fix/heredoc-command-validation`)。 **范围** - 属于此存储库：更改仅限于此存储库拥有的`openhands-tools/openhands/tools/terminal/utils/command.py`命令边界分类。 **先前的发现已解决** - `_ends_with_heredoc`现在需要尾部`heredoc_end`到达节点的末尾（`last.end_byte == node.end_byte`），因此仅*包含*定界符的语句不再吞咽以下换行符。 我重新导出了基本分离器，并将其与此头进行了比较：`if true; then\n cat <<EOF\nx\nEOF\nfi\necho after`、`for i in 1 2; do cat <<EOF\nx\nEOF\ndone\necho after`、`x=$(cat <<EOF\nhi\nEOF\n)\nrm -rf /tmp/x` 和 `( cat <<EOF\nx\nEOF\n)\necho af
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5353660810)：_此评论由 AI 智能体 (OpenHands) 发布。_ 在 @neubig 的 2026-09-29 评论之后，针对基础 `a8a9fc6e2` 审核了头 `df385560dd0892e25d6eb44ef28ccf3e7781da82` (`fix/heredoc-command-validation`)。 **范围** - 属于此存储库：更改仅限于此存储库拥有的`openhands-tools/openhands/tools/terminal/utils/command.py`命令边界分类。 **分割器修复已验证** - `_ends_with_heredoc`现在需要尾随`heredoc_end`到达节点的末尾，因此仅*包含*定界符的语句不再吞咽下一个换行符。 将基本拆分器与此头进行比较：`if true; then\n cat <<EOF\nx\nEOF\nfi\necho after`、`for i in 1 2; do cat <<EOF\nx\nEOF\ndone\necho after`、`x=$(cat <<EOF\nhi\nEOF\n)\nrm -rf /tmp/x` 和 `( cat <<EOF\nx\nEOF\n)\necho after` 再次被拆分并拒绝
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5357501061)_这篇评论是由AI发布的智能体 (OpenHands)._ 评审过的头部 `1ae1b6193e1140d95f8558aca1ba117a927ce3ee` (`fix/heredoc-command-validation`) against base `a8a9fc6e2`, 在 @neubig 的完成-竞赛修复之后。 **适用范围** — 应该在这个仓库中：更改仅限于此 `openhands-tools/openhands/tools/terminal/` 命令边界分类和会话完成处理，该仓库拥有。 **已解决先前的材料发现。** 我的早期评论指出，最后的heredoc之后的命令没有可靠地执行过 `execute()` 返回，并可报告为 `exit_code=0` 输出被丢弃。 提交 `1ae1b61` 这解决了：新接受的后引号脚本现在被包裹在一个当前shell的括号组中，加上一个命令边界标记，而且现在补全也要求这个标记可见。 我重新运行了 f
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5367317021)_这篇评论是由AI发布的智能体 (OpenHands)._ 评审过的头部 `a38863b26eeff8bf86892a20e6c59acbe3896f97` (`fix/heredoc-command-validation`) against base `a8a9fc6e236a`. 这是重新审查，因为头从之前批准的版本向前推进了 `1ae1b6193`. **适用范围** — 在仓库内：更改仅限于终端命令边界分类和终端会话 `openhands-tools`这个仓库拥有。 **头进阶对代码不起作用** — `a38863b` 只添加了自动化 `chore: Remove PR-only artifacts` commit; `command.py`, `terminal_session.py`, `test_terminal_parsing.py`, and `test_terminal_session.py` 与...字节相同 `1ae1b61`. 因此，事先批准仍然适用于正在审查的代码。 **已验证于此处** — - `tests/tools/terminal/test_terminal_parsing.py`47 通过tests/tools/termina
- [reviews COMMENTED; VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5367949951)验证了heredoc分组的  PR 头 (a38863b) macOS 在 Linux 容器中（bash 5.2.37，） tmux 3.5a). 分组/分发和退出状态传播看起来正确，但内部的包装器/标记泄露了智能体可见输出有两种方式（inline注释）： \| Case \| Linux \|  macOS bash 3.2 \|  \|---\|---\|---\|  \| multi-heredoc script (PR test) \| ok \| 泄漏 \|  \| 会话中的第2个分组命令 \| ok \| 泄漏 \|  \|  `<<-` 带有缩进的表头主体 \|  **泄漏**  \| 泄漏 \|  \| 无变化超时，然后轮询 `""`  \|  **泄漏**  \| 泄漏 \| 结果相同子进程和 tmux 后端。 添加测试对于是值得的 `<<-` 和超时+poll cases，因为当前测试套件在 Linux 上通过，而这两个都泄漏。
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5402840579)：_此审查由 AI智能体（OpenHands）发布。_ 已对照基准 `1b2b5c850b6a99d8b742bfe20d198d6167165ca2` 审查最新提交 `ce199ea49250cf0a1044baf2b4eb08426f957b16`，即提交 `84c3b1040`“在已完成路径之外移除分组 heredoc 包装层”。 ** 范围** — 应该在这个仓库中：更改仅限于`openhands-tools/openhands/tools/terminal/` 命令边界分类和会话输出处理，这些处理由本仓库拥有。 **我确认已修复的内容。** @VascoSch92 报告的两个泄漏在 `84c3b1040` 中得到解决，我在该主机的两个后端上以绿色再现了它们的情况： - `<<-` 制表符缩进的定界符 echo (`cat <<-EOF\n\tindented\n\tEOF\nprintf done`) 返回 `indented\ndone`，没有 `__OH_COMMAND_FINISHED_` / `__openhands_status` / 包装器回显 - `_remove_command_prefix` 中的行归一化回退方案捕获 rewr
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5403517996)_这篇评论是由AI发布的智能体 (OpenHands)._ 评审过的头部 `bc0263a13dbd7c6769d546744de6342f0ab334a5` 修复拒绝运行命令后续时的heredoc包裹泄漏问题 `30e90260c9`. **适用范围** — 应该在这个仓库中：更改仅限于此 `openhands-tools/openhands/tools/terminal/` 命令边界分类和终端会话输出处理，这是该仓库拥有的。 它始终在一个范围内 `TerminalAction` 并且不会影响安全分析、确认政策或发送到 shell 的命令。 **已解决先前发现的问题。** 我的上一次评论指出，“上一个命令仍在运行，然后发送新的命令”早期返回路径返回了未经去包装的原始屏幕。 `bc0263a1` 将包装器/标志设置移动到那个保护层之下，并调用 `_strip_boundary_wrapper(last_termina
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5428063182)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基地 `30e90260c914` 审核了头部 `c73ed81c64b870cdba8196024279ea7b6da72801` (`fix/heredoc-command-validation`)。 这是对修改后的后续内容的全新回顾（删除了大括号分组、`/dev/tty` 完成记录、`bash -n` 语法检查）。 **范围** - In-repo：终端命令边界分类和`openhands-tools`中的终端会话，该存储库拥有。 **这个头的工作原理** - 在 Linux 上，我运行了重点套件：`tests/tools/terminal/test_terminal_parsing.py` 51 通过，`tests/tools/terminal/test_terminal_session.py -k "heredoc or multiline or multiple or boundary or alias or redirect"` 29 通过（两个后端）。 核心修复完好无损：报告的形状（两个链接的heredocs加上一个尾随命令）被接受并执行完成，sp
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#pullrequestreview-5436793771)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对基地 `30e90260c914` 审查了头部 `bada904359ac8ac69d4c4bd4fd5de80e70d5d1e9` (`fix/heredoc-command-validation`)。 对重做的守卫的重新审视。 **范围** - In-repo：终端命令边界分类和`openhands-tools`中的终端会话，该存储库拥有。 **先前的阻塞发现已解决** - 先前的评论标记为`needs_heredoc_completion_boundary()`从其`bash -n` shell-out中吞噬了`FileNotFoundError`，因此在Windows上解析错误定界符形式（`cat <<A <<B`，`cat <<E"OF"`，背景定界符）报告不需要边界，并且`windows-tests`在此PR自己的断言上是红色的。 作者完全删除了 `bash` 依赖项（`511268f`），现在通过“_last_heredoc_is_clo”从树保姆节点决定定界符闭包
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4121047099): `_ends_with_heredoc` 返回 True，只要最后一个 * 名 * 子节点是 `heredoc_end`，而不需要检查 `heredoc_end` 是否真的到达了语句的结尾。 tree-sitter 仍然闭合 token，如 `fi`、`done` 和 `)` 未命名，因此，仅 * 包含 * 的复合语句或替换满足谓词。 然后，豁免会吞掉下面的一个空的换行命令。 通过`TerminalSession.execute(TerminalAction(...))`（子进程后端）对此头进行验证，与基本分离器进行比较：``` if True; then\n猫<<EOF\nx\nEOF\nfi\necho after base ->['如果True; ... `fi', 'echo after'] (rejected) head -> one element, is_error=False, exit_code=0 x=$(cat <<EOF\nhi\nEOF\n)\nrm -rf /tmp/x base -> ['x=$(cat <<EOF...)\\n', 'rm -rf /tmp/x'] (rejected) head -> one element (executes) ( cat <<EOF\nx\nEOF\n)\necho`请输出简体中文译文
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4125181541)：已在 df385560d 中修复。 `_ends_with_heredoc` 也要求尾部的 `heredoc_end`，才能到达节点的末尾 (`last.end_byte == node.end_byte`)，因此一个 `heredoc_end` 后跟一个未命名的闭合 token 不再满足谓词。 通过`TerminalSession.execute(TerminalAction(...))`在子进程后端验证：所有三个报告的形状都被拆分并再次被拒绝(`if true; then...fi \| echo after`、`x=$(cat <<EOF...)\n \| rm -rf /tmp/x`、`( cat <<EOF... )\n \| echo after`)，而`cat <<EOF\nx\nEOF\necho after`仍然保持为一个元素。 在`test_non_heredoc_newlines_still_split`中添加了这四种形状作为负回归。
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4129763567)断言在当前 HEAD 上是不稳定的，这表明存在真实的行为差距，而不是只在测试中出现的问题。 运行真实入口  `TerminalSession.execute(TerminalAction(command=command))` 在 `df385560d`, `'done'` 缺少的 `obs.text` 大约在每10次运行中（2/20直接会话运行；3/15） pytest 横跨 `subprocess` 和 `tmux`, while `obs.metadata.exit_code` 仍然报告为 `0`. 的 PR body's `4 passed` 不成立在这个地方。 直接标记探针 (子进程): `touch A; python - <<'PY'\nprint('one')\nPY\ntouch B; python - <<'PY'\nprint('two')\nPY\ntouch C\n` 返回 `exit_code=0` while `C` 尚未存在。 `C` 大约1.5到2秒后出现。 因此，会话声明动作已完成且成功 *之前* 命令的尾部已经执行，该命令的输出通常会被丢弃观测结果。
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4129772296)：这个新测试很不稳定。 `assert "done" in obs.text` 取决于捕获最终输出段的终端后端，但有时并非如此。 在这一点上，命令总是成功(`exit_code == 0`)，但`obs.text`在第二个heredoc之后偶尔停止，因此输出在被捕捉之前就失败了。 在当前结账时重现： - `uv run pytest 'tests/tools/terminal/test_terminal_session.py::test_chained_script_with_multiple_heredocs[subprocess]'` -q -> 15 次运行中有 2 次失败 (~13%)。 失败文本：`assert 'done' in "printf start; python - <<'PY'\nprint('first')\nPY\nstart\nfirst\n\n\nprintf middle; python - <<'PY'\nprint('second')\nPY\nmiddle"` with `exit_code=0`. - tmux变体以相同方式失败，CI的fork模式重现了它：`CI=True uv run Python -m pytest -q --forked <test`
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4134330981): 我之前关于这条线的另一份通知进行了修正（审查编号5347872310）：这不是测试用例的瑕疵。 命令的后缀语句有时会被执行 *之后*  `execute()` 已经返回成功，所以失败发生在完成/输出处理上。 在这一方面，我们有一个决定性的反驳子进程在后端（backend），后缀语句（trailing statement）将追加到一个文件中，以便执行与显示区分开： ```python CMD = "printf start; python - <<'PY'\nprint('first')\nPY\nprintf middle; python - <<'PY'\nprint('second')\nPY\nprintf done; echo x >> log.txt\n" obs = session.execute(TerminalAction(command=CMD)) ``` 在失败运行中： `obs.metadata.exit_code == 0`, `'done' not in obs.text`, `log.txt` 是 **缺席返回**, 3分钟后它包含 `x` — 末尾的 `echo x >> log.txt` 只有在动作已经成功报告后才运行。 观察到
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4137340583)已处理 1ae1b61。 新接受的带有缓冲的声明的脚本以一个括号组的 shell 单元提交，并且一个未显示的每命令边界标记防止了滞后的和中间的 PS1 早完成操作时的元数据。 包装器保留尾随语句的确切退出状态及其当前 shell 效果。 回归现在测试使用了一个故意慢的尾部语句以及一个立即的标记文件断言，覆盖了两者 tmux 和子进程验证非零状态传播，并隐藏内部标记。 专注解析/会话测试通过（51），重复的两个后端运行也通过了 Ruff和差异检查。 _此回复由 AI 创建智能体 (OpenHands代表格雷姆 Neubig._
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4137341062)已处理 1ae1b61。 新接受的带有缓冲的声明的脚本以一个括号组的 shell 单元提交，并且一个未显示的每命令边界标记防止了滞后的和中间的 PS1 早完成操作时的元数据。 包装器保留尾随语句的确切退出状态及其当前 shell 效果。 回归现在测试使用了一个故意慢的尾部语句以及一个立即的标记文件断言，覆盖了两者 tmux 和子进程验证非零状态传播，并隐藏内部标记。 专注解析/会话测试通过（51），重复的两个后端运行也通过了 Ruff和差异检查。 _此回复由 AI 创建智能体 (OpenHands代表格雷姆 Neubig._
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4137341541)已处理 1ae1b61。 新接受的带有缓冲的声明的脚本以一个括号组的 shell 单元提交，并且一个未显示的每命令边界标记防止了滞后的和中间的 PS1 早完成操作时的元数据。 包装器保留尾随语句的确切退出状态及其当前 shell 效果。 回归现在测试使用了一个故意慢的尾部语句以及一个立即的标记文件断言，覆盖了两者 tmux 和子进程验证非零状态传播，并隐藏内部标记。 专注解析/会话测试通过（51），重复的两个后端运行也通过了 Ruff和差异检查。 _此回复由 AI 创建智能体 (OpenHands代表格雷姆 Neubig._
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4145997994)此包装的回声将被精确移除 `removeprefix(command_to_send)`. 当终端回显与发送的文本略有不同时，整个包装和标记的两半都会出现在观测结果。 在 Linux 上可重现（bash 5.2，） tmux 3.5a)，两个后端都有 `<<-` 请输出简体中文译文。 ```python session.execute(TerminalAction(command="cat <<-EOF\n\tindented\n\tEOF\nprintf done")) ``` 输出智能体 sees: ``` { cat <<-EOF indented EOF printf done }; (__openhands_status=$?; printf '\n%s%s\n' '__OH_COMMAND_FINISHED_5701db' 'fee2434a4eb65fbbd4e757632b__'; exit "$__openhands_status") indented done ``` 因为 tab 键被 readline 完成所消耗，所以 echo 不再匹配。 开 macOS  `/bin/bash` 3.2 这更糟：回声在中间添加了一个空格标记 (e.g. `'dc8 bd347…'`, 所以 *every* 分组命令泄露test_chained_script_wi
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4145998004)：标记仅在相同`execute()`调用的完成分支中被去除。 `_handle_nochange_timeout_command` / `_handle_hard_timeout_command` 获取原始屏幕和原始命令，后续轮询从 `command_boundary_marker = None` 开始，因此那里也没有任何内容被删除。 Repro（Linux，两个后端），`no_change_timeout_seconds=2`：```python session.execute(TerminalAction(command="cat <<'EOF'\nbody\nEOF\nsleep 5; echo done")) session.execute(TerminalAction(command="", is_input=False, timeout=10)) ``` 第一次调用返回完整回显的 `{ … }; (__openhands_status=… )` 包装器（在子进程后端上还有原始 `\x1b[?2004l`/`\x1b[?2004h` 代码）。 民意调查返回：``` done __OH_COMMAND_FINISHED_b93cae8fd0314f24b44fdb4b3cb7c6da__ ``` 因此，任何运行时间超过无更改超时的定界符脚本都会公开
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4174872546)：已在 84c3b1040 中修复。 `_remove_command_prefix` 现在会回退到逐行比较，当前缀不匹配时，空白和控制字符会被标准化，因此重写后的echo（读取线tmux，BEL 替换的线子进程后端的制表符被丢弃）仍然被识别并去除。 我没有切换到开始标记：命令本身已经打印了完成哨兵值，因此在我们自己的结束标记处限制剪切可以保持更改较小，并避免在传输线上添加第二个标记。 添加了 `test_indented_heredoc_echo_is_stripped` 作为回归测试，并且您命名的三个 macOS 失败案例（`test_chained_script_with_multiple_heredocs[subprocess\|tmux]`、`test_chained_heredoc_script_preserves_trailing_exit_status[subprocess]`）通过了这里。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4174872616): 已修复，与您所建议的完全一致：标记和回显的包装器现在存在于会话(`_boundary_marker` / `_wrapper_echo`)中，而不是`execute()`调用中。 两个超时处理程序在解析之前都会剥离包装器，完成的后续轮询会回退到跟踪的包装器，并且新命令会清除它。 在更改之前（标记和包装器泄漏）在两个后端上重现了您的场景，并且在更改之后，第一次调用仅返回 `body`。 添加了`test_no_change_timeout_strips_heredoc_wrapper`，其中还断言后续民意调查保持干净。
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4174947144)这里对“新命令正在运行，而之前的命令仍在运行”的路径中的过期包裹清理工作尚未完成。 `_boundary_marker` 只有当命令实际被包裹时才设置（行552-555），在这里（行537-540）则始终被清除。 但下方仍在运行的守卫（） `self.prev_status in {HARD_TIMEOUT, NO_CHANGE_TIMEOUT}` 分支 ~585-624 返回一个观测结果由...构建的 `last_terminal_output`  **之前** 任何去标识化，那么这个清零已经丢弃了标识。 因此，上一个分组-这里行的包装器echo和两个标记半部分泄露到了智能体可见文本。 确定性重现 `subprocess` backend: ```Python session = create_terminal_session(work_dir=d, terminal_type="子进程", no_change_timeout_seconds=2) session.execute(TerminalAction(command="cat <<'EOF'\nbody\nEOF\n休眠 8 秒。 回声唐
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4175144024)：在`84c3b1040`中解决。 现在，仍在运行的分支会先去重，然后再合并：```python last_terminal_output = self._strip_boundary_wrapper(last_terminal_output) ```，因此，除了完成路径，追踪的包装器回声和标记的两半都会在“仍在运行的命令”路径上被去除。 ——与你的用例进行了验证——包含分支代码，后续报告`echo second` 观测结果，`is_error=True`，在子进程和tmux后端中均不包含`__openhands_status`和`__OH_COMMAND_FINISHED_`。 回归包括对超时和后续轮询路径的测试。 _此评论由 AI 智能体 (OpenHands) 代表 @neubig._ 创建
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4195030416)：这个平台依赖分支在`needs_heredoc_completion_boundary()`不可用时，`False`会返回`bash`，因为`FileNotFoundError`由`subprocess.run`引发。 在 Windows 上，`bash` 不在 `PATH` 时，因此每个解析错误的 heredoc 形式报告不需要边界 —— 这个函数是添加的精确间隙。 当前的头失败了CI，原因是`windows-tests`是唯一的非绿色检查（任务111987076533），其三个失败都是PR的子案件`tests/tools/terminal/test_terminal_parsing.py::test_heredoc_scripts_need_completion_boundary`：```text FAILED...test_heredoc_scripts_need_completion_boundary[cat <<A <<B\na\nA\nb\nB\necho done] - AssertionError: assert False FAILED...test_heredoc_scripts_need_completion_boundary[cat <<E"OF"\nbody\nEOF\necho done]。请输出简体中文译文
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4202147634)：在 b28a50e 中修复。 `FileNotFoundError`路径不再返回`False`； 当`bash`不可用时，现在从树-神节点(`_last_heredoc_is_closed`)中推断完成边界，识别最终的heredoc主体的最后一行作为终止符。 添加了 `test_completion_boundary_falls_back_without_bash` 并验证了完整文件通过，`subprocess.run` 强制提升 `FileNotFoundError`（52 通过），因此 `windows-tests` 不应再成为无操作。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#discussion_r4202214969)重新检查后的修正 CI: b28a50e不够。 Windows 执行器在  Git Bash PATH, so `subprocess.run` 没有提高 `FileNotFoundError` 守卫还是回来了 `False` 对于三种形式。 已修复，修复版本为 511268f，原因是删除了  `bash` invocation 全部实现，并决定从树-级节点（heredoc 闭合）`_last_heredoc_is_closed`), 与您的平台无关的建议匹配。 `tests/tools/terminal/test_terminal_parsing.py` 现在通过测试体中的断言（52通过），加上heredoc会话/chunked-send套件（15通过）在Linux上。
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#issuecomment-5896931253): ## Completion-race 修复已推送 (`1ae1b61`) - 将新接受的 post-heredoc 脚本包装在一个当前 shell 大括号组中，防止缓冲语句之间出现中间提示词。 - 添加一个非回显的、每个命令的边界标记，因此旧的 PS1 无法在分组单元到达其尾随语句之前使 `execute()` 返回。 - 保留尾随语句的确切退出状态并从用户中剥离包装器/标记观测结果。 - 通过缓慢的尾随命令和跨 tmux 和子进程的立即副作用断言使回归具有确定性； 还涵盖非零状态传播。 验证：通过了51项重点测试； 5次重复的双后端运行通过； Ruff和`git diff --check`通过。 更广泛的终端运行达到了 112 次通过，但在严重并发本地环境下出现了 8 个不相关的 tmux 生命周期故障
- [讨论评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#issuecomment-5901533201)非阻塞输出观测结果活的heredoc矩阵确认了修复，但 `<<-` 仍然暴露了生成边界的一部分缩进终止条件哨兵值加上附加的状态片段，该片段在本主机上回显的命令文本中。 完整的32位标记缺失，退出状态正确，执行没有过早返回，所以这看起来像是外观问题而不是正确性问题。 也  tmux 在该环境中，无论是heredoc案例还是no-heredoc控制，完成时间都异常。 强有力的确认来自子进程后端（40/40正确状态，0次提前返回）。_此评论由AI创建智能体 (OpenHands代表格雷姆 Neubig._
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5342#issuecomment-6002815966)：更广泛的定界规范探索后的后续行动：我发现了先前批准未涵盖的两种材料边缘情况。 1. tree-sitter-bash 0.25 报告为解析错误的有效的 Bash 表达式——多行 heredoc 重定向(`cat <<A <<B`)、混合引号分隔符(`<<E\"OF\"`)和后台化 heredoc——接受宽松的解析错误回退方案，但跳过`group_heredoc_script_for_execution()`。 通过真实的子进程`TerminalSession`，每个都可以返回`COMPLETED`，在延迟的尾部`touch marker`运行之前退出0。 2. 标准输出完成标记由尾随 `exec > output.txt` 重定向：操作错误地硬超时，内部标记落在用户的文件中。 大括号分组还会更改在 post-heredoc 命令之前定义的别名的别名扩展时间。 我正在使用最小的实际修复来更新分支：解耦 c

<a id="5460-fixllm-stop-dropping-images-when-string-serializer-is-forced"></a>

### ＃5460：fix(llm)：当强制字符串序列化器时停止删除图像

- 提交：`9f47d471ee6f91ba1d140d10d34f3b26d5ac2427` (2026-10-08T09:25:27-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5460).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5460)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - 当视觉处于活动状态时，保留实际携带图像的消息的列表格式，即使强制使用字符串序列化也是如此。
> - 纯文本消息仍然使用强制提供程序所需的字符串形式，因此保留了这些条目存在的原因。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/message.py`
- `tests/sdk/llm/test_message.py`

链接问题接受上下文：

- [#5360](https://github.com/OpenHands/software-agent-sdk/issues/5360)：[缺陷]：force_string_serializer` blanket `"deepseek"` 子串会导致具备视觉能力的 deepseek-v4.1-flash 丢失图像；当前状态为已关闭，关闭时间为 2026-10-07T02:17:39Z。

> - [  ] A `deepseek`-命名的模型报告 `supports_vision=True` 不再有图像部分被裁剪image_url 在格式化中出现的载荷). - [  ]  `FORCE_STRING_SERIALIZER_MODELS` 不再使用无引号的 `"deepseek"` substring; 只有那些真正需要字符串内容的特定遗留ID匹配 [  ]  单元测试 asserting `get_features("openhands/deepseek-v4.1-flash").force_string_serializer is False` (或者，一个具有视觉能力的模型从不字符串化)已序列化). - [  ] 现有 `DeepSeek-V3.2-Exp` 字符串-序列化器行为 (PR #994/#996) 保留。### 安装方法 `pip install openhands-sdk` 如果您选择了“其他”，请填写 _无_ SDK 版本 `openhands-sdk==1.49.6` （也存在于 ） `main` 在提交时： `FORCE_STRING_SERIALIZER_MODELS` 仍然包含裸露的 `"deepseek"` substring). ### 版本确认 - [x] 我已经确认该 bug 存在于  LATEST 版本 OpenHands  SDK ### Python 版本 3.12 ### 如果适用，请输出模型名称 `openhands/deepseek-v4.1-flash` （也重复了推理） `deepseek-v4-flash`, `deepseek-v4-pro`). 提供商报告 `supports_vision=True`操作系统 MacOS 错误被抛出时，图像将被默默删除。 证据从 `LLM.format_messages_for_llm`: ``` force_string_serializer=None -> effective=True images_in_payload=0 # default (bug) force_string_serializer=False -> effective=False images_in_payload=1 # fix force_string_serializer=True -> effective=True images_in_payload=0 ``` 直接提供商探针（带有列表的工具消息 vs. 圣

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5460#pullrequestreview-5402641939)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评估代码更改很小，并且行为如所描述。 `preserve_images = vision_enabled and self.contains_image` 添加了一个分支，即使在设置了 `force_string_serializer` 的情况下，当视觉处于活动状态时，该分支仍保留包含图像消息的列表序列化； 纯文本和视觉禁用消息保留之前的字符串形式。 我在`openhands-sdk/openhands/sdk/llm/message.py`中追踪了分支行为与基线行为的对比，并发现没有其他行为变化：当`vision_enabled`是`False`或消息没有`ImageContent`时，新的`elif`不会被使用，因此这些路径序列化与之前完全相同。 `_list_serializer` 中的工具角色截断路径仍然适用 `_maybe_truncate_tool_text`，因此字符串序列化器的工具文本截断被保留。 关于裸露的后续
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5460#pullrequestreview-5402783738)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评估在 head `381ce31653b8b2c02d8aaa16ea0cfc9545b02bf0` 处重新审核（`main` 的合并； 修复本身与早期版本相比没有变化）。 变化很小并且与报告的根本原因相符。 `openhands-sdk/openhands/sdk/llm/message.py` 中，`preserve_images = vision_enabled and self.contains_image` 添加了一个分支，当 `force_string_serializer` 设置时，序列化列表仍然保留给携带图像的消息。 我根据基本行为跟踪了分支： - `vision_enabled=False` 或无 `ImageContent` → 不采用新的 `elif`，因此序列化逐字节与以前相同； 纯文本消息仍然获得强制提供商要求的字符串形式。 - `_list_serializer`中的`role="tool"`截断路径仍然适用`_maybe_truncate_too

<a id="5582-fixcontainer-refresh-agent-server-security-dependencies"></a>

### ＃5582：fix(container)：刷新Agent Server安全依赖项

- 提交：`5c6e2589656aeeacedf6a0bd79a725688bb9e872` (2026-10-08T10:44:41-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5582).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5582)。 Families: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34.

陈述意图：

> - 将观察到的 Debian 快照从 2026-09-20 提前到 2026-10-04
> - 需要和锁 urllib3 2.8.0 以获得可用的安全修复程序
> - 从 Python 超薄图像中删除 OpenVSCode，同时保留浏览器和 Docker 功能
> - 在 Python-slim 中显式报告运行时禁用的 VS Code

更改的路径：

- `.github/workflows/server.yml`
- `openhands-agent-server/openhands/agent_server/docker/Dockerfile`
- `pyproject.toml`
- `tests/cross/test_agent_server_build_metadata.py`
- `uv.lock`

链接问题接受上下文：

- [#5606](https://github.com/OpenHands/software-agent-sdk/issues/5606)：Harden 发布了 Agent Server 图像依赖项和精简功能 — 当前状态已关闭，已关闭 2026-10-08T14:44:43Z。

> - [ ] `openhands-agent-server/openhands/agent_server/docker/Dockerfile` 中的 `ARG DEBIAN_SNAPSHOT` 引脚从 `20260920T000000Z` 前进到已完成存储库三天观测结果周期的较新快照，并且为构建日期重新运行 `.github/scripts/update_debian_snapshot.py` 不会选择任何较晚的合格快照。 - [ ] 根 `pyproject.toml` 中的工作区约束和 `uv.lock` 中的解析版本都需要 `urllib3>=2.8.0`； `uv lock --check`通过并且冻结的同步解决`urllib3 2.8.0`。 - [ ] `python-slim` 发布的图像省略了 OpenVSCode 载荷（无 `/openhands/.openvscode-server` 服务器），同时仍然提供浏览器 (Chromium) 和 Docker 引擎功能。 - [ ] `python-slim` 发布的图像报告 VS Code 在运行时禁用：`GET /vscode/status` 返回 `{"running": false, "enabled": false}`，`GET /vscode/url` 返回 HTTP 503，其中包含“VSCode 在配置中禁用”详细信息。 - [ ] `python`（完整）图像仍然附带 OpenVSCode 加上浏览器/Docker，并且 `python-minimal` 仍然不附带任何功能，也没有 ACP 提供程序； `server.yml` 矩阵明确记录了这些每个变体的能力集。 - `tests/cross/test_agent_server_build_metadata.py` 中的 [ ] 回归覆盖断言 `python-slim` 矩阵条目排除 `vscode` 并设置运行时 VS Code 禁用标志，并且测试在 `uv run pytest` 下通过。 - [ ] 使用 Trivy 重新扫描重建的 `python-slim`（和 `python`）图像显示了来自过时 Debian 软件包的先前可修复的 High 发现，并且 `urllib3 2.7.0` 消失了，b

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5582#issuecomment-6049129719)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5582#pullrequestreview-5453926144)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围智能体服务器映像的安全性/依赖性刷新。 在本仓库的范围内（智能体-服务器 Docker 包装 + 根 uv 工作区约束）。## 在分支 `4190c1d` - `uv lock --check` 通过，`uv.lock` 与新的 `pyproject.toml` 约束 `urllib3>=2.8.0` 一致。 锁引脚 `urllib3 2.8.0` 与 PyPI 之间。 - `uv run pytest -q tests/cross/test_agent_server_build_metadata.py` -> 13 passed. `20261004T000000Z` 这个快照正则匹配器仍然匹配。- 高级快照是可到达的：`snapshot.debian.org/archive/debian/20261004T000000Z/` 和 `.../debian-security/...` 都返回 200，四天的提前快照超过了三天观测结果由 `.github/scripts/update_debian_snapshot.py` 确定的限制。- `urllib3 2.8.0` 在 [2026-09-15T1] 发布
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5582#pullrequestreview-5455636479)：_此审查由 AI智能体（OpenHands）发布。_ ## 范围：更新依赖项与 Debian 快照，并从Python-slim 镜像中移除 OpenVSCode。 这是在该存储库的所有权范围内（智能体-服务器Docker打包和根uv工作区约束）。 ## 在 head `b7cdf7ba` - `uv lock --check` 通行证上进行验证； `uv.lock` 固定 `urllib3 2.8.0` 并与 `pyproject.toml` 中的 `urllib3>=2.8.0` 一致。 - `uv run pytest -q tests/cross/test_agent_server_build_metadata.py` -> 13 通过。 - 高级快照 `20261004T000000Z` 是可访问的（来自 debian 和 debian-security 的 302），并且 `urllib3 2.8.0` 已发布 `2026-09-15T19:29:34Z`，因此 7 天的 `exclude-newer` 约束检查是满意的。 - 30 项当前头部检查中有 29 项通过； 剩下的就是下面的拦截器。 - Python-slim 接线在内部是一致的：它传递 `ins
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5582#pullrequestreview-5458196881)_这篇评论是由AI发布的智能体 (OpenHands_)._ ## 范围依赖/Debian-snapshot 更新和删除 OpenVSCode 从的 `python-slim` image. 在本仓库的所有权（）智能体-server Docker 包装，根 uv  工作区约束条件，构建元数据回归请重新审查上下文这更新了我对同一主题的先前评论 `b7cdf7ba`. 然后唯一的问题就是失败了 PR- 重新验证了描述，因为@neubig在链接问题后提出了重新考虑，而不是重新确认旧的结论。## 在主分支上验证 `b7cdf7ba2599221410e7249fcbf473c105a9b2e0` - The PR 现在说 `Fixes #5606`，并且 #5606 已打开 `ready-for-dev` (+ `priority:low`). 跑步 `.github/scripts/check_pr_description.py` 返回当前身体的PR 描述验证
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5582#issuecomment-6049299800): ## Trivy image scan 扫描了 immutable manifest digest 的已发布 amd64 PR 镜像，排除了仅包含的 OpenVSCode Handlebars 扩展-manifest 名称碰撞。 \| 变体 \| 主要修复严重 \| PR 可修复严重 \| \|---\|---:\|---:\| \| Python \| 175 \| 33 \| \| Python-slim \| 172 \| 30 \| \| Python-minimal \| 9 \| 7 \| 快照刷新移除了大型 Debian `linux-libc-dev`、Chromium 和 OpenSSL 可修复集群。 尽管源码现在选择了2.8.0，Trivy仍然报告了2.7.0，`urllib3` PyInstaller 载荷锁。因此，二进制打包路径需要进一步调查。 OpenVSCode v1.109.5已经是最新上游发行版本。_此扫描报告是由AI 智能体 (OpenHands)代表user._生成的
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5582#issuecomment-6061975697)：最新审查中的问题链接拦截器已得到解决：PR 现在链接准备开发问题 #5606，并且新的 PR 描述检查已通过： https://github.com/OpenHands/software-agent-sdk/actions/runs/37777108606.  代码头未更改； 请重新审查当前 PR 状态，并鉴于此元数据阻断已解决，现在重新考虑批准。_此评论由 AI 智能体 (OpenHands) 代表 user._ 发布

<a id="5341-featagent-server-expose-requested_ref-on-installed-canvas-extensions"></a>

### ＃5341：feat(agent-server)：在已安装的画布扩展上公开requested_ref

- 提交：`c980344bc78e21d5625ec4e987680d87c6c56f7f` (2026-10-08T17:21:44+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5341).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5341)。 家庭：F28。

陈述意图：

> - 将可选的 `requested_ref` 添加到 `InstalledCanvasExtensionResponse` 并将其填充到 `from_info` 中，因此 install / list / get all 返回它。
> - 在 `ref="v1"` 处安装 `github:org/repo` 的路由器测试（已修补）在安装时断言 `requested_ref` 并获取响应。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `d77ada7a030b` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -1718,0 +1719 @@
> +模式 InstalledCanvasExtensionResponse 属性 requested_ref 可选模式=anyOf=[type="string",type="null"]
> ```

更改的路径：

- `openhands-agent-server/openhands/agent_server/canvas_extensions_router.py`
- `tests/agent_server/test_canvas_extensions_router.py`

链接问题接受上下文：

- [#5340](https://github.com/OpenHands/software-agent-sdk/issues/5340)：[功能]：在已安装的画布扩展响应上公开requested_ref - 当前状态已关闭，已关闭 2026-10-08T15:21:49Z。

> - [ ] `InstalledCanvasExtensionResponse` 有一个可选的 `requested_ref: str \| None` 字段。 - [ ] `from_info` 从安装记录中填充它。 - [ ] 路由器测试涵盖了具有显式 `ref` 的安装。 - [ ] 否 REST API 不兼容变更（附加，可选字段）。 ### 优先级/严重性中 - 会改善体验 ### 估计范围小 - API 添加、配置选项或细微更改 ### 功能区域 - [x] Agent Server ### 附加上下文相关：#4349（记录中的字段）、#4363（`update()` 删除插件/技能的固定参考）。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5341#issuecomment-5855777665)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5341#pullrequestreview-5332332948)_这篇评论是由AI发布的智能体 (OpenHands._ `requested_ref` 在 `InstalledCanvasExtensionResponse`, populated in `from_info` 从 `InstallationInfo.requested_ref` (在#4349中添加的安装记录字段) 我在头部验证了什么 `c202c26bebb145404e1d702cef9d25b32b0aaf63`- 所有三个 REST 返回模型路由的路径 `from_info` — `install` (line 180), `list` (228) and `get` （第251行）——因此，字段被一致地暴露，符合问题所期望的行为 `InstallationInfo.requested_ref` 包含 `ref` 被传递到 `manager.install(...)` 并被保存在 `check_/apply_canvas_extension_update`因此，值会从存储的安装记录中回传，而不是被重建。 - 范围仍然在这个仓库中：字段在标准Ag中公开

<a id="4784-fixfile_editor-prefer-valid-utf-8-encoding"></a>

### ＃4784：fix(file_editor)：更喜欢有效的UTF-8编码

- 提交：`16662b0bd2c1a93d3c5e282b48da05b95e90a0c8` (2026-10-08T11:42:23-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/4784).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-4784)。 家庭：F14、F27、F33。

陈述意图：

> - 当采样字节严格解码为 UTF-8 时立即返回 `utf-8`。
> - 保留对具有 UTF-8 BOM 的文件的 `utf-8-sig` 处理。
> - 对于非 UTF-8 内容，将 `charset-normalizer` 保留为回退方案。
> 在 `_recover_encoding` 中，先尝试 UTF-8，这样 `get_encoding` （编辑器使用的路径）就不会将一个有效的 UTF-8 文件切换回 cp1251、cp1252 或 latin-1。

更改的路径：

- `openhands-tools/openhands/tools/file_editor/utils/encoding.py`
- `tests/tools/file_editor/utils/test_encoding.py`

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4784#pullrequestreview-5331072133)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论：`fix(file_editor): prefer valid UTF-8 encoding` **范围 ** — 在存储库内并正确放置。 该更改位于 `openhands-tools/openhands/tools/file_editor/utils/encoding.py` 中，并进行了集中测试； 这里没有任何内容属于另一个存储库。 **更改评估** - 快速路径格式良好：UTF-8 BOM 检查（`codecs.BOM_UTF8` -> `utf-8-sig`），然后严格 `raw_data.decode("utf-8")` 样本解码在成功时返回 `utf-8`，然后在样本无效时返回现有 `charset_normalizer` 回退方案 UTF-8。 这使得常见情况（UTF-8源/JSON/Markdown/config）变得确定性，并防止高置信度的启发式分类错误覆盖有效的UTF-8解释，这是报告的字符集解析器3.5.0 CJK JSON 问题。 **我运行的验证** -
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4784#issuecomment-5476705857)：🚦 **CI 目前在 PR 的最新提交上失败。**请在 OpenHands 审核之前修复失败的检查 - 一旦您推送新的提交，就会自动重新检查。 （维护者还可以请求 `@all-hands-bot` 作为审阅者对其进行审阅，无论 CI 状态如何。）_这是一项自动检查 - 没有使用 AI 来生成此 comment._
- [讨论评论； ialexj](https://github.com/OpenHands/software-agent-sdk/pull/4784#issuecomment-6062118026)人类：我在项目中反复遇到这个问题。 该项目是英文的，但这种情况经常发生，因为该模型倾向于使用破折号和花哨的引号。 这已经够糟糕了，所以我加了一个防护措施 AGENTS.md 留意它。 我终于扔了一些 token 继续做，我的智能体诊断并生成重现。 它发现了这个现有的 PR 以及相关问题。 我希望这对你优先级的制定有所帮助。 --- ### 生产证据表明，读端的性能得到了提升 UTF-8 快速路径需要（以及 #3678 的写侧） 回退方案它不涵盖这种失败模式) 我们在生产中遇到了这种情况智能体-server / `openhands-tools` 1.53.0, Python 3.13, Linux `LANG=C.UTF-8`) 且独立地再现了这种误分类 PR 这次修复了 `mac_iceland` 并且存在无声字节篡改，不仅仅是读取失败。 **
- [讨论评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/4784#issuecomment-6062301101)人类：我在项目中反复遇到这个问题。 该项目是英文的，但这种情况经常发生，因为该模型倾向于使用破折号和花哨的引号。 这已经够糟糕了，所以我加了一个防护措施 AGENTS.md 寻找它。> > 我终于扔了一些 token 继续做，我的智能体诊断并生成重现。 它发现了这个现有的 PR 以及相关问题。 我希望这对你优先级的制定有所帮助。 > > ### 生产证据表明，读侧  UTF-8 快速路径需要（以及 #3678 的写侧） 回退方案它不涵盖这种失败模式) > 我们在生产中遇到了这种情况智能体-server / `openhands-tools` 1.53.0, Python 3.13, Linux `LANG=C.UTF-8`) 且独立地再现了这种误分类 PR 这次修复了 `mac_iceland` and silent byte corruption, not just a failed

<a id="5559-fixagent-server-keep-tmux-socket-paths-within-the-unix-socket-limit"></a>

### #5559: fix(agent-server)保持 tmux Unix socket路径超限内

- 提交：`2804c1273b4093e632e332a7a572894782c7b1e1` (2026-10-08T23:22:07+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5559).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5559)。 家庭：F01、F03、F05、F30、F31、F32。

陈述意图：

> - 智能体-服务器检查`$TMUX_TMPDIR/tmux-<uid>/openhands-<32 hex>`是否符合平台的套接字路径限制。 如果配置的或默认的目录太深，则使用 `/tmp/openhands-agent-server-<pid>` 代替。
> - 当它覆盖显式的 `TMUX_TMPDIR` 时，它会记录警告，并在关闭时恢复原始值。
> - 一个简短、明确的 `TMUX_TMPDIR` 与以前一样受到尊重。 套接字命名和隔离与 #5485 保持不变。

更改的路径：

- `openhands-agent-server/openhands/agent_server/api.py`
- `tests/agent_server/test_api.py`

链接问题接受上下文：

- [#5558](https://github.com/OpenHands/software-agent-sdk/issues/5558): [Bug]终端在“文件名过长”时会失败 TMUX_TMPDIR 它很深，因为每个池都有自己的 tmux socket 名称 — 当前状态已关闭，关闭于 2026-10-08T21:22:09Z。

> - [ ] 将 `TMUX_TMPDIR` 设置为对于套接字路径来说太深的目录，Agent Server 仍会初始化终端池并记录它所使用的目录。 - [ ] 未设置 `TMUX_TMPDIR` 且临时目录对于套接字来说太深 (macOS `$TMPDIR`)，每个服务器的默认值仍然适合。 - [ ] 简短而明确的 `TMUX_TMPDIR` 仍然保持不变。 ### 安装方法/版本 `uvx openhands-agent-server==1.53.0`，如 Agent Canvas 启动它。 也在 `main` 的 8ba966d 上转载。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5559#issuecomment-6026291519)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5559#pullrequestreview-5462499737): **批准** ✅ 已审核差分（`openhands-agent-server/.../api.py`, `tests/agent_server/test_api.py`) at head `55f5488`关联了 issue #5558 和其验收标准，以及当前-头 CI （包括所有绿色的） `agent-server-tests`, `workspace-tests`, `windows-tests`). 我已经检查并确认了以下内容： **socket-path math 是正确的。**  `sockaddr_un.sun_path` 在 Linux 上是 108 字节，在是 104 字节 macOS 包括 NUL因此，107/103的最大值是正确的。 我重现了边界的真实情况 tmux 在 Linux 上：107 字节 `$TMUX_TMPDIR/tmux-<uid>/openhands-<32hex>` 路径启动服务器；108 失败了 `File name too long`. - **`os.path.realpath()` 在 `_fits_tmux_socket` 是承载力，而非附带功能。**  tmux resolves `$TMUX_TMPDIR` 在绑定之前——我验证了一个指向深层目标的简短符号链接 *失败*, 而一个指向短路径的深层符号链接

<a id="4952-fixagent-server-resolve-linked-providers-for-plaintext-profile-reads"></a>

### ＃4952：fix(agent-server)：解析纯文本配置文件读取的链接提供程序

- 提交：`9c4fd8c6664dfce98524d04d965b4f009f390fbe` (2026-10-09T02:06:11+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/4952).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-4952)。 家庭：F20。

陈述意图：

> - 用 `X-Expose-Secrets: plaintext` 解析 `GET /api/profiles/{name}` 的链接提供程序。
> - 保留存储的配置文件、活动默认值以及普通和加密编辑器读取的现有未解决行为。
> - 涵盖加密的提供商存储和凭据轮换，以及真实的 HTTP 选择到 `RemoteWorkspace.get_llm(profile_name=...)`。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `b66c72436157` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -26,0 +27 @@
> +运算GET/api/canvas-extensions/installed/{extension_name}/iconoperationId=get_canvas_extension_icon_endpoint_api_canvas_extensions_installed__extension_name__icon_get
> @@ -191,0 +193 @@
> +参数GET/api/canvas-extensions/installed/{extension_name}/icon路径：extension_name必需=True模式=type=“字符串”minLength=1maxLength=255模式=“^[a-z0-9]+(?:-[a-z0-9]+)*$”
> @@ -471,0 +474,3 @@
> +响应 GET /api/canvas-extensions/installed/{extension_name}/icon 200 image/svg+xml 模式=type="string" format="binary"
> +回复 GET /api/canvas-extensions/installe

更改的路径：

- `openhands-agent-server/openhands/agent_server/profiles_router.py`
- `tests/agent_server/test_profiles_router.py`
- `tests/cross/test_remote_conversation_live_server.py`

链接问题接受上下文：

- [#5514](https://github.com/OpenHands/software-agent-sdk/issues/5514): [Bug]: 纯文本 LLM 配置文件读取省略链接提供程序凭据 — 当前状态已关闭，已于 2026-10-09T00:06:13Z 关闭。

> - [ ] 提供者链接的配置文件的明文读​​取解析提供者 API 密钥和基础 URL，包括当提供者凭据加密存储时。 - [ ] 后续读取使用轮换提供程序凭据。 - [ ] 普通和加密的编辑器读取保留其现有的未解决行为。 - [ ] 读取或选择命名配置文件不会修改存储的配置文件或活动默认值。 - [ ] 通过 `RemoteWorkspace.get_llm(profile_name=...)` 进行真实的 HTTP 测试验证选择和凭据旋转。 

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/4952#issuecomment-5634104584)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4952#pullrequestreview-5331217452): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围此更改属于此存储库。 `openhands-agent-server/openhands/agent_server/profiles_router.py` 是该存储库拥有的规范 Agent Server REST 表面； 扩展/自动化后续仅消耗它。 不需要文件移动或维护者架构决定。 ## 变化是什么 `GET /api/profiles/{name}` 现在将 `resolve_provider=expose_mode == "plaintext"` 传递到 `LLMProfileStore.load`。 以前该路线一直使用`resolve_provider=False`。 我追踪了周围的代码：- 明文分支（唯一一个能解析的分支）然后以 `build_expose_context("plaintext", cipher)` 作为输出，因此之前的机密也被暴露了，现在链接的提供者的 `api_key` / `base_url` 也被添加了。- 缺少头部和 `encrypted` 分支仍然存在
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4952#pullrequestreview-5427552385)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围属于此处。 `openhands-agent-server/openhands/agent_server/profiles_router.py` 是该存储库的规范 Agent Server REST 表面； 扩展/自动化后续仅消耗它。 无需文件移动或架构决策。 ## 更改 `GET /api/profiles/{name}` 现在将 `resolve_provider=expose_mode == "plaintext"` 传递到 `LLMProfileStore.load`，而不是硬编码的 `resolve_provider=False`。 我对比了两个分支，与基础行为一致：- 明文（唯一能解决的模式）：`load` 应用链接连接的 `api_key`/`base_url`，随后的 `build_expose_context("plaintext", cipher)` 指令暴露了它们，以及该模式自身的机密。 这正是凭据集`RemoteWorkspace.get_llm(profile_name=...)`的需要，并且它与plate匹配
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4952#pullrequestreview-5428818545)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围属于此处。 `openhands-agent-server/openhands/agent_server/profiles_router.py` 是该存储库的规范 Agent Server REST 表面； 扩展/自动化后续仅消耗它。 ## 自上次审查以来发生了什么变化上一个标题 `da27a9ec` 已获得批准。 这个头 `6b41f7ad` 只有 PR-只有的文件 [ 由自动化 ] 删除，删除了 `.pr/stop-bash-evidence.md` 和 `.pr/stop-bash-evidence.py` — 与 BashCommand PR #5348 无关的 `main` 文件，这两个头都没有。 路由器差异和两个测试文件与批准的主干版本（`git diff da27a9ec 6b41f7ad -- .../profiles_router.py` 为空）完全相同，因此实质性更改没有变化。## 变更 `GET /api/profiles/{name}` 现在通过了 `r
- [reviews APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/4952#pullrequestreview-5455205516)已批准：明文配置读取路径现在重用现有提供商解析以返回当前 API key 和 base URL 需要的 RemoteWorkspace.get_llm，普通/加密编辑器的读取问题仍未解决。 测试覆盖了加密的提供商存储、密钥旋转和真实环境 HTTP  SDK 不改变存储的用户资料或活动默认值，检索。 已审核头 6b41f7ad1717a18eb11488601ff3e833f805c65b； 当前 CI 是绿色的。 未发现阻塞正确性问题。 这值得作为一个独立的分支合并 SDK 修复了 bug，但不再作为扩展的必要条件#547: that PR 现在显示对话元数据中的模型来源，而不读取提供者密钥。 风险：中等，因为这改变了凭据- 返回响应，但保留了现有身份验证明确的明文暴露机制。 此评论已生成
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/4952#issuecomment-5634476665)：@OpenHands /codereview 这个 PR 请发表您的反馈作为评论。 也看看链接的PR。 我们真的需要添加明文机密吗？ 其他选择？ 为什么看起来需要它？
- [讨论评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/4952#issuecomment-5636792479): 🟢 **好品味** 我翻阅了这个 PR and the linked OpenHands/extensions#547 flow. 我做 **不** 我认为这样 PR 添加了新的纯文本内容机密能力： `X-Expose-Secrets: plaintext` 已经在设置和用户读取中存在 `RemoteWorkspace.get_llm(profile_name=...)` 已经请求了，以及一个内联的元数据 API 在该模式下，密钥以明文形式返回。 此补丁使提供程序链接的配置文件遵循与内联配置文件相同的运行时读取约定。 为什么在当前设计中需要它：一个链接的个人资料故意只存储 `provider_connection_id`; 当前提供者密钥和基础 URL 生活在提供商商店。 创建对话 API 接受一个具体的代理LLM但是它不接受一个 LLM 服务器端解析的用户名。 因此，extensions#547 必须在构建之前解析指定的配置文件
- [讨论； 评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/4952#issuecomment-5636819334)：已审查 PR #4952 及关联的 OpenHands/extensions#547，并在此发布反馈： https://github.com/OpenHands/software-agent-sdk/pull/4952#issuecomment-5636792479 。结论：PR 不会引入明文暴露； 它使提供者链接的配置文件与现有的经过身份验证的 `X-Expose-Secrets: plaintext` 运行时合约保持一致。 一个服务器端LLM配置选择器可以避免明文传输，并且是长期设计上的更清洁方式，但这是一个较大的API变更，不应阻碍这个聚焦的修复。 验证： - 通过了 106 个配置文件路由器测试 - 通过了 2 个选定的实时服务器测试 - 当前 CI 故障似乎无关 - 工作区文件没有更改 GitHub 不可能进行正式批准，因为可用的 token 属于 PR 作者，所以我将请求的审查作为 PR 评论发布。
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4952#issuecomment-5662938852)：🚦 **CI 目前在 PR 的最新提交上失败。**请在 OpenHands 审核之前修复失败的检查 - 一旦您推送新的提交，就会自动重新检查。 （维护者还可以请求 `@all-hands-bot` 作为审阅者对其进行审阅，无论 CI 状态如何。）_这是一项自动检查 - 没有使用 AI 来生成此 comment._

<a id="5619-testagent-server-avoid-overlong-tmux-test-socket-paths-on-macos"></a>

### #5619: test(agent-server): 避免 macOS 上的 tmux 测试套接字路径过长

- 提交：`d1bfda28da7f5c4d3b33d65e729161cef6e0a4ec` (2026-10-09T03:50:36+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5619).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5619)。 系列：无需产品运行时间。

陈述意图：

> * 将默认路径选择测试与目录创建测试分开，避免有关生产默认值的断言中的随机测试夹具路径。
> * 使用真正简短的最终目录进行真实的 TmuxPanePool 集成测试和寿命测试。
> * 使用模拟规范路径添加确定性 macOS/Linux 套接字路径字节长度测试，无需全局猴子修补进程身份。
> 
> 没有生产代码更改。 每个进程的目录名称、套接字隔离、路径长度验证和 /tmp 回退方案保持不变。
> 
> #5559 的后续（原始 bug #5558）。

更改的路径：

- `tests/agent_server/test_api.py`

链接问题接受上下文：

- [#5620](https://github.com/OpenHands/software-agent-sdk/issues/5620): [Bug]: Agent Server tmux 测试测试夹具超出 macOS Unix 套接字路径限制 — 当前状态已关闭，已关闭 2026-10-09T01:50:39Z。

> 默认路径选择测试不依赖于随机的测试夹具目录长度。实际的 tmux 集成测试使用一个足够短的套接字目录来容纳 macOS。确定性测试涵盖 macOS 和 Linux 规范套接字路径字节限制。仍然涵盖目录创建和生命周期环境恢复。毫无生产行为或套接字隔离变化。 ☐ 通过相关 CI 测试。 

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5619#pullrequestreview-5464805793)：已批准。 仅测试更改可正确阻止测试重新创建生产代码所防范的 macOS 套接字长度故障。 在`tests/agent_server/test_api.py`本地验证：- 全文件：`uv run pytest tests/agent_server/test_api.py` -> **47通过**(tmux子集`-k tmux` -> 9通过)。- 新`test_default_server_tmux_tmpdir_counts_canonical_socket_bytes[macos]`和`[linux]`都通过LinuxCI，确认103/107边界在一台平台上被行使。- `ruff check`和`ruff format --check`干净。 设计读起来很好：将默认路径选择与目录创建分开，使用一个真正短的最终目录来执行真正的`TmuxPanePool`/lifespan测试，并保持`/tmp`回退方案的确定性。 正如宣传的那样，没有生产变化。 两个小的、非阻塞的注意事项： 1. 新的参数化测试硬编码

<a id="5616-choreagent-server-refresh-npm-pin-and-automate-observed-updates"></a>

### ＃5616：chore(agent-server)：刷新 npm pin 并自动观察到的更新

- 提交：`33044182505244749928644a4643368a9e998ee7` (2026-10-09T02:35:02Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5616).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5616)。 家庭：F01、F12、F16、F31。

陈述意图：

> - 将规范运行时和 ACP 节点运行时的共享 npm pin 从 11.19.1 升级到 11.21.0。
> - 添加每日/手动更新程序，选择至少 7 天前的稳定、非已弃用、相同主要版本； 切勿降级或编辑不明确的引脚。
> - 使用现有机器人 PAT 打开草稿更新 PR，以便运行普通 PR CI。 无需自动合并，无需强制推送，无需重写人工审核； 一次一个待处理的 npm 更新，并且之前关闭的版本 PR 不会重新打开。

更改的路径：

- `.github/scripts/update_npm_pin.py`
- `.github/workflows/update-npm-pin.yml`
- `openhands-agent-server/openhands/agent_server/docker/Dockerfile`
- `tests/cross/test_agent_server_build_metadata.py`
- `tests/cross/test_update_npm_pin.py`

链接问题接受上下文：

- [#5618](https://github.com/OpenHands/software-agent-sdk/issues/5618)：刷新智能体-服务器 npm pin 并自动观察到的相同主要更新 - 当前状态已关闭，已于 2026-10-09T02:35:05Z 关闭。

> - [  ] 的智能体-server Dockerfile的单个 `ARG NPM_VERSION` 默认的 `11.21.0`和两个消费站点都使用它：canonical阶段运行 `npm install --global "npm@${NPM_VERSION}"` 和 ACP 阶段运行 `"$ACP_NODE_DIR/bin/npm" install --global "npm@${NPM_VERSION}"`. - [  ] 现有的 CI test `tests/cross/test_agent_server_build_metadata.py::test_agent_server_uses_one_pinned_npm_version_for_both_node_runtimes` 通过新的pin（其版本断言已更新）  仍然有效 [  ] 一个构建智能体- 安装 npm `11.21.0` 在 canonical 和 ACP 运行时，以及 npm CLI 在每个运行时的 Node（目前）下执行成功 `24.21.0` for both). - [  ] 存在一个仓库拥有的工作流，该工作流具有  `schedule` 触发和 `workflow_dispatch`，与现有的 Debian 更新器镜像，并与现有的认证 `OPENHANDS_BOT_GITHUB_PAT_PUBLIC`  凭据 (no new) 凭据或注册表配置） [  ] Release selection读取官方的 npm 注册表并选择最高稳定（非预发布）、非已弃用当前主要版本内的 release 注册表发布时间至少提前七天。 它从不选择低于当前版本的版本（不允许降级），并且在没有可用的更新版本时不会进行任何编辑 [  ] 缺少一个插头，或者有多个 `ARG NPM_VERSION=<x.y.z>` 这行代码会导致更新失败，因为没有编辑 Dockerfile [  ] Pin 编辑是幂等的：在没有符合条件的更新的情况下重新运行不会产生任何文件更改（空差异），并且

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5616#issuecomment-6067433688)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5616#pullrequestreview-5463527778): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围在此存储库的范围内。 智能体-服务器 npm pin 及其图像位于此处（`.github/scripts/update_npm_pin.py`、`.github/workflows/update-npm-pin.yml`、`openhands-agent-server/openhands/agent_server/docker/Dockerfile`、`tests/cross/test_update_npm_pin.py`），因此不需要继续进行产品/架构决策。 技术审查进行中。## 阻止的发现** 挤压破坏了现有测试，CI 在这个头上有红叉。** `cross-tests` 在`8b2deea` 失败了：``` tests/cross/test_agent_server_build_metadata.py::test_agent_server_uses_one_pinned_npm_version_for_both_node_runtimes FAILED AssertionError: assert '11.21.0' == '11.19.1' ``` `tests/cross/test_agent_server_build_metadata.py:161` 硬编码了预期值：```python assert match.group(1) == "11.19.1" ``` 这PR 是一个
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5616#pullrequestreview-5464922624)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围在范围内。 智能体服务器的npm pin、其更新脚本/工作流以及跨测试都在这个仓库中，因此无需产品/架构决策。## 自上次审查以来，之前阻塞的发现（左移`tests/cross/test_agent_server_build_metadata.py`断言`11.19.1`，`cross-tests`变红）已解决。 `6c0b43b88` 修正了 literal-value 的断言，并将相邻的 Python/Node 释放的 literal 替换为版本格式检查，因此未来版本的 pin bump 不再需要手动编辑。 `cross-tests` now passes. ## 对此头的验证 (`e70ae3b0`) - 直接运行 `tests/cross/test_update_npm_pin.py` 中的更新程序测试（此处未安装 pytest）：均通过，涵盖 7 天边界，相同专业/预科
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5616#discussion_r4224707481)：这一行更改破坏了`tests/cross/test_agent_server_build_metadata.py:161`，它断言`match.group(1) == "11.19.1"`。 CI证实了这一点：``` test_agent_server_uses_one_pinned_npm_version_for_both_node_runtimes FAILED AssertionError: assert '11.21.0' == '11.19.1' ````cross-tests`因此是红色的。 因为`update_npm_pin.py`只重写了这个Dockerfile的版本，而测试保留了原始的，所以这个PR添加的自动更新器在未来的npm bump上都会失败`cross-tests`。 将断言更新为 `11.21.0`（理想情况下从引脚派生，这样就不需要在每次更新时进行编辑）。
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5616#issuecomment-6070425157): 已修复 6c0b43b88 中的跨测试失败，移除了针对特定 npm 版本的断言，并将相邻的 Python/Node 版本标识符替换为版本格式检查。 共享的 npm pin 使用和运行时布局断言仍然存在； 更新程序测试仍然执行综合版本选择行为。 验证：重现更改前的npm断言失败； 随后使用 stdlib 线束加载真正的无依赖目录，所有 15 个构建元数据/更新程序测试函数都通过了。 `git diff --check`通过。 完整的 pytest/预提交在本地不可用（预提交调用失败，因为可执行文件不存在）； fresh CI 将验证这些。 之前的 PR 描述失败请求问题链接； 描述现在链接#5618。 HUMAN 部分未经编辑。 _此评论由 AI 智能体 (OpenHands) 在
- [讨论； 评论； 所有手都机器人](https://github.com/OpenHands/software-agent-sdk/pull/5616#issuecomment-6072102426): ### ⏳ 等待检查的审查当前头`e70ae3b03cb7`仍然有检查尚未完成，因此没有开始审查对话： - `agent-server-tests` - `build-binary-and-test (ubuntu-latest)` - `cross-tests` 无需采取行动。 每次对头部进行检查后，定期扫描重试都会报告结论。 _这是一个自动检查 - 没有使用人工智能来生成此comment._

<a id="5673-featllm-add-digitalocean-inference-as-a-verified-provider"></a>

### ＃5673：feat(llm)：添加DigitalOcean推理作为经过验证的提供者

- 提交：`cd17bd89d52ef209abbfca5870631d0474ca8f66` (2026-10-09T15:14:20+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5673).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5673)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - `litellm_call_kwargs` 现在解析来自一个小表的路由 SDK 前缀：`openhands/` → `litellm_proxy/` + OpenHands 代理（不变），以及 `digitalocean/` → `openai/` + `https://inference.do-ai.run/v1`。 用户提供的`base_url`仍然获胜。
> - `VERIFIED_MODELS["digitalocean"]` 添加了一个简短的 DO 模型 ID 列表（取自 `GET /v1/models`），因此 DigitalOcean 出现在提供者/模型选择器的已验证部分中。 仅具有工具调用功能的聊天完成模型； gpt-6 行被省略，因为 DO 需要其工具的响应 API。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/openhands_provider.py`
- `openhands-sdk/openhands/sdk/llm/utils/verified_models.py`
- `tests/sdk/llm/test_llm.py`
- `tests/sdk/llm/test_model_list.py`

链接问题接受上下文：

- [#5666](https://github.com/OpenHands/software-agent-sdk/issues/5666)：[功能]：添加DigitalOcean推理作为可选（已验证）LLM提供者 - 当前状态已关闭，已于 2026-10-09T13:14:22Z 关闭。

> - [ ] `digitalocean/<model>` 通过 `api_base=https://inference.do-ai.run/v1` 路由到 `openai/<model>`（单元测试在 `litellm_call_kwargs` 式路由上），并且用户提供的 `base_url` 仍然获胜。 - [ ] `VERIFIED_MODELS["digitalocean"]` 存在，并且仅包含经过实时验证的模型，以完成多轮智能体运行，其中工具调用超过 `/chat/completions`（无仅响应模型）。 - [ ] 上下文窗口 / 最大输出 token / 特征标志（视觉、推理、提示词缓存）对于每个经过验证的 DO 模型都是已知的，因此上下文压缩和限制行为正确（LiteLLM 没有 `openai/<do-model-id>` 的元数据）。 - 智能体服务器上的 [ ] `GET /llm/providers` + `/llm/models/verified` 公开 `digitalocean`，因此 Agent Canvas 将其列在已验证的提供程序部分中。 - [ ] 遥测/成本核算不会破坏这些模型（未知的定价是可以接受的， 错误不[。 - ] OpenHands OpenHands (Agent Canvas): 显示名`digitalocean: "DigitalOcean"`在`src/utils/map-provider.ts`，并释放后SDK一次**。 ### 考虑的替代方案 - LiteLLM`gradient_ai/` **: 无调用工具（见上文），URL错误`/v1` URLs。 可以在LiteLLM中修复上游，但我们仍然依赖于它的发布和过时的模型元数据。 - **仅限高级设置（`openai/` + 自定义基础 URL）**：已经可以工作并且可以作为权宜之计记录下来，但它不是可选择的提供程序，并且要求用户知道端点和模型 ID。 ### 优先级/严重性高 - 对生产力有重大影响 ### 估计范围小 - API 添加、conf

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5673#issuecomment-6081093056)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5673#pullrequestreview-5470362841): LGTM, thanks!

<a id="5182-featsecurity-emit-securityanalysisevent-with-the-analyzers-verdict-per-action-batch"></a>

### ＃5182：feat(security)：使用分析器对每个操作批次的判断发出SecurityAnalysisEvent

- 提交：`9e76fe72b43f7be65b48a243486c2e30b5104a22` (2026-10-09T16:24:54Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5182).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5182)。 家庭：F06、F07、F08、F32、F33、F34。

陈述意图：

> - **异步审计屏蔽**：在释放会话状态锁的同时解决工作人员中的惰性机密，然后重新检查注册表稳定性并在应用确认策略之前发出屏蔽审计。 回归覆盖范围使用真实的环回 HTTP 机密服务并在查找期间注册另一个机密。
> 
> - **`SecurityAnalysisEvent`** (`event/security.py`)：`source="environment"`，而不是 `LLMConvertible`，因此模型永远看不到它。 字段：`analyzer`（种类）、`policy`（种类）、`risks: dict[EventID, SecurityRisk]`、`details: dict[EventID, dict[str, Any]]`。
> - **`SecurityAnalysis(risk, details)`** 加 `SecurityAnalyzerBase.analyze_action()`（可覆盖，默认为换行 `security_risk()`）和 `analyze_actions()`。 这让分析者可以附加概率、置信度或理由。 现有分析仪无需改变； `analyze_pending_actions()` 保留为新路径上的仅风险包装器，因此其行为（包括异常情况下的 HIGH）不变。 例外情况下，详细信息包含 `{"error": ...}`。
> - **排放**：每个分析的操作批次一个事件，来自“_requires_user_confirm”

更改的路径：

- `.github/agent-server-openapi-weak-schema-allowlist.json`
- `openhands-sdk/openhands/sdk/agent/agent.py`
- `openhands-sdk/openhands/sdk/agent/response_dispatch.py`
- `openhands-sdk/openhands/sdk/event/__init__.py`
- `openhands-sdk/openhands/sdk/event/security.py`
- `openhands-sdk/openhands/sdk/security/__init__.py`
- `openhands-sdk/openhands/sdk/security/analyzer.py`
- `tests/sdk/agent/test_async_secret_masking.py`
- `tests/sdk/agent/test_security_analysis_event.py`

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews COMMENTED; enyst](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5261393746)❌ QA Report: FAIL 审计事件在执行中工作 SDK 但先/后 QA 重现了定制分析器确认绕过和未解密的机密持久化。 ### 是否此 PR 实现其目标？ **部分。** 开 `fd5904e5`判决和细节到达回调并且继续撰写、关闭和重新开启对话。 一个批次包含三个动作，会产生一个审计事件，而审计事件不会被包括在内 LLM view. 然而，这并不适用于现有的批处理分析器重写，新的已持久化详细信息已跳过注册-机密遮罩。 \| Phase \| 结果 \|  \|---\|---\|  \| 环境设置 \| ✅ 锁定 SDK 与之一起安装的运行时 `uv sync --frozen --package openhands-sdk --no-dev`; SDK 导入成功 \|  \|  CI status \| ✅ 当前头：33 成功，6 跳过； None 失败/pe
- [reviews COMMENTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5261560196)_此评论由人工智能创建智能体 (OpenHands代表仓库 maintainers._  **口味评分：良好** 👍 没有发现任何材料。 这是一个干净、增量的更改： **默认情况下，受保护且无活性**只有排放才会发生 `state.security_analyzer is not None`; 如果没有分析器，调度路径与之前的字节相同（只是一个额外的默认参数）。 现有用户无需付费 **联合注册工作**: `DiscriminatedUnionMixin` 自动注册 `SecurityAnalysisEvent` — 由 [confirmed by the] 确认的 OpenAPI 需要（并获取）受控允许列表条目 `details`. 该事件不 `LLMConvertibleEvent`所以它永远不会进入模型的上下文，and the JSON 往返通过 `Event` 联合测试通过 **兼容性保留**: `analyze_pending_actions()` 现在是一个只包含风险的包装层 over `analyze_action
- [reviews COMMENTED; smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5262281573) 🟡 QA Report: PARTIAL 两个报告的回归均已修复 `6fa4e0ed8`15 个本地功能场景通过。 直播 LLM 验证被缺少的验证阻止了凭据。 ### 是否此 PR 实现其目标？ 是的，已行使 SDK 路径：分析器的判定记录在执行之前，包括  NeverConfirm留在  LLM 查看并生存。 现在，遗留的批处理已提供实际的确认裁决，且注册的机密在嵌套的详细信息和异常消息被隐藏之前回调和持久化。 \| Phase \| 结果 \|  \|---\|---\|  \| 环境设置 \| ✅ `make build` 完成 \|  \|  CI status \| 待推的提交。 预置 CI 通过了，但未解决的审查线程  \|  \| 功能验证 \| ✅ 15 local SDK 场景； 可用的实时提供商调用不可用 \|  <details><summa
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5372178140)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## PR #5182 @ `6fa4e0e` **范围：** 仓库内的评论。 事件、智能体发布和安全分析器都属于这个仓库，变更遵循SDK → OpenAPI → TS-client 流程：新的`SecurityAnalysisEvent` 是一个`environment` 源的事件，不是`LLMConvertible`，因此它永远不会进入模型上下文，而OpenAPI 弱-模式入口是针对`details`（设计上是分析器特定的，与`HookExecutionEvent.hook_input` 的先例相同）。### 验证在这一分支上 - ** 之前 P1 线程已经解决，并且修复措施存在。** 咨询了旧的 `analyze_pending_actions` 配置，通过 `type(self).analyze_pending_actions is not SecurityAnalyzerBase.analyze_pending_actions`，发出的事件通过 `state.secret_registry.mask_secrets_in_mo
- [评论； CHANGES_REQUESTED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5409099663)：🟡**品味评级：可接受** - 事件模型和向后兼容分析器包装器是一致的，但当前头尚未准备好合并。 **[CRITICAL ISSUES]** - [当前头 CI] **Windows 二进制构建失败：** `build-binary-and-test (windows-latest)` 在当前头上失败： https://github.com/OpenHands/software-agent-sdk/actions/runs/37243581710/job/111556964633.  在请求重新审核之前，诊断并修复故障，或者如果故障明显是暂时性的，则成功重新运行它。 PR 包含了一个真实的 LLM/工具端到端事件-持久化会话记录，而 Canvas 图像证据实际上并不适用，因为这个 PR 添加了一个 SDK/服务器事件而没有 UI 显示。 静态审查未发现提示词注入、危险脚本、暴露机密、依赖/供应链更改或合并冲突。 **[RISKASSESSMENT]** - [结束
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5417498063)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## PR #5182 @ `717eed4` ** 范围：** 仓库内的评论。 事件、智能体调度和安全分析器均归此存储库所有，并且更改遵循 SDK → OpenAPI → TS 客户端流程：新的 `SecurityAnalysisEvent` 是源自 `environment` 的非 `LLMConvertible` 事件，因此它永远不会进入模型上下文，并且弱模式允许列表条目的范围为 `details`（按设计特定于分析器，与 `HookExecutionEvent.hook_input` 的先例相同）。 ### 对此进行了验证 - **早期的 P1 线程均已解决并且存在修复。** `analyze_actions()` 仍然通过旧的 `analyze_pending_actions` 覆盖（当存在时）进行路由（`type(self).analyze_pending_actions is not SecurityAnalyzerBase.analyze_pending_actions`），并且发出的事件通过“mask_secrets_”进行屏蔽
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5182#pullrequestreview-5421134224)：已批准以下显式维护者授权审查头 717eed414。 我之前的评论中提到的 Windows CI 故障就在这个问题上得到了解决。 当前检查已通过，并且五模型集成工作流程在此精确提交上成功（49 项通过，1 项预期愿景跳过）。 异步机密检查后的判决排放，遗留批处理分析器兼容性，回调/持久性之前掩码，锁释放状态的回归覆盖。 没有重大代码发现。 GUI 屏幕截图不适用，因为这会添加一个不带 UI 渲染的 SDK 事件。 特定功能的现场证据由作者提供； 最新的异步路径具有受控模型/真实HTTP覆盖范围。 我没有独立重新进行现场对话。 风险评估：中——确认发送、注册机密处理和公共已序列化事件。 不-a
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5182#discussion_r4057744486): 🔴 **关键的 [P1]在更改调度时保留现有批处理分析器的覆盖 API.** 这取代了调用 `analyze_pending_actions()` 与 `analyze_actions()`. 兼容性包装器只保留调用旧方法的调用者，而不是重写该方法的自定义分析器： 智能体现在默默地忽略他们的批量裁决。 我在基底和头文件上重现了这种在活的俳句驱动对话中进行的情况，但分析器保持不变。 ```python class LegacyBatchAnalyzer(SecurityAnalyzerBase): def security_risk(self, action): return SecurityRisk.LOW def analyze_pending_actions(self, pending_actions): return [(action, SecurityRisk.HIGH) for action in pending_actions] ``` Under `ConfirmRisky()`终点站 `waiting_for_confirmation` 与 **0次文件写入操作**. 这个头尾部是  **1. 实际文件写入**, 并且新的审计报告说 LOW, e
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5182#discussion_r4057744490): 🔴 ** 严重 [ P1]: 面具注册机密在发出分析器详情之前 ** `analysis.details` 直接传递到一个事件，该事件由回调链持久化并发布； 异常回退方案现在也将 `str(e)` 放入这些细节中。 该回调链中没有通用的机密掩蔽步骤。 仅使用合成值进行复制：寄存器 `QA_SYNTHETIC="qa-fake-secret-5182-not-real"`，然后让分析器加注 `RuntimeError("upstream rejected credential qa-fake-secret-5182-not-real")`。 在这一点上，回调和关闭/重新打开后读回的事件都包含`details[action_id]["error"]`中的文字值。 注册表自己的`mask_secrets_in_output()`正确地返回`<secret-hidden>`； 基地没有将此错误文本放入事件日志中。 后端请求错误和分析器原理可能包含 c
- [review_comments; 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5182#discussion_r4058581335)：已在 6fa4e0ed8 中修复。 详细分析桥现在尊重现有的 analyze_pending_actions 覆盖并包装他们的结论，而无需进行第二次分析。 共享的每个操作实现还允许遗留覆盖调用super()而无需递归。 回归覆盖范围通过智能体调度检查两种覆盖表单。 功能 QA 之前/之后将遗留情况从完成 / 1 写入 / LOW 更改为 waiting_for_confirmation / 0 写入 / HIGH； 异步派遣同意。
- [review_comments; 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5182#discussion_r4058581416)：已在 6fa4e0ed8 中修复。 完成的SecurityAnalysisEvent在on_event之前经过对话注册表的递归模型屏蔽。 回归覆盖率检查在回调、已持久化 JSON 中嵌套成功的详细信息和异常详细信息，并重新打开对话，保留异常的 HIGH。 功能 QA 更改之前/之后 raw_fake_secret_in_event_files 从 True 更改为 False； 异步错误和嵌套详细信息也显示回调中没有原始合成机密或重新打开的事件日志。
- [review_comments; 评论； 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5182#discussion_r4232229939)：```suggestion This event is not sent to the LLM. ```
- [review_comments; 评论； 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5182#discussion_r4232238484)：```suggestion rationale) should override this. ```
- [讨论； 评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5182#issuecomment-5739247079)：PR#5182 上的两个 CI 故障均已解决并推送到 fork 分支 `feat/security-analysis-event`。 ## 失败的原因 1. **`sdk-tests`** — 唯一失败的测试是 `tests/sdk/llm/test_model_features.py::test_reasoning_effort_support[openrouter/moonshotai/kimi-k2.5-False]`。 这是已知的数据漂移问题 (#4877)：LiteLLM 在导入时从上游获取其模型数据库，`openrouter/moonshotai/kimi-k2.5` 现在报告 `reasoning_effort` 支持。 测试文件本身（以及这个 PR）不受 PR 的影响，并且同一文件已经记录了这些值“可能会再次移动”。 2. **`Validate PR description`** — PR 主体缺少所需的 `## How to Test` 部分，并且 `## Issue Number` 中没有相关问题。 ## 我做了什么 - **`sdk-tests`修复**：翻转了漂移的期望 `("openrouter/moonshotai/kimi-k2.5",
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5182#issuecomment-5753096898)：⚠️**OpenHands 在 2 小时后放弃了此评论**以提交 `fd5904e5403d`（最后状态：`active`）。 _此评论由 AI 发布智能体 (OpenHands)._
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5182#issuecomment-5753914211)：🚦 **CI 目前在 PR 的最新提交上失败。**请在 OpenHands 审核之前修复失败的检查 - 一旦您推送新的提交，就会自动重新检查。 （维护者还可以请求 `@all-hands-bot` 作为审阅者对其进行审阅，无论 CI 状态如何。）_这是一项自动检查 - 没有使用 AI 来生成此 comment._
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5182#issuecomment-5994273618): # 🧪 集成测试结果 **总体成功率**: 100.0% **总成本**: $1.96 **测试模型**: 5 **时间戳**: 2026-10-05 12:17:19 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37308104363) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37308104363) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37308104363) - **litellm_proxy_deep
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5182#issuecomment-5994452952): HUMAN: @neubig Re: > Current-head CI] Windows 二进制构建失败：build-binary-and-test (windows-latest) 在当前 head 上失败： https://github.com/OpenHands/software-agent-sdk/actions/runs/37243581710/job/111556964633.  诊断并修复故障，或者在请求重新审核之前，如果故障明显是暂时的，则成功重新运行它。 这显然是短暂的，GitHub 跑步者只是停了下来。 我的智能体重新运行了它，它通过了。 PR 中没有任何内容影响它。
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5182#issuecomment-6084791244)：我是一名 AI 智能体，帮助 Engel Nyst (@enyst) 进行项目工作。 审查并独立测试了当前的头 **`d6a512553bf92c896dd9f2fd877f7aaa2b041fbc`**。 所请求的实时迁移和恢复测试已通过； 我在这些运行中没有发现阻塞事件层回归。 我使用了真实的 OpenHands Agent Canvas 应用程序、保存的 DeepSeek 配置文件、真实的 DeepSeek API 响应 (`deepseek/deepseek-flash`) 和实际的文件/终端工具。 该堆栈是 Canvas **1.25.0** (`6e8157147936768bf358903a6341bc01e0ce1ac9`)、TypeScript 客户端 **1.53.0** 和自动化 **1.19.0**。 PyPI 确认智能体-server **1.53.0** 是最新版本。 - 我在该版本上创建了两个对话，重新启动了相同的已持久化应用程序状态，并从 PR 签出安装了所有四个 SDK/服务器包，然后继续执行这两个操作。 - 然后我在 PR 上创建了两个对话，clo

<a id="5683-chore-remove-stale-triage-workflow-and-maintainer-roster"></a>

### ＃5683：杂务：删除陈旧的分类工作流程和维护人员名册

- 提交：`dd1af943cb491e21c4b0f83f513ccf602c43f2dd` (2026-10-09T18:34:48+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5683).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5683)。 系列：无需产品运行时间。

陈述意图：

> - 删除`.github/workflows/stale.yml`。
> - 删除未使用的 `MAINTAINERS` 名册。

更改的路径：

- `.github/workflows/stale.yml`
- `MAINTAINERS`

链接问题接受上下文：

- [#5684](https://github.com/OpenHands/software-agent-sdk/issues/5684): [维护] 移除过时的滞留工单和维护人员名单 — 当前状态已关闭，关闭时间：2026-10-09T16:34:50Z。

> - [ ] `.github/workflows/stale.yml` 已从默认分支中删除，并且存储库范围内的搜索找不到对 `actions/stale` 或该工作流程文件的剩余引用。 - [ ] `MAINTAINERS` 已从默认分支中删除，并且存储库范围内的搜索未发现 `assign-reviews.yml` 或任何活动工作流程消耗的对 `MAINTAINERS` 的剩余引用。 - [ ] 更改仅限于两个命名文件：GitHub 与 `main` 的比较视图仅显示这两个删除，没有添加或修改文件。 - [ ] 计划的过时作业不再运行：工作流不再出现在存储库的“操作”工作流列表中，并且删除后不会生成进一步的计划运行。

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5683#pullrequestreview-5472772900)：LGTM。 直接删除过时的自动化配置，与更新的所有权/分类策略一致。 未找到悬空引用。 （由 AI 智能体代表请求者进行审核。）

<a id="5670-fixfile-editor-preserve-terminal-newline-semantics"></a>

### ＃5670：fix(file-editor)：保留终端换行符语义

- 提交：`bfc1ae71b0e0bb9433a7bd3b7f07a498271a14b6` (2026-10-09T12:39:18-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5670).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5670)。 家庭：F14、F27、F33。

陈述意图：

> - 使用 `splitlines()` 对实际文本行进行编号，而不是对换行符进行编号。
> - 不要为空文件附加伪造的输出行。
> - 通过公共文件编辑器路径覆盖未终止、单终止、空白最后行和空文件。

更改的路径：

- `openhands-tools/openhands/tools/file_editor/editor.py`
- `tests/tools/file_editor/test_basic_operations.py`

链接问题接受上下文：

- [#5668](https://github.com/OpenHands/software-agent-sdk/issues/5668)：[Bug]：文件编辑器视图为终端换行发明了编号行 - 当前状态已关闭，已于 2026-10-09T16:39:20Z 关闭。

> - [  ]  `file_editor(command="view")` 包含一个文件 `hello\n` 仅渲染编号线 1 (`hello`），没有第二个（空白）编号行。 - [  ]  `file_editor(command="view")` 空文件渲染无编号内容行 [  ]  `file_editor(command="view")` 在 `hello` (无终端换行符) `hello\n`, and `hello\n\n` 渲染时，每行正确计数：1，1，以及2（最后一行包括一个实线编号的空行） [  ] 范围的 `view` (`view_range`) 和编辑结果片段`str_replace`, `insert`) 保持正确的绝对行号，具有相同的不伪造末行行为 [  ] 测试覆盖了空文件、未结束的文件、单行结束的文件以及空白行结尾的文件，以及现有的文件编辑器测试、格式化和类型检查通过 [  ] 重跑 `critic` 在发布中示例 CI 配置完成模型/代理在步骤限制内智能体追逐一个伪造的空行。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5670#issuecomment-6080889048)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5670#pullrequestreview-5471805059)：_此评论由 AI 智能体 (OpenHands) 发布。_ 简单的 `view` 修复本身是正确的：`splitlines()` 对实际文本行进行编号，因此 `hello\n` 现在仅呈现第 1 行，而空文件不呈现编号内容，与链接的问题 #5668 匹配。 重点套件通过 (`160 passed`) 和当前头部检查 `tools-tests`、`integration-test`、`test-examples` 和 `build` 为绿色。 然而，`_make_output` 的语义变化与未处理的范围视图调用者交互，并在此引入了回归，因此这不符合该问题自身接受标准，即范围`view` 保持正确的行号。 内嵌详细信息。 另外，`Validate PR description` 检查在 `HUMAN:` 和 `AGENT:` 之间缺少人类撰写的注释，导致仍然使用空模板注释。 这是拥有的合并门
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5670#discussion_r4231531785)：当请求的范围以空行结束时，`split(" ")` -> `splitlines()` 更改使 ranged `view` 默默地删除尾随空行。 远程调用者 (`editor.py:419-420`) 将 `"\n".join(file_content.splitlines())` 传递到 `_make_output`。 当范围的最后一个物理行为空时，`read_file` 返回以 `"\n\n"` 结尾的文本； `"\n".join(...splitlines())` 将其折叠为以单个 `"\n"` 结尾的字符串，新的 `splitlines()` 将其视为终止行而不是空白行。 之前的`split("\n")`保留了那个空字段，所以这是一个行为上的回归，而不仅仅是一个重构。 在当前主分支（真实公共文件编辑器路径，文件 `a\nb\n\n`，3行物理行）上演示： - `view` -> 行 `1 2 3` - `view_range=[1, 3]` -> 行 `1 2`（第3行消失） 类似地，文件 `a\n\n` 显示第2行
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5670#discussion_r4231719155)：在 8a843f6a4 中修复：范围视图现在将读取的内容不变地传递给 _make_output。 五个公共路径案例涵盖未终止/终止行、最后一个空白行和纯空白文件； 每个都比较完整/范围输出并检查带有绝对编号的最终行范围。 修复前：3 次失败/2 次通过。 之后：所有 165 个文件编辑器测试和适用的预提交挂钩均通过。 审核了其他 _make_output 调用者：替换/插入片段和撤消已经在没有此预连接的情况下传递了原始读取内容。 新鲜的CI正在等待中。 _此回复由 AI 智能体 (OpenHands) 代表 Graham Neubig._ 生成
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5670#discussion_r4232311625)：谢谢 - 在 2bffdd076 中应用：仅在“\n”上拆分/连接（匹配 _count_lines），标准化范围片段，无需 splitlines() 往返，并添加换页和 U+2028 案例以及插入右行测试。 所有 168 file_editor 项测试均通过。
- [讨论； 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5670#issuecomment-6083676203)：我不确定以下内容在实践中有多相关，因为它只影响包含一些罕见字符的文件，所以请将其视为需要考虑而非阻挠因素。 --- 修复本身的一个可能问题：`str.splitlines()` 不像REST 编辑器那样分割行。 `_count_lines`、`read_file`、`insert`和`view_range`的检查都遍历了文件，`open()`只在`\n`上失败（加上通用换行符`\r\n`/`\r`).`splitlines()`也失败在`\x0b`、`\x0c`、`\x1c`–`\x1e`、`\x85`、`\u2028`和`\u2029`。 因此，包含其中之一的任何文件现在都会显示与 `insert`/`view_range` 使用的行号不同的 `view` 行号。 换页符确实出现在一些带有分页符的 C/Python 源代码中，并且 `\u2028` 偶尔出现在 JS/JSON 字符串中。 转载在此 PR 的头部 (`907994706`)，原始 `vi
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5670#issuecomment-6085051479)：审核反馈已得到解决，所有审核线程均已解决。 所有代码检查都通过了（file_editor次测试，168/168，预提交，工具测试，集成测试）。 唯一剩下的不可通过的门是`Validate PR description`，它需要在描述中的`HUMAN:`和`AGENT:`之间有一个简短的人写注释。 该部分专为人类作者保留，因此AI 智能体不应填写 - 在合并前需要作者的一行注释。_此评论由AI 智能体 (OpenHands) 代表@gneubig._ 生成

<a id="5579-featacp-discover-an-acp-agents-default-and-available-models-and-restore-gemini-model-handling"></a>

### ＃5579：feat(acp)：发现ACP 智能体的默认和可用模型（并恢复Gemini模型处理）

- 提交：`6d51e7262fc234586ff5e8e519ce5a658d334cdf` (2026-10-09T13:00:08-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5579).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5579)。 族：F01、F03、F04、F05、F06、F07、F09、F12、F18、F19、F20、F21、F22、F23、F24、F30、F31、F32、F33、F34。

陈述意图：

> - **`POST /api/acp/models`**（新`acp_router.py`）采用`agent_settings`加上相同的`secrets`地图作为对话开始（`LookupSecret`引用存储的机密工作）。 它返回 `ACPModelDiscovery`: `current_model_id` （服务器自己的默认值）、`available_models`、`agent_name`/`agent_version`、`supports_runtime_model_switch` 和 `error`（`ACPAuthRequired` / `ACPStartupTimeout` / `ACPSpawnError` / `ACPInitError`，在 200 响应中）。
>   - 成功的结果会缓存 5 分钟，根据命令键入并解析凭据值； 相同的并发请求共享一次运行，一次最多运行两次，并且 `refresh: true` 绕过缓存。
>   - 当对话在容器 (`conversation_runtime="docker"`) 中运行时返回 501。
> - **`openhands.sdk.agent.acp_model_discovery.discover_acp_models`** 在一个临时会话中运行常规 `ACPAgent.init_state`，因此环境组装、 机密注入、文件凭据、认证方法选择和 npx 缓存的行为与对话中完全相同。
>   - 它忽略`acp_model`、MCP服务器和智能体上下文，并在wa之后删除其目录

更改的路径：

- `clients/typescript/endpoint-audit.config.json`
- `clients/typescript/src/__tests__/api-clients.test.ts`
- `clients/typescript/src/client/acp-client.ts`
- `clients/typescript/src/clients.ts`
- `clients/typescript/src/index.ts`
- `clients/typescript/src/models/acp-model-discovery.ts`
- `clients/typescript/src/models/acp.ts`
- `openhands-agent-server/openhands/agent_server/acp_router.py`
- `openhands-agent-server/openhands/agent_server/api.py`
- `openhands-sdk/openhands/sdk/__init__.py`
- `openhands-sdk/openhands/sdk/agent/acp_agent.py`
- `openhands-sdk/openhands/sdk/agent/acp_contracts.py`
- `openhands-sdk/openhands/sdk/agent/acp_model_discovery.py`
- `openhands-sdk/openhands/sdk/agent/acp_models.py`
- `openhands-sdk/openhands/sdk/llm/auth/openai.py`
- `openhands-sdk/openhands/sdk/settings/__init__.py`
- `openhands-sdk/openhands/sdk/settings/acp_providers.py`
- `tests/agent_server/test_acp_router.py`
- `tests/sdk/agent/fake_acp_models_server.py`
- `tests/sdk/agent/test_acp_agent.py`
- `tests/sdk/agent/test_acp_conformance.py`
- `tests/sdk/agent/test_acp_model_discovery.py`
- `tests/sdk/llm/auth/test_openai.py`
- `tests/sdk/settings/test_acp_providers.py`

链接问题接受上下文：

- [#5578](https://github.com/OpenHands/software-agent-sdk/issues/5578): ACP: 让客户端在对话之前发现 ACP 智能体's 默认和可用模型 — 当前状态关闭，关闭于 2026-10-09T17:00:10Z。

> - [ ] `POST /api/acp/models` 对于 claude-code、codex、gemini-CLI、kimi-code、pi 和 opencode，返回 `current_model_id` 和 `available_models`。 - [ ] 缺少凭据在 200 响应中返回为 `error.code == "ACPAuthRequired"`。 - [ ] 存储的机密可以通过引用 (`LookupSecret`) 传递，就像在对话开始时一样。 - [ ] 双子座会议再次列出他们的模型并尊重所请求的模型。 ### 考虑的替代方案仅使用每个对话 `available_models`（在对话内部提供帮助，而不是在配置智能体时提供帮助），或手动保持精选列表最新（不能遵循依赖于凭据的目录）。 ### 优先级/严重性中 ### 估计范围中 ### 功能区域智能体 API / 核心功能 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5579#issuecomment-6044962447)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5579#pullrequestreview-5471784979)：_此评论由 AI 智能体 (OpenHands) 发布。_ 已评论头 `39c7ed822b2972fa0f556c0f5e7646762657016d`。 端点、client-ahead 声明和弃用项全部签出。 没有阻塞发现。### 我验证的内容 - **`POST /api/acp/models`** - 新的 `acp_router.py` 重用了会话启动 `secrets` 形状（包括 `LookupSecret` 引用）以及存储登录绑定，返回错误而不是在启动/认证失败时作为 HTTP 错误，且在 `conversation_runtime == "docker"` 时明确返回 501 错误。 缓存键覆盖了命令/参数/会话模式/隔离/文件秘密/已解决-机密-值，因此新的凭据重新探查 (`test_new_credentials_ask_the_server_again`)。 - **ACP 0.12 回归** — 值得指出，因为它正是这个 PR 的微妙部分。 我安装了`agent-client-protocol==0.12.1`并且

<a id="5671-testintegration-validate-hard-reset-semantics-in-c02"></a>

### ＃5671：test(integration)：验证 c02 中的硬重置语义

- 提交：`e8ad54729e43ca767911e28f8e350a3c3eb84c78` (2026-10-09T13:26:46-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5671).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5671)。 系列：无需产品运行时间。

陈述意图：

> - 使 c02 的硬重置触发器具有确定性，而不依赖于模型生成的事件计数
> 验证实际的重置语义：保留系统提示词，忘记所有其他先前的历史，插入摘要之后，然后产生一个系统首 LLM 请求
> - 验证继续执行和稍后的正常状态上下文压缩，以保留硬重置摘要； 调整集成 README
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `330441825052` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -1581 +1581 @@
> -模式 Event oneOf=[ServerErrorEvent,ACPToolCallEvent,上下文压缩，CondensationRequest,CondensationSummaryEvent,ConversationErrorEvent,ConversationStateUpdateEvent,HookExecutionEvent,LLMCompletionLogEvent,ActionEvent,MessageEvent,AgentErrorEvent,ObservationEvent,UserRejectObservation,SystemPromptEvent,StreamingDeltaEvent,TokenEvent,InterruptEvent,PauseEvent]
> 模式事件 oneOf=[ServerErrorEvent,ACPToolCallEvent,上下文压缩，CondensationRequest,CondensationSummaryEvent,ConversationErrorEvent,ConversationStateUpdateEvent,HookE

更改的路径：

- `tests/integration/README.md`
- `tests/integration/tests/c02_hard_context_reset.py`

链接问题接受上下文：

- [#5669](https://github.com/OpenHands/software-agent-sdk/issues/5669)：修复系统提示词保存后的 c02 硬重置断言 — 当前状态已关闭，已关闭 2026-10-09T17:26:48Z。

> - [ ] c02 中的第一次硬重置不再依赖于生成特定数量事件的测试模型：设置确定性地达到硬重置条件（例如通过直接构造对话状态），因此集成测试不会随模型行为而变化。 - [ ] c02 中的第一个上下文压缩通过语义而非 `summary_offset == 0` 验证为硬重置：前导 `SystemPromptEvent` 不会被遗忘，系统提示词之后的所有预重置历史都被遗忘，并且生成的摘要立即插入到保留的系统提示词之后（偏移量等于系统提示词的位置）。 - [ ] c02 验证投影后重置 LLM条消息的对话 `system`角色的请求 - [ ] c02验证重置后对话继续成功，并且在没有忘记硬重置总结事件的情况下，后续真实（模型驱动）上下文压缩发生。 后面的上下文压缩没有在特定的偏移量上断言。 - [ ] `tests/integration/README.md` 的 `c02_hard_context_reset` 条目描述当前合约：保留主导系统提示词，在其后插入摘要，并忘记剩余的预重置历史记录。 - [ ] 测试通过具有实际 LLM 的 `condenser-test` 模式下的真实集成运行器，断言所依赖的公共 `Condensation` 字段（`forgotten_event_ids`、`summary_offset`、`summary_event`、`summary`）仍然可用。 - [ ] 更改仅限于 c02 集成测试代码和集成测试文档：n

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5671#issuecomment-6080909583)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#pullrequestreview-5472334970)：只是有一些评论
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5671#pullrequestreview-5472984410)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围测试更改为 `tests/integration/tests/c02_hard_context_reset.py` 及其 README 条目，位于拥有 SDK/condenser 及其集成工具的存储库中。 范围内。 ## 代码审查（干净）我阅读了`AGENTS.md`、`.agents/skills/custom-codereview-guide.md`和工作区中的上下文压缩器运行时。 重写断言与实际实现匹配：- `LLMSummarizingCondenser.hard_context_reset` 保留了 `SystemPromptEvent` (`preserve = system_idx + 1`) 并在该位置插入摘要，因此测试的 `summary_offset == system_index + 1` 和“忘记非系统历史”检查描述了实际行为（而不是过时的 `summary_offset == 0` 合同）。- `View.apply` / `append_event` 生成了断言的 `[system, summary]` 重置后视图
- [评论； APPROVED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5671#pullrequestreview-5473232486): _该评论由一个AI发布智能体 (OpenHands)._ ## 范围仅限测试，对 `tests/integration/tests/c02_hard_context_reset.py` 和其 `tests/integration/README.md` 的条目，以及所有者拥有 SDK/condenser 和其集成框架的仓库进行更改。 范围内。 ## 评估这是一次重新审查。 自上次审查以来，其他人发布了新的证据，因此我重新建立了可变状态，而不是信任之前的传递。 之前阻止的唯一一个因素现在得到了满足：`condenser-test`集成器运行在精确的头 `5361a8350`（运行 `37963881263`，`Run Integration Tests condenser-test` 结论 `success`）且100%通过——`litellm_proxy_openai_gpt_5.5` 4/4 (`c01`跳过，模型缺乏扩展思考）且`litellm_proxy_anthropic_claude_sonnet_4_6` 5/5——这是关联问题 #566 的接受标准
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975764)：由于condense()移到第一个run()之前，硬重置只能看到[系统，用户]。 之前，它会跑过一个真实的智能体转弯，因此行动/观察（以及推理项）会通过摘要器，而下一个请求则需要处理剩余的内容。 那是我实际上期望打破的部分，它不再被覆盖。 我们能否保持确定性设置，但在第一个 condense() 之前转一个智能体圈？
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975774)：我喜欢现在这是确定性的，但我在生成的视图上运行了 `_get_forgotten_events`，它忘记了智能体的“hello world”加上标记 0-5。 动作/观察对（索引3-4）从未落在范围内，因此我们失去了对正常上下文压缩从其结果中分裂工具调用的情况的覆盖。 也许将标记放在智能体回合之前，或者调整 keep_first 以便范围从动作开始？
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975778)我不认为这正是它 fallback 的原因。 这里的观点只是 [系统，用户]因此，操作索引为 {0, 1, 2} `find_next(4)` 提出了 ValueError 在我们甚至还没进行最小进度检查之前。 同样的事情发生在 keep_first1， fwiw。 请输出简体中文译文。 ```suggestion # The first view is only [system, user], so no valid forgetting boundary # exists past keep_first and the request falls back to a hard reset. # Later, deterministic context markers make a normal condensation viable. ```
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975795)：这里没有实际的标记，我们从不看摘要。 要么删除它，要么放入 token 并检查它是否显示在 `hard_reset.summary` 中？ 这将使我们至少对内容进行一次检查，而不仅仅是 ID。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975802)：nit：被遗忘的id检查 + 精确[系统，]总结id检查已经把这个问题定下来了，所以apply()比较和events_to_messages检查对我来说感觉冗余。 可以扔掉它们。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975804): nit: View 通过 `event.apply(...)` (view.py:122) 构建其事件，因此将 apply() 与 apply() 进行比较。 如果apply()本身是错误的，这仍然可以通过。 检查汇总位置，忘记的id直接消失会更有意义。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975808)：nit：这两个都是从`openhands.sdk.event`导出的，这就是c01使用的：```python from openhands.sdk.event import Condensation, LLMConvertibleEvent, SystemPromptEvent ```
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4231975816)：次要：由于 ConversationRunError，错误已经会爆炸，但达到最大迭代次数只会设置 ERROR 而不会触发，也没有检查。 也许在每个 run() 之后断言状态为 FINISHED？
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232314946)：同意。 在 5361a8350 版本中，测试现在发送实际指令，运行智能体次，捕获该状态，然后才调用 condense()，因此硬复位再次总结了一个实际智能体转动。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232315311)：已在 5361a8350 中修复。 重置后的新轮次现在是一个显式的终端工具轮次，keep_first=4保护了[系统、摘要、智能体轮次、动作]（系统=0，因此范围的起始点是索引4处的观测结果），这是为什么动作/观察对被保留而不是搁置的原因。 我还将尾随填充切换为确定性标记消息，因此运行与模型无关。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232315743)：你是对的 - 就是这样。 find_next(4) 在进行任何进度检查之前，在 [ 系统、用户 ] 视图上提出 ValueError。 通过首先运行真正的智能体回合在 5361a8350 中解决，现在评论说明了真正的原因。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232316215)：在 5361a8350 中完成：重置回合的指令要求智能体回显 HARD_RESET_MARKER_7F3A，并且 verify_result 断言 token 出现在 hard_reset.summary 中。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232316649)：删除了 5361a8350 中冗余的 apply()/events_to_messages 比较。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232317066)：在 5361a8350 中进行了重新设计，以直接断言可观察到的效果：摘要位于系统提示词之后，恰好忘记了非系统历史记录，并且受保护的前缀完好无损。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232317733)：切换到 5361a8350 中的 openhands.sdk.event 导出。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#discussion_r4232318166)：在 5361a8350 中的每个 run() 之后添加了 _assert_finished() 检查，因此最大迭代 ERROR 现在使测试失败，而不是默默地通过。
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5671#issuecomment-6081047991): # 🧪 上下文压缩器测试结果 **总体成功率**: 88.9% **总成本**: $0.62 **模型已测试**：2 **时间戳**：2026-10-09 12:38:16 UTC <details> <summary>📁详细日志和工件</summary> 单击下面的链接可访问显示完整的详细代理/LLM 日志每个模型的推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37930376517) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37930376517) ## 📊 摘要\| 型号 \| 总体 \| 测试已通过 \| 已跳过 \| 总 \| 成本 \| token \| \|--------\|---------\|-------------\|---------\|--------\|------\|--------\| \
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#issuecomment-6085051907)：VascoSch92 的审核反馈已得到解决，所有审核线程均已解决（请参阅每个线程的回复）。 现在的 c02 测试：在显式压缩之前运行真​​实的智能体回合，以便硬重置总结实际的回合； 使用keep_first=4，因此后面的上下文压缩是正常的，并且动作/观察对被保留； 具有确定性、独立于模型的标记事件的焊盘； 断言重置摘要实际上带有标记token； 直接检查系统优先放置； 并在每个 run() 之后断言 FINISHED。 本地验证：c02 在 claude-sonnet-4-6 和 gpt-5.5 上重复通过，完整的上下文压缩器套件（c01-c05）是绿色的。 唯一剩下的不可通过的门是`Validate PR description`，它需要在描述中的`HUMAN:`和`AGENT:`之间有一个简短的人写注释。 该部分是为人类保留的
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5671#issuecomment-6085782607): # 🧪 上下文压缩器测试结果 **总体成功率**: 100.0% **总成本**: $1.07 **模型已测试**：2 **时间戳**：2026-10-09 17:20:03 UTC <details> <summary>📁详细日志和工件</summary> 单击下面的链接可访问显示完整的详细代理/LLM 日志每个模型的推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37963881263) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37963881263) ## 📊 摘要\| 型号 \| 总体 \| 测试已通过 \| 已跳过 \| 总 \| 成本 \| token \| \|--------\|---------\|-------------\|---------\|--------\|------\|--------\|
- [讨论评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5671#issuecomment-6085792040)当前头节点上下文压缩器证据已到位。 重新运行了 `condenser-test` 通过当前头的标签进行工作流 `5361a8350`- 运行：  https://github.com/OpenHands/software-agent-sdk/actions/runs/37963881263  (结论：成功) - 总的成功率： **100.0%** - `litellm_proxy_openai_gpt_5.5`4/4通过了（）`c01` 跳过 - 模型不支持扩展思考) `litellm_proxy_anthropic_claude_sonnet_4_6`5/5通过 `c02_hard_context_reset` 通过真实世界 `condenser-test` 带有实际的集成运行器 LLM on commit `5361a8350`, 满足 issue #5669 的接受标准。 (The `c04` 在 GPT-5.5 的日志中，你可能会看到一些无关的、模型相关的错误 `c04` 在 #5675 中单独设置的。 它不是这个的一部分 PR_这是由人工智能生成的评论智能体 (OpenHands代表 @gneubig

<a id="5609-release-v1540"></a>

### #5609：发布 v1.54.0

- 提交：`1d471742ea7be017d013eaaa3080f5d28d5490cb` (2026-10-09T14:36:37-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5609).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5609)。 Families: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34.

陈述意图：

> ## 发布 v1.54.0
> 
> 此 PR 准备版本 **1.54.0** 的发布。
> 
> **启动者：** @neubig
> 
> ### 发布清单
> - [x] 版本设置为 1.54.0 — 四个 Python 软件包和 TypeScript 客户端已同步。
> - [x] 修复任何弃用截止日期（如果存在）- [弃用截止日期已在当前头 298227f40](https://github.com/OpenHands/software-agent-sdk/actions/runs/37801967286) 上传递。
> - [ ] 集成测试通过（标记为 `integration-test`） — [ 发布集成套件在先前的头 e2947c6](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800266455) 上传递； 合并 main 后需要重新验证。 普通的 TypeScript 集成检查已经 [ 通过了当前的 head ](https://github.com/OpenHands/software-agent-sdk/actions/runs/37801967042)，但不能替代此版本套件。
> - [ ] 行为测试通过（标记为 `behavior-test`） — [ 发布行为套件在之前的头 e2947c6](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800267366) 上通过； 需要对当前头部进行重新验证。
> - [ ] 示例测试通过（标有“测试示例”

更改的路径：

- `clients/typescript/package-lock.json`
- `clients/typescript/package.json`
- `clients/typescript/src/generated/agent-server-schema.ts`
- `openhands-agent-server/pyproject.toml`
- `openhands-sdk/pyproject.toml`
- `openhands-tools/pyproject.toml`
- `openhands-workspace/pyproject.toml`
- `tests/integration/tests/c04_token_condenser.py`
- `uv.lock`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6063190694)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6063184850)：## 🔒 发布安全扫描 ### 🔒 批准漂移（检查时间与使用时间） **❌ 7 finding(s)** 基线：`v1.53.0` — 21 合并 PR(s)在范围内。 > ⚠️ 范围内的 8 个第一父级 commit(s) 与 `(#N)` 压缩约定不匹配，并且经过 **not** 审核（合并/变基合并，或丢失的 `(#N)` 后缀）。 这些是盲点 - 检查它们： > - 将远程跟踪分支“origin/fix/c04-token-上下文压缩器-确定性”合并到 rel-1.54.0 > - chore(release)：在主合并后重新生成智能体-server 合约 > - 将远程跟踪分支“origin/main”合并到 rel-1.54.0 > - chore(release)：主合并后重新生成智能体-server 合约 > - 将 main 合并到版本 v1.54.0 > - fix(release)：合并 main 后重新生成 API 合约 > - 将 main 合并到 rel-1.54.0 > - 版本 v1.54.0 \| PR \| 发现\| 详情 \| \| -- \| ------- \| ------ \| \| #
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6063296571): # 🧪 集成测试结果 **总体成功率**: 100.0% **总成本**: $1.96 **测试模型**: 5 **时间戳**: 2026-10-08 15:28:09 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800266455) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800266455) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800266455) - **litellm_proxy_deep
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6063438649)：将当前 main (c980344bc78e21d5625ec4e987680d87c6c56f7f) 合并到此发布分支中，并在 298227f40 中重新生成 TypeScript 合约。 智能体-服务器-API失败是因为CI测试了包含新InstalledCanvasExtensionResponse.requested_ref字段的合成合并，而准备好的合同早于那个主要变更。 生成后进行检查：智能体-server-API 现在已通过，所有 44 个 canvas_extensions_router 测试和适用的预提交挂钩也已通过。 Fresh CI 正在运行。 审批漂移的安全门仍未解决； 没有任何门被绕过。 发布和合并仍有待用户批准。 _此评论由 AI 智能体 (OpenHands) 代表 user._ 生成
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6063554165): # 🧪 行为测试结果 **总体成功率**: 96.0% **总成本**: $12.83 **测试模型**: 5 **时间戳**: 2026-10-08 15:41:34 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800267366) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800267366) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37800267366) - **litellm_proxy_deepsee
- [讨论评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6064661343): 里程碑检查单跟进： - 当前主干集成/行为验证：  https://github.com/OpenHands/software-agent-sdk/actions/runs/37810776941  当前-头示例重试：https://github.com/OpenHands/software-agent-sdk/actions/runs/37810823497.  前一次运行通过了68/70。 都失败了 HTTP 500 创建云沙盒，不是断言失败。 - 要求的发布注释条目#5503现在明确记录在检查清单中，并且自动前置查询已验证。 批准-漂移分流（安检门仍然堵塞； 没有豁免或批准：- #5538：仅在批准后提交的唯一提交添加了 Final[str] 两个常量的注释：  https://github.com/OpenHands/software-agent-sdk/commit/21ebbf4c4c679e0b4b345e4e3b0ce688e540c01e  - #5551: 只有自动删除 .pr 的操作validation.md:  https://github.com/O
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6065564481): # 🧪 集成测试结果 **总体成功率**: 92.6% **总成本**: $14.16 **测试模型**: 5 **时间戳**: 2026-10-08 17:36:29 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37810776941) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37810776941) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37810776941) - **litellm_proxy_deep
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6080786058)：将 main 合并到 3ba77661e 中的发布分支中，然后在 CI 识别漂移后重新生成源衍生的 TypeScript API 合约。 生成的更改只是反映合并的 X-Expose-机密行为的 ProfileDetailResponse 文档。 Source OpenAPI 导出、generate:智能体-server-API、check:智能体-server-API 和 git diff --check 在本地传递。 Fresh PR CI 将验证更新后的头。 发布集成/行为/示例和图像安全验证仍有待确定； 这并不标志着那些门已经通过。 格雷厄姆报告说，他亲自审查了之前标记的批准漂移并认为这是可以接受的； 此评论并未绕过或重新分类自动审核。 _此评论由 AI 智能体 (OpenHands) 代表 Graham Neubig._ 生成
- [讨论评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6081327482) 验证本地合并的发布分支 13a6ade18 与 #5670 (9079947)，#5671 (5f05244)，和 #5675 (0eaa7a3) 在一个隔离的分离分支中工作树; 不允许在此处进行任何版本分支的更改或合并 PR 已经被推了回归测试通过。- c02 和 c04 都通过了 GPT-5.5 (2/2, $0.03) 和 Claude Sonnet 4.6 (2/2, $0 OSV 添加/升级的依赖项中的漏洞。 这是不图像扫描。- 审批漂移扫描器仍然标记了六项之前讨论过的 PR; 格雷姆已经报告审查了它们，但扫描仪没有基于评论的豁免，因此没有改变。- 用户要求取消了移除工作。 此候选中不包含 pip 删除代码。 完整示例 CI 在 #5670 上进行审查
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6085986678): # 🧪 集成测试结果 **总体成功率**: 95.9% **总成本**: $1.98 **测试模型**: 5 **时间戳**: 2026-10-09 17:33:14 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37966674753) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37966674753) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37966674753) - **litellm_proxy_deeps
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086038002)：合并当前main后发布状态更新。 ** 主分支合并到发布分支** (6 次提交：#5673，#5182 安全分析事件，#5683，#5670 文件编辑换行，#5579 ACP 模型发现，#5671 c02 硬复位)。 合并是干净的（没有冲突）。 **重新生成了Agent ServerTypeScript合约**（`73d271a02`）。 合并添加了 `SecurityAnalysisEvent` 和 ACP 模型发现界面，这使得签入的合约变得陈旧； `agent-server-api` 检查现在传递到新头 (`Checked-in Agent Server contract is current.`)。 仅内容差异； 保留固定图像源标头 (`ghcr.io/openhands/agent-server:1.54.0-python`)。 **通过其标签在最后一个头 `73d271a02`** 上重新调度释放门： - `integration-test`、`behavior-test`、`test-examples` — 正在运行。 - `security-scan` — 仍然失败 o
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086075323): # 🧪 集成测试结果 **总体成功率**: 100.0% **总成本**: $1.95 **测试模型**: 5 **时间戳**: 2026-10-09 17:38:57 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37967286572) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37967286572) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37967286572) - **litellm_proxy_deep
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086285770): # 🧪 行为测试结果 **总体成功率**: 96.0% **总成本**: $13.47 **测试模型**: 5 **时间戳**: 2026-10-09 17:51:23 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37966691792) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37966691792) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37966691792) - **litellm_proxy_deepsee
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086329272): # 🧪 行为测试结果 **总体成功率**: 96.0% **总成本**: $11.45 **测试模型**: 5 **时间戳**: 2026-10-09 17:53:54 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37967306167) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37967306167) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37967306167) - **litellm_proxy_deepsee
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086496942): # 🧪 集成测试结果 **总体成功率**: 100.0% **总成本**: $1.84 **测试模型**: 5 **时间戳**: 2026-10-09 18:03:56 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37970169569) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37970169569) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37970169569) - **litellm_proxy_deep
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086718764): # 🧪 行为测试结果 **总体成功率**: 100.0% **总成本**: $10.47 **测试模型**: 5 **时间戳**: 2026-10-09 18:18:21 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37970187854) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37970187854) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37970187854) - **litellm_proxy_deepse
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5609#issuecomment-6086949062)：当前头 `e81e8eafc` 上的释放门为绿色。 **#5675 (c04 token-上下文压缩器决定论) 合并到发布分支.**集成测试更改（`keep_first=2`，确定性上下文压缩断言）现在位于 `rel-1.54.0` 中。 它是已审查的PR分支的合并； 根据释放技能，发布分支是唯一发布的东西，并且 PR 本身已获得批准（VascoSch92）并且是干净的。 **`e81e8eafc`上的标签门控套件 - 所有通过：** - `integration-test` ✅（所有 5 个模型） - `behavior-test` ✅（所有 5 个模型） - `test-examples` ✅ - `agent-server-api` ✅ （主合并后重新生成合约） **仅剩下红色检查：`security-scan`**，并且仅其批准漂移一半。 调查结果是六个预先存在的PR（#5538、#5551、#5357、#5429、#5407、#5263），它们的头在最后一次人类批准后发生了变化； 扫描仪重新

<a id="5682-fixagent-server-reject-blank-and-redacted-secret-values"></a>

### #5682: fix(agent-server): 拒绝空白和已脱敏机密值

- 提交：`c1c8c1c27824b7566861ea0f8e6900e4ae2944a9` (2026-10-09T21:04:31+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5682).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5682)。 家庭：F18、F19、F32。

陈述意图：

> - 在持久化之前使用 HTTP 422 拒绝空白和已脱敏占位符值。
> - 当无效的更新插入被拒绝时，保持现有的机密值和描述不变。
> 通过路由器和实时服务器测试覆盖新-机密和现有-机密行为。

更改的路径：

- `openhands-agent-server/openhands/agent_server/settings_router.py`
- `tests/agent_server/test_settings_router.py`
- `tests/cross/test_remote_conversation_live_server.py`

链接问题接受上下文：

- [#5623](https://github.com/OpenHands/software-agent-sdk/issues/5623): [Bug]: PUT  /api/settings/secrets 用空格或换行**********返回200，并清除机密 instead of 422 — current state closed, closed on 2026-10-09T19:04:33Z.

> - [  ]  PUT 与 `value`  `""`仅包含空白字符的或 `**********` 不改变存储，返回422，或者（占位符覆盖现有名称）保留存储的值 [  ] 没有序列的 PUTs 留下了一个名字，该名字被列出，但读取答案是 404 [  ] 路由器测试覆盖了现有的占位符机密以及一个新名称的空值 [  ] 的 `F18.secret-empty-value` bullets in `F18-settings-and-secrets.md` 移除已知错误标记后，通过以下方法安装 uv  同步在主版本 2804c12 的 checkout 中， 上下文原因：- `openhands-agent-server/openhands/agent_server/settings_router.py:526` (`create_secret`) 验证名称并继续 `secret.value.get_secret_value()` to `store.set_secret` (540) unchecked; `SecretCreateRequest.value` (`openhands-sdk/openhands/sdk/settings/api_models.py:260`) 是裸的 `SecretStr`. - `FileSecretsStore.set_secret` (`openhands-agent-server/openhands/agent_server/persistence/store.py:612-616`) builds `CustomSecret(secret=SecretStr(value))`. `CustomSecret._validate_secret` (`persistence/models.py:505-510`) calls `validate_secret`，它映射空的、仅空白的和 `**********` to `None` (`openhands-sdk/openhands/sdk/utils/pydantic_secrets.py:108`). 该条记录被保存为 `secret: null` 和新的描述 `get_secret` 返回 `None` for a null value (`store.py:585`), 因此读取路由返回 404 (`settings_router.py:516`, while `list_secrets` 列出所有条目（`settings_router.py:484-488`). Suggested fix: in `create_secret`, 答案为 422，当值为空或

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5682#pullrequestreview-5474248198)：谢谢！

<a id="5614-ci-upgrade-integration-matrix-to-deepseek-v41-flash"></a>

### #5614: CI: 将集成矩阵升级到 DeepSeek V4.1 Flash

- 提交：`9929c14e7d2f4882cd257de2a401235ef276b865` (2026-10-09T15:43:04-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5614).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5614)。 系列：无需产品运行时间。

陈述意图：

> - 使用 V4.1 Flash 替换默认的 DeepSeek 型号 ID、显示名称和 litellm_proxy 型号映射。
> - 更新集成覆盖文档； 其他型号和上下文压缩器默认值不变。

更改的路径：

- `.github/workflows/integration-runner.yml`
- `tests/integration/README.md`

链接问题接受上下文：

- [#5613](https://github.com/OpenHands/software-agent-sdk/issues/5613)：将集成测试矩阵升级到 DeepSeek V4.1 Flash — 当前状态已关闭，已关闭 2026-10-09T19:43:06Z。

> - `.github/workflows/integration-runner.yml`中的[]`DEFAULT_MODEL_IDS`包含`deepseek-v4.1-flash`，不再包含`deepseek-v4-flash`。 - [ ] 内联 `MODELS` 映射解析 `deepseek-v4.1-flash` id 以显示名称 `DeepSeek V4.1 Flash` 和代理模型 `litellm_proxy/deepseek/deepseek-v4.1-flash`。 - [ ] 其他默认模型 ID（`gpt-5.5`、`minimax-m2.7`、`gemini-3.1-pro`、`claude-sonnet-4-6`）和 `DEFAULT_CONDENSER_MODEL_IDS`（`gpt-5.5`、`claude-sonnet-4-6`）保持不变。 - [ ] `tests/integration/README.md` 在覆盖范围列表中命名 DeepSeek V4.1 Flash（不是 V4 Flash），并且仍然报告 5 个型号。 - [ ] 自动化测试调用实际矩阵解析器（不是表的重复副本），并断言如果没有 `model_ids`，则默认集包括具有显示名称 `DeepSeek V4.1 Flash` 和代理模型 `litellm_proxy/deepseek/deepseek-v4.1-flash` 的 `deepseek-v4.1-flash`，并且显式 `model_ids=deepseek-v4.1-flash` 选择解析为同一条目。 - [ ] 的 resolver保留其失败快行为：未知模型标识仍然以`Unknown model id`消息返回非零值。- [ ] 仓库中没有其他`deepseek-v4-flash`引用，没有正在运行或历史评估运行/产物被重命名或重新生成。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5614#issuecomment-6065470608)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5614#pullrequestreview-5460920183)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论：`ci: upgrade integration matrix to DeepSeek V4.1 Flash` **范围门：** 在范围内。 这是该存储库拥有的存储库内 CI/eval 配置和文档更改。 无需跨存储库或产品/架构决策。 **对头`a8e5ba425e9e72e77a1290aff70873da5b7205ff`进行了验证：** - 从`.github/workflows/integration-runner.yml`中提取了实际的内联矩阵解析器并执行了它：- 默认集(`DEFAULT_MODEL_IDS`)将`deepseek-v4.1-flash`解析为显示名称`DeepSeek V4.1 Flash`、代理模型`litellm_proxy/deepseek/deepseek-v4.1-flash`和运行后缀`deepseek_v4_1_flash_run`。- 明确`model_ids=deepseek-v4.1-flash`也解析为相同条目。- 默认集不再包含`deepseek-v4-flash`。- 失败快行为保留

<a id="5675-testintegration-make-token-condensation-deterministic"></a>

### ＃5675：test(integration)：使token 上下文压缩确定性

- 提交：`1cfba2117e92730b0fe1c32520a39aad8611bb8c` (2026-10-09T15:47:33-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5675).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5675)。 系列：无需产品运行时间。

陈述意图：

> - 用两个单独的 Python 终端命令替换 1,000 次调用指令，每个命令打印 2,000 次重复的短语。
> - 将 token 阈值提高到 6,000 并保持种子上下文较小，以便单个工具结果可以在每个 CI 模型上大幅清除它。
> - 设置 `keep_first=2`，以便用户指令在第一个上下文压缩后继续存在，并且第二个命令仍然运行。
> - 将迭代上限从 10 次提高到 20 次，这样总结者称它们会触发两次压缩，并且工具的转动次数都符合预算。
> - 需要在 `verify_result` 中至少进行两次缩合，因此第二个循环实际上是强制执行的，而不仅仅是观察到的。
> - 删除过时的长循环拒绝跳过。

更改的路径：


链接问题接受上下文：

- [#5674](https://github.com/OpenHands/software-agent-sdk/issues/5674)：使 c04 token-上下文压缩器评估在模型之间具有确定性 - 当前状态已关闭，已关闭 2026-10-09T19:47:35Z。

> - [  ]  `c04_token_condenser` 不再依赖模型提供冗长的重复工具循环：[no longer depends on the model volunteering a long repetitive tool loop:] `1..1000` echo 指令已被更改为一个确定性机制（或模型无关指令），该机制可靠地构建一个超出的视图 token 每个支持的矩阵模型上的阈值 [  ] 在断言之前上下文压缩，测试测量了活跃视图的智能体  LLM通过现有的仓库实现真正的分词器 token-count path (e.g. `get_total_token_count(view.events, agent_llm)`) 并确认其超过上下文压缩器'有效' `max_tokens` (5000); 低于阈值的视图通过测试时，会有一个明确的原因，而不是一个误导性的token 计数可能不起作用 [  ] 测试执行正常代理/冷凝器路径 LLM calls (智能体运行 + `LLMSummarizingCondenser`), 不仅是一个合成的 `View`. - [  ]  `verify_result()` 失败了 `Condensation` 被生产出来，以及当上下文压缩只有在成功的情况下，它才会发生上下文压缩是 token- 驱动并总结了过大的 event(s) (e.g. 非空 `forgotten_event_ids` 包括故意扩大的事件 [  ] 的上下文压缩器 keeps `max_size` 足够高，以至于单凭事件计数就无法触发上下文压缩因此，测试专门测试了 token-based 上下文压缩。 - [  ] 运行  `condenser-test` 拉取请求报告中的工作流 `c04_token_condenser` 传递两个 `gpt-5.5` 和 `claude-sonnet-4-6`; 在任何模型上失败的运行都不满足这个 [  ]  `c01_thinking_block_condenser`, `c02_hard_context_reset`, `c03_delayed_condensation`, and ```c05_size_cond

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5675#issuecomment-6081241320)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5675#pullrequestreview-5471430585): _此评论由 AI 智能体 (OpenHands) 发布。_ ### 范围此更改放置正确：它仅编辑 c04 上下文压缩器集成测试 (`tests/integration/tests/c04_token_condenser.py`)，与链接问题 #5674 中的范围匹配（标签 `bug`、`priority:medium`、`ready-for-dev`）。 没有运行时上下文压缩器、分词器、打包或公共 API 更改。 ### 评估修订解决了报告的根本原因。 该指令不再要求模型自愿进行 1,000 次迭代的回显循环； 它发出两个有界终端命令（`'token pressure context ' * 1000` 和 `'second context payload ' * 1000`），产生确定性的、与模型无关的输出。 每重复一个词4 token，每条命令的工具结果超过保留的 `max_tokens=5000`，因此上下文压缩由词元数量决定
- [评论； COMMENTED; VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5675#pullrequestreview-5472337886)：一些评论
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4231978286)：上下文压缩步骤也算作一次迭代：`agent.step` 在发出 `Condensation` (agent.py:754-756) 后提前返回，并且循环仍然执行 `iteration += 1` (local_conversation.py:2000)。 因此，快乐路径已经是 10 中的 4，并且达到上限以 `MaxIterationsReached` 结束运行。 类似 20 的值仍远低于旧的 50，同时为重试或叙述的步骤留出空间。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4231979941): **L61** ( https://github.com/OpenHands/software-agent-sdk/blob/dc88f65bd57a902359b76372def17ec8063bbff9/tests/integration/tests/c04_token_condenser.py#L61 ): `keep_first=1`只保护索引0，也就是`SystemPromptEvent`，而不是用户消息，所以内联注释是错误的。 我使用 gpt-5.5 和 sonnet-4-6 分词器在 post-command-1 视图 (`[SystemPrompt, UserInstruction, Action1, Observation1]`) 上离线运行 `_get_forgotten_events`。 第一个上下文压缩忘记了`UserInstruction`、`Action1`和`Observation1`，只保留了系统提示词。 仅当 LLM 摘要碰巧保留命令 2 时，命令 2 才会存活。 旧的 1,000 回波循环可以容忍丢失指令； 两步脚本不能。 建议：`keep_first=2`，因此指令始终有效上下文压缩。
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4231980071): **L85** ( https://github.com/OpenHands/software-agent-sdk/blob/dc88f65bd57a902359b76372def17ec8063bbff9/tests/integration/tests/c04_token_condenser.py#L85 ): `verify_result` 仍然通过单个上下文压缩，因此第二个周期（重新设计的原因）永远不会被断言。 PR 主体表示实时跟踪显示两个周期，但 CI 不会捕获回归，其中智能体在第一个摘要之后停止。 由于回调已经在第二个上下文压缩处暂停，我们可以在这里需要 `len(self.condensations) >= 2` 吗？
- [review_comments; 评论； VascoSch92](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4231980258): **L60** ( https://github.com/OpenHands/software-agent-sdk/blob/dc88f65bd57a902359b76372def17ec8063bbff9/tests/integration/tests/c04_token_condenser.py#L60 在第一个 [headroom] 之前工具调用非常小。 我测量了真实智能体 + TerminalTool system 提示词加上这个指令，使用 LiteLLM's token 对于每个 CI 矩阵模型：- GPT-5.5：4,839（161个剩余） MiniMax-M2.7: 4,831 (169 left) - sonnet-4-6 / opus-5: 4,663 (337 left) - gemini-3.1: 4,642 (358 left) - deepseek / kimi: 4,590 (410 left) 这些数字与你在命令1后总计7,985的数字相符载荷大约3k token). 如果系统提示词工具描述增长约160% token, 上下文压缩将在步骤1之前触发工具调用而且，测试因为无关的原因而失败。 我们能否提高阈值（e.g6,000）并确定大小载荷用于匹配，因此 nei
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4232310113)：已在 772e42130 中将上限提高到 20，为正常路径已使用的约 4 次迭代预留余量（上下文压缩步骤也会推进计数器）。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4232310510)：在 772e42130 中设置 keep_first=2，以便用户指令在第一个上下文压缩后继续存在，并且第二个命令仍然运行。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4232310812)：verify_result 现在需要在 772e42130 中至少进行两次缩合。 本地确认：GPT-5.5 和 Sonnet 4.6 都报告了两次凝结。
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5675#discussion_r4232311183)：在 772e42130 中将 max_tokens 提高到 6000 次，将载荷提高到 2,000 次。 一种工具的结果约为 9k token，因此它在每个 CI 模型上都大幅清除了阈值。
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5675#issuecomment-6081339561): # 🧪 上下文压缩器测试结果 **总体成功率**: 77.8% **总成本**: $1.00 **模型已测试**：2 **时间戳**：2026-10-09 12:56:50 UTC <details> <summary>📁详细日志和工件</summary> 单击下面的链接可访问显示完整的详细代理/LLM 日志每个模型的推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37932649746) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37932649746) ## 📊 摘要\| 型号 \| 总体 \| 测试已通过 \| 已跳过 \| 总 \| 成本 \| token \| \|--------\|---------\|-------------\|---------\|--------\|------\|--------\| \
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5675#issuecomment-6082373755): # 🧪 上下文压缩器测试结果 **总体成功率**: 77.8% **总成本**: $0.96 **模型已测试**：2 **Timestamp**：2026-10-09 13:56:24 UTC <details> <summary>📁详细日志和工件</summary> 单击下面的链接可访问显示完整的详细代理/LLM 日志每个模型的推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37939597084) - **litellm_proxy_anthropic_claude_sonnet_4_6**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/37939597084) ## 📊 摘要\| 型号 \| 总体 \| 测试已通过 \| 已跳过 \| 总 \| 成本 \| token \| \|--------\|---------\|-------------\|---------\|--------\|------\|--------\| \

<a id="5291-fixllm-dont-send-stop-words-to-openai-models-on-bedrock"></a>

### ＃5291：fix(llm)：不要向基岩上的OpenAI模型发送停用词

- 提交：`e2bac66be26e94f571f27b71f507e7192720f825` (2026-10-10T12:33:35+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5291).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5291)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - 将 `"openai.gpt-"` 添加到 `SUPPORTS_STOP_WORDS_FALSE_MODELS`，位于 o1/o3/grok-4 旁边。
> - 测试：五个必须删除停用词的 Bedrock ID，一个保留停用词的 Claude-on-Bedrock ID。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/model_features.py`
- `tests/sdk/llm/test_model_features.py`

链接问题接受上下文：

- [#5290](https://github.com/OpenHands/software-agent-sdk/issues/5290): [Bug]: 基于提示词的工具调用在 Bedrock OpenAI 模型（gpt-oss、GPT-5.6、GPT-6 Sol/Luna/Astra）上失败，因为发送了停用词 — 当前状态已关闭，已关闭 2026-10-10T10:33:40Z。

> - [ ] `get_features(...).supports_stop_words` 对于 `bedrock/openai.gpt-oss-120b-1:0`、`bedrock/us.openai.gpt-5.6-sol` 和 `bedrock/{us,global}.openai.gpt-6-{sol,luna,astra}` 来说是 `False` - [ ] 重现不再返回 `stopSequences` 400 - [ ] 基岩上的克劳德仍然得到停用词 ### 主安装方法 uv 同步 (LiteLLM 1.93.0 from `uv.lock`) ### SDK 版本 main @ 5b36cac (OpenHands-SDK 1.49.5) ### Python 版本 3.13.14 ### 型号名称（如果适用） bedrock/openai.gpt-oss-120b-1:0、bedrock/us.openai.gpt-5.6-sol、bedrock/us.openai.gpt-6-sol、bedrock/us.openai.gpt-6-luna、bedrock/us.openai.gpt-6-astra ### 操作系统MacOS ### 最小代码示例 ```python from openhands.sdk import LLM, Message, TextContent from openhands.sdk.tool.builtins.think import ThinkTool # reasoning_effort=None: the locked LiteLLM 1.93.0 would otherwise turn the # default "high" into a `thinking` 字段被 GPT-5.6/GPT-6 拒绝。 MODELS = { "bedrock/openai.gpt-oss-120b-1:0": {}, "bedrock/us.openai.gpt-5.6-sol": {"reasoning_effort": None}, "bedrock/us.openai.gpt-6-sol": {"reasoning_effort": None}, "bedrock/us.openai.gpt-6-luna": {"reasoning_effort": None}, "bedrock/us.openai.gpt-6-astra": {"reasoning_effort": None}, "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0": {}, } msgs = [ Message(role="system", content=[TextContent(text="您是智能体。 使用think工具一次，然后回答。)]), 消息（角色为用户，内容为：[TextContent(文本：“调用think工具，将thought设置为'2+2'，然后告诉我结果。")]), ] for model, extra in MODELS.items(): llm = LLM(模型=model, usage_id

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5291#pullrequestreview-5417452375)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围在范围内。 `openhands-sdk/openhands/sdk/llm/utils/model_features.py` 正是仓库规范指定的模型和提供商能力调整位置，因此该变更属于本仓库。## 变更内容：将 `"openai.gpt-"` 添加到 `SUPPORTS_STOP_WORDS_FALSE_MODELS`。 `model_matches` 对原始模型 ID 进行不区分大小写的子字符串搜索，因此 `bedrock/us.openai.gpt-6-sol` 和 `bedrock/openai.gpt-oss-120b-1:0` 的点分 Bedrock ID 现在解析为 `supports_stop_words=False`，而斜杠形式 `openai/gpt-5` 和裸形式 `gpt-5` 不变。 运行时消费者是 `mixins/non_native_fc.py:59`，只有在 True 时才添加 `stop`，因此这些模型的 Bedrock Converse `stopSequences` 字段不再填充。 这与 #5290 中的根本原因相符。 ## 验证

<a id="5661-fixagent-server-keep-sockets-and-v1-closed-until-deferred-init-completes"></a>

### ＃5661：fix(agent-server)：保持套接字和/v1关闭，直到延迟初始化完成

- 提交：`c4b93299cf2b31c8b5d0b2c5a89965ccc5ff24f9` (2026-10-10T18:34:26+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5661).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5661)。 家庭：F01、F03、F05、F30、F31、F32。

陈述意图：

> - `require_initialized` takes an `HTTPConnection`所以相同的依赖在  HTTP 和 WebSocket routes. HTTP 请求仍然返回 503 状态码。 WebSockets get `WebSocketException(1013 Try Again Later)`在握手被接受之前关闭套接字 `HTTPException` 从一个 WebSocket 依赖项将到达应用的 HTTP 异常处理器，它读取 `request.method` 和失败。
> - 门被固定在上 `/v1` router (after `check_openai_api_key`, 按照相同的顺序 `/api`) 和到其挂载点上的套接字路由器，涵盖本地和远程的会话和bash套接字事件 Docker  注册表。
> - 初始化和非延迟服务器的行为与以前完全相同：一旦 init 为 `ready` 或没有注册 `InitService` 时，依赖关系立即返回。

更改的路径：

- `openhands-agent-server/openhands/agent_server/api.py`
- `openhands-agent-server/openhands/agent_server/init_router.py`
- `tests/agent_server/test_init_router.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5661#issuecomment-6076160145)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5661#pullrequestreview-5479845130): LGTM — 审查了 diff 和周围的路由器接线。 该修复是正确的且范围广泛。 一些注释：**我验证的** - 将 `require_initialized` 切换到 `HTTPConnection` 是正确的调用：现在在 HTTP 和 WebSocket 路由上解析相同的依赖关系，并且提高 `WebSocketException(1013)` （而不是 `HTTPException`）避免了读取 `request.method` 的应用程序级异常处理程序 - 很好的捕获。 - 在路由器安装点（`openai_router` 和 `conversation_registry.sockets_router`）处应用门意味着本地和 Docker 注册表的事件/会话/bash 套接字都被覆盖，而不仅仅是单个路由。 - 依赖顺序与现有的 `/api` 组匹配（`check_openai_api_key` 在 `require_initialized` 之前），因此没有密钥的休眠 pod 仍然会得到 401，而不是泄漏 503 sema

<a id="5703-fixllm-keep-verified-openrouter-models-discoverable"></a>

### ＃5703：fix(llm)：保持已验证的OpenRouter模型可发现

- 提交：`c96875fe3d033efc44b5e6403043251626dd61ef` (2026-10-11T01:57:03+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5703).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5703)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - 在 SDK 模型发现中包含策划的、经过验证的 OpenRouter 路线及其 `openrouter/` 前缀，独立于 LiteLLM 的成本图。
> - 使用包含和省略 OpenRouter 条目的固定目录来执行 HTTP 过滤器； 保留仅目录路由、排序、重复数据删除和提供程序隔离。
> - 替换活库模型和能力断言，SDK 合同检查，纠正MCP 保存指导，将反序列化测试动作移动到模块范围，使其无法影响后续事件。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/AGENTS.md`
- `openhands-sdk/openhands/sdk/llm/utils/unverified_models.py`
- `openhands-sdk/openhands/sdk/llm/utils/verified_models.py`
- `tests/agent_server/test_llm_router.py`
- `tests/sdk/llm/test_model_features.py`
- `tests/sdk/llm/test_model_list.py`
- `tests/sdk/tool/test_mcp_schema.py`

链接问题接受上下文：

- [#5704](https://github.com/OpenHands/software-agent-sdk/issues/5704): [Bug]:OpenRouter 远程 LiteLLM 目录删除后发现和测试中断 — 当前状态已关闭，已于 2026-10-10T23:57:05Z 关闭。

> - 当 LiteLLM 不提供 OpenRouter 目录条目时，[ ] 精选的 OpenRouter 路线会出现在完整的模型列表和经过提供商过滤的模型列表中。 - [ ] 过滤结果保留其路由前缀，排除直接提供商冲突，并保持排序和重复数据删除。 - [ ] 当 LiteLLM 提供时，其他 OpenRouter 目录条目仍然可发现。 - [ ] 模型发现和能力转发测试不会改变 OpenRouter 目录内容。 - [ ] 完整的 SDK 和 Agent Server CI 套件通过。 ### 安装方法工作区可通过`make build`（`uv sync --dev`）编辑安装。 ### SDK版本主要提交`c4b93299c`，包版本1.54.0； LiteLLM 1.93.0。 ### 版本确认 - [x] 我已经确认在复制它时，最新的 SDK 主版本中存在此错误。 ### Python 本地版本 Python 3.13.11； PythonCI中的 3.13.16。 ### 型号名称 `openrouter/deepseek/deepseek-chat` ### 本地操作系统 macOS 和 CI 中的 Linux。 ### 日志和错误消息 ```text assert len(response.models) > 0 E assert 0 > 0 E where [] = ModelsResponse(models=[]).models ``` ### 证据和附加上下文在检查  https://github.com/OpenHands/software-agent-sdk/pull/5700  时对回归进行了调查，并在 main 上独立复制。  https://github.com/OpenHands/software-agent-sdk/pull/5703.  The fixed 端点 lists 21 curated OpenRouter routes against the actual remote catalog. ---  HTTP 证据和回归确定性覆盖率的修复可用

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5703#pullrequestreview-5481241687): ## 审查 - 代码看起来不错； 一个合并门来清除感谢您的修复。 我阅读了 7 个文件 diff 以及周围的上下文（`unverified_models.get_supported_llm_models`、`agent_server/llm_router.list_models`、`verified_models` 和 OpenRouter 运行时适配器）。 这种方法是正确的：独立注入`openrouter/<verified>`，而不依赖于`litellm.model_list`/`model_cost`，恢复发现，而不将精选路由绑定到上游的目录，从而可以丢弃，同时保持前缀，从而通过端点 API，保留下游提供者推导和上下文窗口分辨率。 我对差异的正确性没有任何担忧。 一些注意事项，None 阻塞：1。 当`openrouter`出现在`litellm.provider_list`（`_LITELLM_PROVIDER_NAMES`）中时，`_extract_model_and_provider`仅识别`openrouter/...`。 现在的修复取决于 LiteLLM 保留 * 提供者 *
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5703#pullrequestreview-5481247486): 更新后重新审查。 的 `Validate PR description` 门现在是绿色的 `282fc998` issue #5704 carries `ready-for-dev` 并链接为 `Fixes #5704`), 头部的完整检查套件是绿色的SDK-tests 智能体-服务器、跨平台、二进制构建、预提交等。 我之前的评论笔记是非阻塞的； 批准。_此审核是由 AI 创建的智能体 (OpenHands代表  user._

<a id="5700-fixagent-server-gate-ingress-during-deferred-initialization"></a>

### #5700: fix(agent-server): 延迟初始化期间的门入口

- 提交：`f824a949af7f8045cc6691d7945ce7b31bfe9606` (2026-10-11T00:12:11Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5700).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5700)。 家庭：F01、F03、F05、F30、F31、F32。

陈述意图：

> - 在 `/api/*` 上的身份验证之前运行延迟初始化门，
>   `/v1/*` 和工作区文件路由。
> - 对所有 Canvas 后端入口应用相同的门，包括会话，HTTP
>   代理和 WebSocket 路由。
> - 添加确定性的过渡比赛覆盖范围以及真正的 Uvicorn/wsproto
>   生命周期回归。

更改的路径：

- `openhands-agent-server/openhands/agent_server/api.py`
- `tests/agent_server/test_init_router.py`
- `tests/cross/test_remote_conversation_live_server.py`

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5700#pullrequestreview-5480149326)：检查了与合并的 #5661 基线的差异（主要现在位于 `c4b9329`，#5661 合并）。 改变本身看起来是正确的。 **有什么好处** - 正确地重用共享的 `require_initialized` 依赖项，而不是添加特定于 WS 的变体，并将其应用于两种 `/app-backends/{extension_name}` 路由形式 — 覆盖 #5661 遗漏的 Canvas 入口。 - 依赖项的 `WebSocketException(code=1013)` 路径是端到端执行的（休眠握手被拒绝，然后在 `/api/init` 之后被接受），并且测试正确地解释了 `TestClient`（关闭代码 1013）和真正的 uvicorn/wsproto 握手（HTTP 403 表现为 `InvalidStatus`）之间可观察到的差异。 - 断言 bash 套接字流在初始化（auth + 命令往返）后仍然有效，可以很好地防止门过度阻塞。 **屏蔽/请解决*
- [评论； APPROVED; 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5700#pullrequestreview-5480159558)：谢谢！
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5700#pullrequestreview-5481254483)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## `ef4e0e6d8f2bfd4f3e56f9bcab105f5dbbaf4a0a` **范围的评论：** 在此存储库的范围内。 这是用于延迟初始化的 Agent Server 入口门控，遵循 #5661 和 #5688 强化伞的一部分（当前为 `ready-for-dev`、`security-related`、`priority:medium`）。 不需要交叉存储库或产品决策。 **我在代码中验证的内容** - 延迟初始化门现在在 `/api/*`、`/v1/*` 和工作区静态文件路由 (`api.py`) 上的凭据评估之前运行。 因为`check_session_api_key`、`check_openai_api_key`和`check_workspace_session`在请求时读取`app.state.config`，所以按照`require_initialized`的顺序读取可以解决之前文档中提到的键`POST /api/init`未被尊重的贸易条件。 记录了这一点的评论
- [讨论； 评论； 所有手都机器人](https://github.com/OpenHands/software-agent-sdk/pull/5700#issuecomment-6103115015)：### ⚠️ 暂停审查：当前头检查未通过。当前头`ef4e0e6d8f2b`的检查未通过，因此没有开始审查对话：- `agent-server-tests` 修复上述检查并推送。 然后，计划扫描开始对更新后的磁头进行检查。 _这是一个自动检查 - 没有使用人工智能来生成此comment._
- [讨论； 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5700#issuecomment-6103119500)：@all-hands-bot 失败的 CI 是在 main 上，我们将不得不等待它被修复。

<a id="4838-fixmcp-recover-after-http-session-failure"></a>

### ＃4838：fix(mcp)：HTTP会话失败后恢复

- 提交：`4cc058275c5a08d845bd846576aafc80e5dd7d0d` (2026-10-11T02:20:14Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/4838).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-4838)。 家庭：F19。

陈述意图：

> - 在重新连接之前，将已完成的 FastMCP 会话重置到现有会话锁下。
> - 添加一个真实的 HTTP 回归测试，注入一个 504 响应并验证下一个工具调用是否成功。

更改的路径：

- `openhands-sdk/openhands/sdk/mcp/client.py`
- `tests/sdk/mcp/test_create_mcp_tool.py`

链接问题接受上下文：

- [#4837](https://github.com/OpenHands/software-agent-sdk/issues/4837): [Bug]:MCP 在瞬态 HTTP 错误后重新连接仍然断开 - 当前状态已关闭，已关闭 2026-10-11T02:20:16Z。

> - [ ] 在 HTTP 错误终止 FastMCP 会话任务后，下一个 MCP 工具调用重新连接并成功。 - [ ] 现有 MCP 客户端测试继续通过。 ### 安装方法`uv sync`从存储库中签出。 ### SDK 当前版本 `main`，位于 `e26683288ab4dd69518810016b74682de2a8c4e4`。 ### 版本确认 - [x] 我已经确认 LATEST 版本的 OpenHands SDK ### Python 版本 3.13.7 ### 操作系统 Linux ### 日志和错误消息 ```text First call: 504 Gateway Timeout Second call: MCP Connection Failure Cause: RuntimeError: Internal error: nesting counter should be 0 when starting new session, got 1 ``` ### 最小代码示例链接的 PR 包括一个集成测试，它启动本地 FastMCP HTTP 应用程序，注入一个 504 响应，并通过真实的应用程序进行两次调用SDK 工具执行器。 ### 屏幕截图和附加内容上下文草案 PR #3444 在较旧的 SDK 架构上确定了相同的 FastMCP 陈旧计数器状态。 Current `main` 现在在工具执行器中具有自动重新连接功能； 该报告涵盖了当前路径并使用真实的HTTP故障而不是模拟的会话状态。 存储库锁定的 FastMCP 3.2.0 和 3.4.7 都会重现该故障。 它不支持FastMCP 4.0.2，其会话实现发生了变化，但采用重大版本的断开行为与当前支持的FastMCP 3.x依赖项的重连行为是分开的。

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews COMMENTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/4838#pullrequestreview-5114975027)_此评论由人工智能创建智能体 (OpenHands代表仓库 maintainers._ 总结这个 PR 修复了一个实际存在的 bug 在  MCP 客户端重连路径。 当一个临时的 HTTP 错误导致失败 FastMCP背景会话任务 `_context_manager`'s `finally` 块调用 `_reset_session_state()` without `full=True`, which clears `session` 和 `initialize_result` 但留下 `nesting_counter` 在1和 `session_task` 指向已完成的任务。 的 SDK's `call_tool` then sees `is_connected() == False` and calls `connect()`但是 FastMCP's `_connect()` 拒绝启动新会话 `nesting_counter != 0`, raising `RuntimeError` -> `MCPError("MCP Connection Failure")`. 修复正确地在现有会话下重置了过期状态锁在调用之前 `__aenter__()`. 我通过追踪验证了修复 FastMCP 3.4.7's `_c
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4838#pullrequestreview-5465952177): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 摘要这是对 head `3a5533d` 的最新评论； 该帐户的早期审查是针对被取代的提交 `f608a6a`。 生产变化是 `MCPClient.connect()` 中的 4 条生产线加上实际的 HTTP 回归测试。 我跟踪了固定依赖项 (`fastmcp/client/client.py`) 使用的 FastMCP 3.2.0 内部结构。 机制描述如下：在`_context_manager()`输入时，HTTP的流式错误被抛出，从而通过其`finally: self._reset_session_state()`（而不是`full=True`）来摧毁会话任务，这会清除`session`/`initialize_result`，但会留下`session_task`指向已完成的任务，而`nesting_counter == 1`则指向一个已完成的任务。 然后 SDK 看到 `is_connected() == False` 并调用 `connect()`，但是 `_connect()` 引发 `RuntimeError("当开始新的 sess 时，嵌套计数器应该为 0
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/4838#pullrequestreview-5481594012)：🟢**品味好 — 已批准。**感谢您的专注修复和真实的 HTTP 回归报道。 审查头 `3a5533d0da12bbdd2e7eefdcc555b53f7e56f5b3`：已完成的会话重置使用 FastMCP 的现有锁和重置原语，并满足 #4837 中的范围接受标准。 独立运行时检查重现了第二个失败的工具调用，然后使用精确的PR方法成功了三次，与一个真实的本地FastMCP HTTP服务器（第一次调用：504）。 第二个电话：pong）。 这使用了已安装的 SDK/FastMCP 3.4.8 以及内存中方法替换，而不是完整的基本/头部签出或 LLM 驱动的任务。 当前头实现CI是绿色的。 没有发现任何实质性的正确性。 **风险：LOW**——狭窄的死会话恢复变化； 没有依赖性或公共合同变化。 **结论：值得合并。** _这个版本
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4838#issuecomment-5535237821)：🚦 **CI 目前在 PR 的最新提交上失败。**请在 OpenHands 审核之前修复失败的检查 - 一旦您推送新的提交，就会自动重新检查。 （维护者还可以请求 `@all-hands-bot` 作为审阅者对其进行审阅，无论 CI 状态如何。）_这是一项自动检查 - 没有使用 AI 来生成此 comment._
- [讨论评论； HussainShibli](https://github.com/OpenHands/software-agent-sdk/pull/4838#issuecomment-5570718803)我们用同样的类重现了这个故障 SSE  MCP 桌面桥 (每个对话都有自己的) SSE 会话到桌面应用。 当桥重启时， **现有的** 对话永久失败 `Connection closed` / nesting-counter-stuck errors, while brand-new conversations always work). 我们的测试发现了一个可能与这里相关的细微差别：  该现象可以出现在  **two** 作为抬高的方式 `MCPError` / `Connection closed`, and (b) as an **错误工具结果** 当呼叫通过在进程内部传播时 FastMCP 返回一个断开的远程会话 `CallToolResult(isError=true, text="Error calling tool '...': Connection closed")` rather than raised). 仅针对引发的异常的重新连接/重试逻辑不会涵盖 (b)。 环境： OpenHands-SDK / OpenHands-智能体1.42.1; 1.44.1 和当前版本

<a id="5436-fix-support-gpt-6-sol-luna-and-gpt-61-sol-subscriptions"></a>

### ＃5436：修复：支持 GPT-6 Sol、Luna 和 GPT-6.1 Sol 订阅

- 提交：`3934349da2db0433238621542173a00a8af7439c` (2026-10-11T13:26:34Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5436).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5436)。 族：F04、F06、F07、F09、F20、F22、F23、F24、F30、F33、F34。

陈述意图：

> - 将 `gpt-6.1-sol`、`gpt-6-sol` 和 `gpt-6-luna` 添加到 ChatGPT 订阅白名单。
> - 将订阅模型与 Codex ACP 模型目录分开。 当前的 `main` 已经解耦了这些表面，因此 PR 不再宣传固定的 ACP 适配器拒绝的模型。
> - 验证 Agent Server 订阅模型端点公开完整的允许列表。
> - 对每个受支持的订阅模型的订阅 LLM 构建覆盖范围进行参数化。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/auth/openai.py`
- `tests/agent_server/test_llm_router.py`
- `tests/sdk/llm/auth/test_openai.py`

链接问题接受上下文：

- [#5440](https://github.com/OpenHands/software-agent-sdk/issues/5440)：[功能]：支持GPT 6 Sol、6 Luna 和 6.1 Sol — 当前状态已关闭，已关闭 2026-10-11T13:26:36Z。

> - [ ] GPT-6 Sol、GPT-6 Luna 和 GPT-6.1 Sol 均与 OpenAI 提供商一起使用 - [ ] 现有模型继续工作。 ### 考虑替代方案_无响应_ ### 优先级/严重性中等 - 会改善体验 ### 估计范围未知 - 不确定技术复杂性 ### 功能区域 - [ ] 智能体 API / 核心功能 - [ ] 工具/工具系统 - [ ] 技能/插件 - [ ] Agent Server - [ ] 工作区管理 - [x] 配置/设置 - [ ] 示例/模板 - [ ] 文档 - [ ] 测试/开发工具 - [ ] 性能/优化 - [ ] 集成（GitHub、APIs等） - [ ] 其他 ### 技术实现想法（可选） - 无响应 ### 另外上下文 - 无响应 --

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5436#pullrequestreview-5402707467): _这篇评论是由 AI 智能体 (OpenHands) 发布的。_ ## 评估核心变化很小，重点突出，而且方向正确：在 `openhands-sdk/openhands/sdk/settings/acp_providers.py` 中将 `gpt-6.1-sol`、`gpt-6-sol` 和 `gpt-6-luna` 添加到 `_CODEX_MODELS` 使它们流入 `OPENAI_CODEX_MODELS`（通过 `_get_current_codex_model_ids()`），这正是 `OpenAISubscriptionAuth.create_llm()` 在联系 OpenAI 之前检查的许可名单。 参数化工厂测试通过，我在本地为 `tests/sdk/llm/auth/test_openai.py` 和 `tests/sdk/settings/test_acp_providers.py` 复制了 `91 passed`，并为 `tests/sdk/llm/test_model_list.py` 和 `tests/agent_server/test_llm_router.py` 复制了 `29 passed`。 然而，更改是不完整的：它更新了 ACP 提供者注册表的 Python 事实来源，但没有镜像相同的更改
- [reviews COMMENTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5436#pullrequestreview-5439456863)_这篇评论是由AI发布的智能体 (OpenHands)._ ## 评估意图是正确的，杠杆是正确的： `OPENAI_CODEX_MODELS` 源自《Codex》 ACP  注册表 (`_CODEX_MODELS` -> `get_acp_provider("codex").available_models`因此，在那里添加模型是扩大订阅允许名单的方法。 但新增的三个Codex ID未被锁定的实时适配器接受，因此该更改不符合关联问题的接受标准，并破坏了仓库 CI  该问题已关闭 CI gate `acp-live-tests` (运行 37486259371，任务 112526543725) 在此节点上失败： ```text FAILED  tests/sdk/agent/test_acp_conformance.py::test_acp_conformance_probe[codex] E ValueError: ACP 服务器拒绝 set_config_option请输出简体中文译文。
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5436#discussion_r4174825790)：将这些 id 添加到 `_CODEX_MODELS` 也会更改 `ACP_PROVIDERS["codex"].available_models`，并镜像到 `clients/typescript/src/models/acp-providers.json`。 那面镜子没有更新，因此在`.github/workflows/typescript-client-ci.yml`的`validate-acp-providers`任务在此分支上失败了：``` $ OPENHANDS_SUPPRESS_BANNER=1 uv run python clients/typescript/scripts/check-acp-drift.py ERROR: src/models/acp-providers.json has drifted from openhands-sdk. EXIT CODE: 1 ````clients/typescript/src/models/acp.ts`文档了合同（“先编辑`acp_providers.py`，然后镜像更改……CI直到两方匹配”。） 重新生成并提交镜像：```bash OPENHANDS_SUPPRESS_BANNER=1 uv run python clients/typescript/scripts/check-acp-drift.py --write ```
- [review_comments; 评论； viblo-majority](https://github.com/OpenHands/software-agent-sdk/pull/5436#discussion_r4192199684)：在 437e0feb 中修复：重新生成 TypeScript ACP 注册表镜像并验证 `check-acp-drift.py` 通过。 已添加 GPT-6.1 Sol 到已验证的 OpenAI 列表中，覆盖 API。120 个相关测试和所有适用的预提交检查都通过了。_此回复由 OpenHands 代表 contributor._ 生成
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5436#discussion_r4204571414)：相同的实时适配器检查存储库已运行（`acp-live-tests`），拒绝当前头上的此确切 ID：```text FAILED tests/sdk/agent/test_acp_conformance.py::test_acp_conformance_probe[codex] ValueError: ACP server rejected set_config_option(model)(model='gpt-6.1-sol'): Invalid params ``` 根据固定的 `@agentclientprotocol/codex-acp@1.10.0` 在本地复制：`gpt-6.1-sol`、`gpt-6-sol` 和 `gpt-6-luna` 均被 `_CODEX_MODELS` 拒绝，而 `gpt-6-astra`、`gpt-5.6-*` 条目和 `gpt-5.5` 被接受。 这些是上面的评论`_CODEX_MODELS`描述的“活动服务器`set_config_option`拒绝的死条目”。 因为`OPENAI_CODEX_MODELS`是从这个元组导出的，被拒绝的ID会传播到订阅允许列表和codexACP选择器中，但仍然不可用，同时live conformance gate也会受到影响
- [review_comments; 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5436#discussion_r4241694531)已解决在 931649fe5。 当前主要实现了 decoupling ChatGPT Codex订阅白名单 ACP 在第5579号。 This PR 现在只添加了这三个模型 `OPENAI_CODEX_MODELS` and its Agent Server 端点/工厂测试它不再改变 `_CODEX_MODELS`, the TypeScript  ACP 镜像，或验证提供商列表。 直播 ACP 因此，可避免一致性失败，同时保留贡献者的成功订阅响应探针智能体 (OpenHands代表  contributor._

<a id="5715-fixterminal-notice-a-finished-command-within-milliseconds-instead-of-at-the-next-05-s-poll"></a>

### #5715: fix(terminal): 注意在几毫秒内完成的命令，而不是在接下来的 0.5 秒轮询

- 提交：`3dcb27b227aa177f6a7eadb0eb144339245cbbc4` (2026-10-11T18:51:05-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5715).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5715)。 家庭：F13、F27、F33。

陈述意图：

> - 轮询间隔从 `MIN_POLL_INTERVAL` (0.02 s) 开始，并随着命令的运行时间 (`elapsed / 4`) 增长，直至 `POLL_INTERVAL` (0.5 s)。
>   - 一个简短的命令会在几十毫秒内被注意到。
>   - 与以前一样，每 0.5 秒轮询一次运行时间超过 2 秒的命令。
>   - 没有命令持续时间比现在等待的时间更长。
> - 新测试：第一次轮询低于 `POLL_INTERVAL` 的一半，间隔永远不会缩小，并且 2.5 秒的命令会退回到 `POLL_INTERVAL`。 它在 tmux 和子进程后端上运行。

更改的路径：

- `openhands-tools/openhands/tools/terminal/constants.py`
- `openhands-tools/openhands/tools/terminal/terminal/terminal_session.py`
- `tests/tools/terminal/test_terminal_session.py`

链接问题接受上下文：

- [#5714](https://github.com/OpenHands/software-agent-sdk/issues/5714)：[Bug]：终端仅在接下来的 0.5 秒轮询时返回短命令 — 当前状态已关闭，已关闭 2026-10-11T22:51:06Z。

> - [ ] 在 tmux 和子进程后端上，在 0.1 秒内完成的命令无需等待 0.5 秒轮询即可返回。 - [ ] 运行几秒钟的命令不会比现在更频繁地轮询（每个 tmux 轮询都会产生 `tmux capture-pane`）。 ###安装方法uv（源码查看）---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5715#issuecomment-6113510113)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5715#pullrequestreview-5485296644)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## PR #5715 的评论在 head `e7a917a21902a136015c74112215c6db6a7ef7a3` 处进行了评论（头部未更改； PR 标题/正文/标签和链接问题 #5714 现在重新阅读）。 **范围**——回购内和所有权内。 自适应轮询位于共享 `TerminalSession.execute` 循环 (`openhands-tools/openhands/tools/terminal/terminal/terminal_session.py`) 中，因此 tmux、子进程/PTY 和 Windows 后端都使用它。 没有公开 API、设置或电汇合同变更； 正如问题 #5714 所要求的，更改保留在共享会话和常量代码中。 **正确性**——新的睡眠`min(POLL_INTERVAL, max(MIN_POLL_INTERVAL, elapsed_time / 4))`受到`POLL_INTERVAL`的限制，因此没有命令在读取之间等待的时间比现在更长。 第一个间隔是 `MIN_POLL_INTERVAL`（0.02 秒），

<a id="5689-fixagent-server-reap-canvas-backend-descendants-after-leader-exit"></a>

### ＃5689：fix(agent-server)：领导者退出后收获 Canvas 后端后代

- 提交：`c0471362d340ade1e334595ba98417108b415e88` (2026-10-12T00:56:49+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5689).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5689)。 家庭：F28。

陈述意图：

> 在报告退出的后端为不健康之前，先收割拥有进程组。 实时后端保持 TERM 到 KILL 的正常关闭，而已退出的领导者留下的后代将立即终止。
> - 在直接重新启动之前回收已退出的运行时，并在其进程组保持活动状态时阻止强制安装和数据删除。
> - 添加真实子进程状态覆盖、直接停止、直接重启、响应式准备/日志/数据操作和SIGTERM忽略后代。

更改的路径：

- `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`

链接问题接受上下文：

- [#5634](https://github.com/OpenHands/software-agent-sdk/issues/5634): [Bug]: 当子进程比领导者寿命长时，应用程序后端状态挂起并持有应用程序锁； 预期不健康 — 当前状态已关闭，已于 2026-10-11T22:56:51Z 关闭。

> - [ ]leader退出后，status返回`unhealthy`/`Backend exited with code <n>`，无需等待其他进程关闭管道。 - [ ] `stop` 在leader退出后，也在status记录退出后杀死进程组的REST。 - [ ] 真实的子进程测试涵盖了这种情况。 - [ ] verify-智能体-server F28 映射中的 `F28.status-exit-hang` 项目符号通过，其 `# bug` 标记被删除。 ### 检查主版本中的安装方法 uv 同步 ### 2804c12 的主版本 ### 附加上下文在 `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py` 中： - `status()` (444-453) 保存每个应用程序锁，并且一旦设置了领导者的 `returncode`，就等待 `_finish_runtime()`，它收集排出任务 (676-681)。 `_drain()`（526-537）读到EOF； 管道（642-649）被每个子进程继承，因此EOF等待最后一个。 - 只有`_terminate_runtime()`（707-725）通知组，从`stop()`（734-753），需要相同锁。 `status()` 也设置 `runtime.process = None` (450)，因此较晚的 `stop()` 会提前返回 (709-710)。 - `has_running_backends()` (727-732) 仅检查领导者，因此接受强制安装。 建议的修复方案：当 `status()` 看到一个退出的领导者时，通过 `_terminate_runtime()` 重新获取组（它已经在 `_group_alive(pgid)` 时发送信号），或者将 drain 等待绑定并取消 drain 任务，以确保锁从未持有在管道 EOF 上

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5689#pullrequestreview-5485029407)：_此评论由 AI 智能体 (OpenHands) 发布。_ **范围**：此更改属于此存储库。 它修改了智能体-服务器 Canvas 应用后端生命周期 (`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`) 和其回归测试，无需 REST 模式或 TypeScript-客户端更改（`pid`/`port` 字段已经在 `BackendStatus` 中已经可选了，生成的客户端）。 不需要维护者做出决定。 **头 93c6480 的验证** - 运行工作区中的重点套件。 186 个测试中有 9 个在这里失败，只是因为测试后端带有 `#!/usr/bin/python3` shebang，并且该沙箱中不存在该解释器（创建符号链接需要 root，而 root 不可用）。 重新运行指向可用解释器的未跟踪副本给出 186/186 通过，与 PR 的声明相符。 - 确认
- [评论； APPROVED; 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5689#pullrequestreview-5485390469)：谢谢！

<a id="5587-fixsdk-recognize-haiku-55-prompt-caching-without-model-metadata"></a>

### ＃5587：fix(sdk)：识别 Haiku 5.5 提示词缓存，无需模型元数据

- 提交：`3385a486997edec21c1a2b859344f57a74dea84b` (2026-10-12T05:05:12Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5587).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5587)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - 将 `claude-haiku-5-5` 添加到 `PROMPT_CACHE_MODELS`。
> - 使用裸、Anthropic 和 LiteLLM 代理名称测试两个模型的回退方案识别和真实消息格式。
> - 检查启用和禁用缓存的自动缓存标记。 公共APIs和缓存策略保持不变。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/model_features.py`
- `tests/sdk/llm/test_llm.py`
- `tests/sdk/llm/test_model_features.py`

链接问题接受上下文：

- [#5702](https://github.com/OpenHands/software-agent-sdk/issues/5702)：[Bug]：Haiku 5.5 提示词当模型元数据不可用时禁用缓存 - 当前状态已关闭，已于 2026-10-12T05:05:14Z 关闭。

> - [ ] Haiku 5.5 回退方案识别适用于裸名、`anthropic/` 和 `litellm_proxy/anthropic/` 名称。 - [ ] 真实消息格式在启用时添加自动缓存标记，在禁用时添加 None。 - [ ] Opus 5.5 的行为在这些名称形式中保持不变。 - [ ] 没有公共 API 或缓存策略更改； 实时提供商缓存命中测量不属于这个范围狭窄的修复范围。 

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5587#pullrequestreview-5480435066)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## #5587 的评论（头 `b3e72dc2d`） ### 范围在此存储库的范围内。 更改发生在`openhands-sdk/openhands/sdk/llm/utils/model_features.py`中，AGENTS.md将其称为模型/提供者能力调整的正确家园，并将其保持在`llm.py`之外。 不需要架构或产品决策。 ### 技术评估 `"claude-haiku-5-5"` 到 `PROMPT_CACHE_MODELS` 的一行添加是正确的。 回退方案只在 `_supports_explicit_prompt_cache()` 时出现，`model_matches(model, PROMPT_CACHE_MODELS)` 时缺少或结论不明，`model_matches` 对原始模型字符串进行不区分大小写的子字符串匹配，因此，`anthropic/`、`litellm_proxy/anthropic/` 等形式都匹配。 LiteLLM俳句 5 的元数据。
- [讨论； 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5587#issuecomment-6102723694)：将回归链接为 Fixes #5702 并更新了测试证据。 新的运行与审查相符：327 次通过，3 OpenRouter 次推理失败； 以缓存为中心的子集通过了所有 49 项测试。 现在，描述将原始记录结果与此次重新运行区分开来。 配套文档 PR OpenHands/docs#913 在 Notes 中链接。 HUMAN 部分未更改，无需更改代码。 剩下的关卡是问题准备：#5702 需要维护者分类/准备开发。 该帐户无法应用标签。

<a id="5659-fixagent-server-ignore-empty-session-api-keys"></a>

### ＃5659：fix(agent-server)：忽略空会话API键

- 提交：`e696f72c260b959d1b36d570a6688e99977ec28a` (2026-10-12T07:06:07+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5659).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5659)。 族：F01、F02、F03、F06、F07、F13、F29、F31、F32。

陈述意图：

> - `Config` 获取 `session_api_keys`  验证器这会丢空字符串，所以环境槽 env slots JSON 配置和显式构造在一处进行规范化。 `[""]` becomes `[]`, `[key, ""]` becomes `[key]`. 这符合旧版 `SESSION_API_KEY=""`, which `_default_session_api_keys` 已经处理为无键。
> - 两者 WebSocket auth paths（遗留的查询/头部认证和第一帧认证）即使列表中曾经存在一个，拒绝空呈现的密钥 `candidate and candidate in keys` pattern `check_workspace_session` 使用。
> - 默认绑定地址遵循已清理的列表。 非空键的行为与以前完全相同。
> - `/api/init` 在离开休眠状态之前拒绝使用 HTTP 422 的任何空 `session_api_keys` 条目； 客户端可以重试使用有效的密钥。

更改的路径：

- `openhands-agent-server/openhands/agent_server/config.py`
- `openhands-agent-server/openhands/agent_server/init_router.py`
- `openhands-agent-server/openhands/agent_server/sockets.py`
- `tests/agent_server/test_config.py`
- `tests/agent_server/test_init_router.py`
- `tests/agent_server/test_preload_modules.py`
- `tests/agent_server/test_websocket_first_message_auth.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5659#issuecomment-6076092603)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5659#pullrequestreview-5484862257)_这篇评论是由AI发布的智能体 (OpenHands[_] ## 范围在范围内。 这是一个智能体- 本仓库自己的包中，服务器认证加固的更改`openhands-agent-server/`), 以及关联的伞形问题 #5688 明确将此路径分配给此 PR请拒绝空会话 API 在键之前 `/api/init` 更改服务器状态：#5659。 没有产品/架构决定事项在等待 `50c9514`) - **环境/ JSON 直接建设** — 新的 `Config._drop_empty_session_api_keys`  验证器标准化每个 `model_validate` 所以 `[""]` → `[]` 和 `[key, ""]` → `[key]`. `load_config()` 将环境槽合并到模型中验证所以空白 `OH_SESSION_API_KEYS_0=` 槽位被丢弃， 默认绑定决策 `__main__._auth_enabled()` (`bool(config.session_api_keys)`）现在是清理后的列表。 钍

<a id="5657-fixllm-keep-provider-credentials-out-of-completion-logs"></a>

### ＃5657：fix(llm)：将提供者凭据排除在完成日志之外

- 提交：`e3a26821f8f7c85e98078c7b5e1a80647fc7d0c7` (2026-10-12T05:23:46Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5657).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5657)。 族：F04、F06、F07、F09、F19、F20、F22、F23、F30、F33、F34。

陈述意图：

> - `Telemetry.on_request` 复制了 `extra_headers` 和 `headers` 的日志，然后通过现有的 `sanitize_dict` 辅助函数 (`openhands/sdk/utils/redact.py`) 传递，因此在调用过程中无法实现原地修改的日志和凭据-类似头信息会被记录为 `<redacted>`。
> 成功的调用 (`log_llm_call`) 和失败的`on_error`) 从这个日志中记录上下文，服务器的日志事件也是从同一个源头构建的已序列化数据，因此一个更改覆盖了所有日志被写入的地方。
> - 记录的 kwargs 中的类似凭据的字符串和 `SecretStr` 选项是已脱敏。 提供程序错误消息、表示和回溯在记录之前进行清理，包括多行凭据值。
> - 非凭据的标头保留其值以供调试。 发送给提供者的请求没有改变。

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/telemetry.py`
- `openhands-sdk/openhands/sdk/utils/redact.py`
- `tests/sdk/llm/test_llm_log_completions_integration.py`
- `tests/sdk/utils/test_redact.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5657#issuecomment-6075863054)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5657#pullrequestreview-5484726365)：_此评论由 AI 智能体 (OpenHands) 发布。_范围检查：这是 SDK 的 LLM 遥测/编辑路径中的错误修复，该存储库拥有该路径（AGENTS.md 和评论指南）。 它在范围内，链接的问题 #5688 是 `ready-for-dev` 和 `security-related` / `priority:medium`。 CI 当前分支的测试结果是绿色的（SDK-测试，智能体-服务器测试，集成测试，OpenAPI，覆盖率等），并且两个重点测试套件本地通过：`tests/sdk/utils/test_redact.py`（50通过）和`tests/sdk/llm/test_llm_log_completions_integration.py`（7通过）。 两个重要的发现，都在凭据-脱敏路径中，这个 PR 旨在强化。 1. `openhands-sdk/openhands/sdk/utils/redact.py:284` - 新的 `_SENSITIVE_ENTRY_RE` 与 `.*?` 匹配，不会跨越换行符（该模式不使用 `re.DOTALL` 进行编译）。 拍拍
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5657#pullrequestreview-5485307014)：_此评论由 AI 智能体 (OpenHands) 发布。_ 头部 `31d81aec` 的新鲜评论。 早期的 `all-hands-bot` 评论是针对 `95ff8676` 的，`smolpaws` 和 `Fieldnote-Echo` 此后发表了评论，因此这是一个新的传递，而不是前一个传递的重复。 范围：回购内。 该更改强化了SDK的LLM遥测/脱敏路径(`openhands-sdk/openhands/sdk/llm/utils/telemetry.py`和`openhands-sdk/openhands/sdk/utils/redact.py`)，而不是添加一个并行脱敏实现，这符合仓库指导。 不需要产品或架构决策。 我对此进行了验证： - 报告的泄漏已关闭。 `Telemetry.on_request` 现在存储请求上下文 (`_redact_request_credentials`) 的已脱敏副本，复制 `kwargs` 并传递 `extra_headers`/`headers`
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5657#discussion_r4243002404): `(?P<value>.*?)` 与换行符不匹配，因为该模式不是用 `re.DOTALL` 编译的，并且 `.*?` 在第一个 `\n` 处停止。 这两个被取代的模式使用了 `[^']*` / `[^"]*`，它们会跨行，因此这是行为回归：一个敏感的条目，其值跨越多行，现在以原始版本已脱敏的方式记录下来。 在此头上复制：`redact_text_secrets("{'private_key': '<PEM with newlines>'}")` 保持密钥完好无损（基础：`<redacted>`）； 这同样适用于任何多行 `token` / `secret` / `password` / `authorization` 值。 这削弱了 `redact_text_secrets` 的每个调用者 - 遥测错误 `message`/`repr`/`traceback`、`acp_agent`、`utils/command.py`、`profiles_router` - 因此它削弱了 PR 添加的强化。 添加 `re.DOTALL`，或使用可容忍 `\n` 的值体。
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5657#discussion_r4243002408): `isinstance(value, str)` 跳过 `pydantic.SecretStr`，这是 SDK 自己的凭据类型（`LLM.api_key` 是 `SecretStr`）。 以这种方式传递的调用者提供的机密被逐字复制，并且 `_safe_json` 将其序列化到其内部字段。 转载：`llm.completion(msgs, api_key=SecretStr("CALLERSECRET123456"))` 将 `"api_key": {"_secret_value": "CALLERSECRET123456"}` 写入完成日志。 PR 主体表示记录的 kwargs 中类似凭据的选项是已脱敏； 这不适用于`SecretStr`。 编辑机密键控值，无论类型如何（e.g. 显式处理`SecretStr`），因此日志不能携带包装值。
- [review_comments; 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5657#discussion_r4243232821)：在 31d81aec6ad5464bb4b12afaccffc038664547a6 中确认并修复。 现有模式现在使用 `re.DOTALL`，因此引用的多行凭据值为已脱敏。 回归包括单引号、双引号、混合引号和转义引号分隔符，保留相邻的公共多行文本，以及在`message`、`repr`和`traceback`到`LLM.completion()`之间的多行提供者错误。 这些新案例在 95ff8676 上失败并通过修复。 脱敏和完成日志套件通过了所有 65 项测试； 预提交通行证。
- [review_comments; 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5657#discussion_r4243232860)：在 31d81aec6ad5464bb4b12afaccffc038664547a6 中确认并修复。 凭据选项现在通过现有的 `sanitize_dict` 帮助器接受脱敏的 `str` 和 `SecretStr`。 测试覆盖了成功和失败完成日志中的包裹值 `api_key` 和 `aws_secret_access_key`，验证提供者仍然接收原始值，并保留数值 `max_completion_tokens`。 两个wrapped-凭据案例在95ff8676上失败并通过修复。 更广泛的回归运行通过了 613 项测试，其中一个 ACP 会话持久化失败，该失败也在未受影响的 95ff8676 头上重现。
- [讨论； 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5657#issuecomment-6103712703)：@enyst，我查看了 #5657 并在共享错误文本脱敏路径中发现了一些相邻的案例。 小写和 JSON 样式的标头键、混合引号样式和转义引号可以绕过当前匹配。 我有一个包含两个文件的小补丁，其中包含重点测试。 您希望我将其作为提交发送给您审核或挑选吗？
- [讨论； 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5657#issuecomment-6113935049)：@enyst 很快就会发布详细的评论。 保持内联，因为我认为我没有权限将提交推送到您的分支。
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5657#issuecomment-6114003229)：> @enyst 很快就会发布详细的评论。 保持内联，因为我认为我没有权限将提交推送到您的分支。 谢谢！ 酷，由你决定，我想你也可以用你的叉子制作一个 PR 到这个 PR

<a id="5621-add-verify-agent-server-an-executable-feature-map-and-control-cli-for-the-agent-server-api"></a>

### ＃5621：添加 verify-智能体-server：可执行特征图和 Agent Server API 的控制 CLI

- 提交：`acca181af1f353975965bcf6486e1d0a58f444c0` (2026-10-12T21:22:20+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5621).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5621)。 系列：无需产品运行时间。

陈述意图：

> - `.agents/skills/verify-agent-server/` 下的贡献者技能：控件 CLI (`control-agent-server`)、可执行功能图（34 个系列，每个系列一个文件）和维护杠杆。
> - **`control-agent-server`**从结帐启动隔离服务器（私有HOME、持久化、密钥、端口），使用断言驱动任何REST路由或WebSocket，安排测试夹具（git存储库、技能、插件、MCP服务器、Webhook接收器、脚本化LLM存根），并使用机密已脱敏记录证据。 模型支持的配方通过服务器自己的预检使用DeepSeek。
> - **该功能图** 智能体面向的路线 `map coverage` 绿色：193条中，203条路线被拥有并驾驶，10条路线被故意排除，原因在`map run --all --fresh`。 已知的产品错误被保留为预期的故障，因此修复显示为意外的通过。
> - **维护：** 覆盖率，解析测试与实际进行比较 CLI两个提交之间的路由表差异，以及更改文件的拥有者查找。 一个跨仓库测试（`tests/cross/test_verify_agent_server_

更改的路径：

- `.agents/skills/verify-agent-server/SKILL.md`
- `.agents/skills/verify-agent-server/references/adaptation.md`
- `.agents/skills/verify-agent-server/references/feature-map/F01-server-status.md`
- `.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md`
- `.agents/skills/verify-agent-server/references/feature-map/F03-deferred-init.md`
- `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`
- `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md`
- `.agents/skills/verify-agent-server/references/feature-map/F06-conversation-events.md`
- `.agents/skills/verify-agent-server/references/feature-map/F07-session-socket.md`
- `.agents/skills/verify-agent-server/references/feature-map/F08-confirmation-security-secrets.md`
- `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`
- `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md`
- `.agents/skills/verify-agent-server/references/feature-map/F11-goals.md`
- `.agents/skills/verify-agent-server/references/feature-map/F12-runtime-and-credentials.md`
- `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`
- `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`
- `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`
- `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md`
- `.agents/skills/verify-agent-server/references/feature-map/F17-workspaces-registry.md`
- `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md`
- `.agents/skills/verify-agent-server/references/feature-map/F19-mcp.md`
- `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md`
- `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md`
- `.agents/skills/verify-agent-server/references/feature-map/F22-meta-profiles.md`
- `.agents/skills/verify-agent-server/references/feature-map/F23-llm-catalog-and-connections.md`
- `.agents/skills/verify-agent-server/references/feature-map/F24-openai-subscription.md`
- `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`
- `.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md`
- `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`
- `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`
- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md`
- `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`
- `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`
- `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`
- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `.agents/skills/verify-agent-server/references/feature-map/README.md`
- `.agents/skills/verify-agent-server/references/maintenance.md`
- `.agents/skills/verify-agent-server/references/mapping.md`
- `.agents/skills/verify-agent-server/references/report.md`
- `.agents/skills/verify-agent-server/scripts/control-agent-server`
- `.agents/skills/verify-agent-server/scripts/control_agent_server.py`
- `.impeccable/config.json`
- `openhands-agent-server/AGENTS.md`
- `tests/cross/conftest.py`
- `tests/cross/test_verify_agent_server_skill.py`

链接问题接受上下文：

- [#5617](https://github.com/OpenHands/software-agent-sdk/issues/5617)：[功能]：用于验证Agent Server的REST和WebSocket APIs的可执行功能图和控件CLI - 当前状态已关闭，已关闭2026-10-12T19:22:23Z。

> - [  ] Every 智能体- 面向路由拥有一个唯一的拥有者家庭和至少一个驱动它的配方 (`map coverage`). - [  ] 每条食谱命令都解析真实的数据 CLI (`map check`), 由执行单元测试。 - [  ] 每个家庭都在一个新服务器上从头开始播放`map run --fresh`). 真实的行为来自真实模型DeepSeek); 一个脚本 stub 仅用于提供者失败，而真实模型无法按需生产 [  ] 在产品开发过程中发现的缺陷被记录为已知缺陷的食谱，包括重现步骤 **通过服务器驱动 TypeScript 客户端。** 客户端本身也是一个消费者。 它被固定在发布服务器上，不覆盖所有路由，并且会隐藏状态码、错误体和 WebSocket 它自己后面有关闭代码 API. 将其作为独立的消费者家族进行覆盖，紧邻  Python  SDK 客户端。### 优先级/严重性中等 - 会改善用户体验 ### 预估范围中等 - 新功能，中等复杂度 ### 功能区域 - [x]  Agent Server - [x] 测试/开发工具——

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5621#issuecomment-6073720178)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#pullrequestreview-5475829425)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## `verify-agent-server` 范围检查的评论：这在 `.agents/skills/` 下添加了一项贡献者技能，一个跨存储库测试，并在 `openhands-agent-server/AGENTS.md` 中添加了一个指针。 它属于这个存储库，并且不涉及运行时代码，因此范围门通过了，我对其优点进行了审查。 我在头 `cee9a8bb8a392bd382a8d742b76d5b1c856fb2b4` 上验证的状态： - 头仍然与请求的 SHA 匹配； PR打开，没有标签； 只有`all-hands-bot`的审查请求。 - 在这一部分，CI是绿色（运行测试，预提交，REST API的断层，TypeScript客户端CI/审计，已持久化设置，PR描述，审查线程门，Agent Server）。 - 本地：`tests/cross/test_verify_agent_server_skill.py`通过11/11，`ruff`/`pyright`在新文件上干净，`control-agent-server map check`绿色（3
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#pullrequestreview-5485063074)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## `verify-agent-server` 评论（头 `5c34e09`）范围检查：这在 `.agents/skills/` 下添加了贡献者技能、跨存储库测试和 `.pr/` 评论工件。 它属于此存储库，并且不涉及运行时代码，因此范围门通过。 在此头上验证的状态： - head `5c34e09a91c5d0f1d3d613229c42a598225fd4a7` 匹配； PR开放、非草稿、无标签。 - CI：除了 `Review Thread Gate` (`unresolved-review-threads`) 之外，每个检查都是绿色的，它失败只是因为 `control_agent_server.py` 上的两个较早的 `all-hands-bot` 线程仍未解决 - 作者操作，而不是代码缺陷。 - 本地：`tests/cross/test_verify_agent_server_skill.py` 34/34通行证； `map check`绿色（34个文件，931个ID）； `map coverage` 绿色（204 条路线，194 条拥有/驾驶）。 先前的两项发现
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#pullrequestreview-5494552136): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 对 `verify-agent-server` 头部 `fff65e3` 范围检查的评论：此 PR 在 `.agents/skills/verify-agent-server/` 下添加了一项贡献者技能（控制 CLI + 可执行功能图）、一个跨存储库测试和 `.pr/` 审核工件，以及 `openhands-agent-server/AGENTS.md` 中的短指针和 `.impeccable/config.json` 忽略条目。 它属于此存储库，并且不更改运行时代码，因此范围门通过。 在此头上验证的当前状态： - head `fff65e3ebff18786e389c161dbdd30f955e3bb6b` 匹配； PR开放，非草稿，无标签，`mergeable_state: blocked`。 - CI：在此头上运行的每次检查都是 `success` (49) 或 `skipped` (2)； 没有失败。 - 本地：`tests/cross/test_verify_agent_server_skill.py` 39/39 通行证； `map check`绿色（34个文件，935个ID）； `map coverage`绿色（204r
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4234957309)：`--field`（此处）和`--print-header`（第1355行）`print()`原始值而不是经过`emit()`/`REDACT`，因此带有机密的字段到达标准输出时未编辑 - 与`SKILL.md`合同相矛盾，即CLI编辑了运行的密钥，`$DEEPSEEK_API_KEY`以及来自所有输出和证据的密码加密值。 `api GET /info --field echo_key`（身体重播了`X-Session-API-Key`，）原文`qa-session-key-123456`，以及`--field config.api_key`打印了一个原始的`gAAAAA...` Fernet token，在JSON路径上显示为`<redacted:encrypted>`。 提交的映射依赖于这些标志来获取机密承载值 (e.g. `F20-llm-profiles.md` `--field config.api_key`、`F18-settings-and-secrets.md` `--field agent_settings.llm.api_key` 和许多 `F29` `--print-header set-cookie` 捕获），所以一个食谱
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4234957320): `ok` 省略 `undriven`，因此 `map coverage` 报告成功，而路线已拥有但从未行驶。 使用合成路由表复制，其中 `F01` 列出 `Routes: `GET /api/thing``，并且没有配方调用它：`cmd_map_coverage` 返回 `owned_but_not_driven: [{"route": "GET /api/thing", ...}]` 和 `ok: True`（出口 0）。 子命令 help 描述“没有家庭或驾驶的路线”，维护周期检查这个结果，因此未驾驶的情况被默许忽略了。 使用`not unowned and not undriven and not multi and not stale`。
- [review_comments; 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4240354514)：已在 2f1aa080f1ee4179c4891e0e161023a5b7cb6ded 中修复。 现在，两个输出路径都默认使用现有的编辑器。 原始的单向往返需要显式地使用 --unsafe-unredacted 标志。 证据仍然存在已脱敏，受影响的食谱是故意选择的。 复制之前/之后的环回和回归测试涵盖标头、字段、结构化输出和加密 token。 评论笔记： https://htmlpreview.github.io/?https://github.com/OpenHands/software-agent-sdk/blob/08e548c80b9664edf0eb8b9e9580fe8392bee5bd/.pr/review-fixes.html
- [review_comments; 评论； smolpaws](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4240354568)：已在 2f1aa080f1ee4179c4891e0e161023a5b7cb6ded 中修复。 自有但无人驾驶的路线现在无法覆盖。 再现使用真实路线表，其中包含一条拥有的未行驶路线：原始出口 0 和修复出口 1。 合并主要路线和覆盖路线 POST /api/acp/models 后，地图上的 204 条自有/驾驶路线中有 194 条为绿色，其中 10 条除外。 评论笔记： https://htmlpreview.github.io/?https://github.com/OpenHands/software-agent-sdk/blob/08e548c80b9664edf0eb8b9e9580fe8392bee5bd/.pr/review-fixes.html
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4243319541): `--field` 此处（以及第 298 行和第 613 行的加密读取）现在默认返回脱敏占位符，因此下一行的 `test "${ENC#gAAAAA}" != "$ENC"` 失败，并且在 `set -eo pipefail` 下，F09 在第一个块处失败。 F18 和 F20 在同一个提交中更新为通过 `--unsafe-unredacted` 来完成此读取； 这个被错过了。 将 `--unsafe-unredacted` 添加到此文件中的三个加密 `--field` 读取中（并保留原始 token 证据）。
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4243319543)：与 F09 相同的错过选择加入：此加密读取现在生成 `<redacted:encrypted>`，因此下面的 `test "${ENC#gAAAA}" != "$ENC"` 失败，后续的 `/api/mcp/test` 调用接收占位符而不是它必须解密的密文。 在此添加`--unsafe-unredacted`。
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4243608466)：已在 cb00b0c 中修复（现已推送）。 F09（`config.api_key`、`config`和`agent_settings`）中的三个加密读取现在通过`--unsafe-unredacted`； 证据仍然存在已脱敏。 配对在新服务器上运行：在 `fc01624` 上，`map run --file F09 --only F09.auth-required` 在 `test "${ENC#gAAAAA}" != "$ENC"` 的先决条件中失败。 修复后它通过了，`F09.load-plugin`（将设置与`secrets_encrypted: true`一起发回）和`F09.switch-llm-registered-usage-id`（在其标记行处失败）也是如此。 详细信息参见 `.pr/followup-fixes.md` 第 4 节。 --- _由 [Claude Code](https://claude.ai/code) 生成_
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5621#discussion_r4243608633)：已在 cb00b0c 中修复（现已推送）。 此读现在已通过`--unsafe-unredacted`。 另外两个 F19 读取也有同样的问题：已完成的 OAuth 作业的 `oauth_state`（在 `F19.oauth-inline-writeback` 和 `F19.oauth-stored-state` 中），其 token 也是密文。 两者现在都选择加入。 存储的访问令牌的两个 `plaintext` 读取也选择加入。 如果没有它，返回密文的回归将返回为 `<redacted:encrypted>`，并且 `test "${TOKEN#gAAAA}" = "$TOKEN"` 检查仍然会通过。 配对在新服务器上运行：在 `fc01624` 上，`F19.test-encrypted-env` 在 `test "${ENC#gAAAA}" != "$ENC"` 上失败。 `F19.oauth-stored-state` 也失败，因为 `/api/mcp/test` 与已脱敏状态在工具列表上超时。 修复后，`F19.oauth-inline-writeback` 和 `F19.oauth-refresh-writeback` 都通过了。 未出现原始 token
- [讨论； 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5621#issuecomment-6091287181)：我对主要修复程序和两个开放修复程序进行了测试。 它已经得到了回报。 F28 为两者提供了清晰的基线修复信号。 `F28.install-ref-cached` 在 main 上 x 失败两次，在 #5685 上 x 通过两次； 额外的运行还涵盖了相邻的首次获取、有效引脚和最新引用行为。 `F28.status-exit-hang` 在 main 上 x 失败两次，在 #5689 上 x 通过两次。 我随后对#5689进行了完整的F28家庭测试：24个普通用例通过，四个不相关的已知错误仍然预期失败，生命周期修复是唯一的意外通过。 我还运行了一个无模型的 F02 切片，其中通过了八个身份验证、工作区-cookie 和 CORS 案例。 一些事情浮出水面： - `--checkout` 适用于外部新鲜运行，但配方内的嵌套 `launch --new` 调用回落到线束结账。 在 F02 前缀 cookie 的情况下，o
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5621#issuecomment-6115034096)：我是一个基于 Opus 5.5 的 AI 智能体，帮助 Engel Nyst (@enyst) 进行项目维护。 @Fieldnote-Echo，感谢您的狗粮活动。 看到#5685和#5689的基准修复信号按预期工作，以及#5689的F28条目现在在分支上是一个普通的通过条目，真是太好了。 所有三项发现都在2f1aa080中解决，后续跟进在fc016247： - **`--checkout` 接入嵌套启动：** 基线检查现在嵌入到嵌套`launch --new`调用和SDK步骤中，因此多服务器配方不再混合基准和目标。 - ** 家族级前提条件：** 列表项可以声明自己的`Requires:`，需求按选定的配方检查，因此`--only`切片运行时不需要家族的无关前提条件，如DeepSeek预飞或tmux。 - ** 综合报告：** 合并多个账簿

<a id="5724-replace-policy-rail-regexes-with-shell-ast-analysis"></a>

### ＃5724：用 shell AST 分析替换策略轨道正则表达式

- 提交：`d97eb76f60829a4250dd313f5a9d4d03e2951de8` (2026-10-13T05:30:07+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5724).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5724)。 家庭：F08。

陈述意图：

> - 使用共享的树托管 Bash 解析器解析每个原始可执行段。
> - 重用命令字和重定向拥有的参数的共享命令视图。
> - 解析引用的命令名称、路径、支持的包装器、描述符流以及文字嵌套或管道 shell 源。
> - 当无法解析相关管道输出、重定向、消费者或继承的输入时，返回 `UNKNOWN`。
> - 将`command -v/-V`视为检查。 保持 `command -p`、嵌套替换和支持的内置包装器链可执行。
> - 保留现有的铁路 ID 和评估顺序。 实施 #2721 的同一管道获取下游命令策略。
> - 保持模式分析器 AST 扫描原始片段。 其现有的正则表达式语料库保留规范化的文本。

更改的路径：

- `openhands-sdk/openhands/sdk/security/_shell_ast.py`
- `openhands-sdk/openhands/sdk/security/defense_in_depth/pattern.py`
- `openhands-sdk/openhands/sdk/security/defense_in_depth/policy_rails.py`
- `openhands-sdk/openhands/sdk/security/defense_in_depth/shell_semantics.py`
- `tests/sdk/security/defense_in_depth/test_policy_rails.py`
- `tests/sdk/security/defense_in_depth/test_shell_semantics.py`
- `tests/sdk/security/test_shell_ast.py`

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; enyst](https://github.com/OpenHands/software-agent-sdk/pull/5724#pullrequestreview-5495736400)：HUMAN：我的智能体声称它重现了一些问题，我不确定 1 是否值得修复，但也许是？ 2 对我来说似乎相当合理 fwiw > 在 f1b6ca1 中发现了三个可操作的问题。 我建议 COMMENT 待修复。 > 1. [P1]可执行文字脚本变为LOW。 [policy_rails.py:209](https://github.com/OpenHands/software-agent-sdk/pull/5724/files) > eval 'dd of=/dev/sda' 和 bash <<<'mkfs.ext4 /dev/sda1' change from HIGH → LOW. The scanner only follows -c script operands, skipping these executable payloads. With PolicyRailSecurityAnalyzer and ConfirmRisky alone, confirmation is bypassed. Scan literal eval arguments and shell stdin scripts. > 2. [P2] 捕获的curl 输出错误地触发了管道导轨。 [policy_rails.py:377](https://github.com/OpenHands/software-agent-sdk/pull/5724/files) > response=$(curl x) \| jq . LOW 的变化
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5724#pullrequestreview-5495989910)：_此评论由 AI 智能体 (OpenHands) 发布。_范围：此 PR 属于此处（SDK 拥有的安全分析器，#2721 的一部分）。 根据基础 `acca181` 和当前头部 `f1b6ca1` 进行审查； CI 在这个头上是绿色的，`uv run pytest tests/sdk/security` 复制了所述的 `646 passed, 7 skipped, 10 xfailed`。 轨道 ID、排序和获取 `node`/nested-`-c` 的改进是真实的。 针对基本正则表达式行为，在这个头上展示了三个发现； 每一个都是在受支持的路径上的行为改变，而不是风格上的缺陷。 **1. 可执行文字脚本回归 HIGH -> LOW（安全）。**嵌套脚本操作数仅跟随运行程序的 `-c` 操作数； `eval` 参数和 shell stdin 脚本不是。 `eval 'dd of=/dev/sda'`、`bash <<< 'mkfs.ext4 /dev/sda1'` 和 `bash <<< 'dd of=/dev/sda'` 是基本寄存器中的 `HIGH`
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5724#pullrequestreview-5497694257)：_此评论由 AI 智能体 (OpenHands) 发布。_范围：此更改属于此存储库（SDK 拥有的安全分析器，#2721 的一部分），并继续 shell 到 AST 的迁移。 在头部 `99c7901e` 与基础 `acca181a` 进行审查。 CI在这个头上是绿色的，`uv run pytest tests/sdk/security`复制了所述的`646 passed, 7 skipped, 10 xfailed`。 我重新检查了之前关于这个头的评论的三个发现（真实`EnsembleSecurityAnalyzer([PolicyRailSecurityAnalyzer(), PatternSecurityAnalyzer()])`，默认`propagate_unknown=False`，`ConfirmRisky`）：1。 可执行的文字脚本（固定）。 `eval 'dd of=/dev/sda'`、`bash <<< 'dd of=/dev/sda'`、`bash <<< 'mkfs.ext4 /dev/sda1'`又是`HIGH`。 2. 捕获的提取输出（已修复）。 `response=$(curl x) \| jq .`和``out=`curl x` \| jq .``又是`LOW`。 3. 全局删除 (fi
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5724#pullrequestreview-5497798409)：_此评论由 AI 智能体 (OpenHands) 发布。_ 重新评论 head `99c7901`（取代之前对 `f1b6ca1` 的评论）。 我重新获取了 PR 的评论/帖子，链接到问题 #2721，以及头的检查运行，并在当前头版本上重新验证了以下所有声明，与基线 `acca181` 相比。 **我验证的内容** - 之前审查的所有三个发现都固定在这个头上。 `eval 'dd of=/dev/sda'`、`bash <<< 'dd of=/dev/sda'` 和 `dd 2>/dev/null of=/dev/sda` 重定向表单现在返回 `HIGH`； `response=$(curl x) \| jq .`回到`LOW`； 良性`rm *.o`/`rm -- ./build/*.o`例又是`LOW`。 作者在线程`4252363867`/`4252363873`/`4252363881`中的回复是准确的。 - `UV_CACHE_DIR=/tmp/uv-cache-review2 uv run pytest -q tests/sdk/security` → `775 passed, 7 skipped, 10 xfailed`。 - 唯一失败的检查
- [评论； APPROVED; 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5724#pullrequestreview-5498437112)：谢谢！
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4252363867)：可执行文字脚本从 `HIGH` 回归到 `LOW`。 `static_shell_script` 仅从运行程序的 `-c` 操作数中提取嵌套程序，因此 `eval 'dd of=/dev/sda'`、`bash <<< 'dd of=/dev/sda'` 和 `bash <<< 'mkfs.ext4 /dev/sda1'` 现在都返回 `LOW`。 在 `acca181` 这里，这三者返回 `HIGH` （`dd ... of=/dev/` 和 `mkfs.` 正则表达式没有检查上下文），并且在 `_evaluate_rail` 这里，每个返回 `LOW`，没有 `UNKNOWN` 回退方案。 当智能体配置有 `PolicyRailSecurityAnalyzer` + `ConfirmRisky`（无 `PatternSecurityAnalyzer`）时，通过 `eval`/herestring 的破坏性写入不再达到确认。 扫描文字 `eval` 参数和 shell stdin/herestring 脚本，而不仅仅是 `-c` 操作数。
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4252363873)：`response=$(curl x) \| jq .` 更改 `LOW` -> `HIGH`。 解析：管道LHS阶段是一个`variable_assignment`，其值为包含`curl`的`command_substitution`。 `_has_command_ancestor` 从 `curl` 节点出发，直到到达阶段 `variable_assignment` 时，它从未见过一个包含 `command` 节点，因此 `curl` 被接受为生产者，尽管替换输出被捕获到 `response` 并丢弃在管道中。 ``out=`curl x` \| jq .`` 的结果相同。 对于这个输入（正则表达式引擎需要下游解释器），基础 `acca181` 返回 `LOW`。而这个头返回 `HIGH`/`fetch-to-exec`.。排除包含在包围管道源命令中的赋值和命令替换生产者。
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4252363881)任何在中的通配符或括号单词 `rm` 现在参数被视为不确定的 arity，所以普通清理命令返回 `UNKNOWN` rather than `LOW`. 在这一点上 `PatternSecurityAnalyzer` reports `UNKNOWN` 为了 `rm *.o`, `rm build/*.log`, and `rm -- ./build/*.o`; 在基础上 `acca181` 所有三人都有 `LOW`. 因为 `ConfirmRisky` 默认值为 `confirm_unknown=True`这些无害的删除操作提示词确认。 `--` 它也不抑制它： `_extract_script_operand` handles `--` 对于选项解析，但这个分支独立评估 `argument_arity_is_uncertain` 在 `./build/*.o` 仍然在运行。 尊重此处的选项终止符（一旦） `--` 可以看到，扩展的文件名不能引入 `-r`/`-f` flags)，并考虑将不确定性限制在可能被合成的破坏性标志的场合。
- [review_comments; 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4253279745)：在`0bf3a2c`中修复。 扫描器现在通过有界嵌套源路径跟踪文字 `eval` 参数和 shell 标准输入源。 动态源返回`UNKNOWN`。 脚本文件输入、`-c` 输入数据和由稍后重定向替换的标准输入保留在嵌套扫描之外。
- [review_comments; 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4253280253)：在`0bf3a2c`中修复。 分配命令替换不再算作封闭管道的生产者。 直接获取管道和已知的输出转发阶段仍然被涵盖。
- [review_comments; 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4253280701)：在`0bf3a2c`中修复。 `rm` 扫描现在限制了 `--` 之前的扩展的不确定性，可以产生递归或强制选项。 普通路径 glob，包括 `*.o`、`build/*.log` 和 `rm -- ./build/*.o`，保留为 `LOW`。
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4253756304)Fetch-to-exec regresss `HIGH` -> `LOW` 当 fetch 和 interpreter 是同一个可执行段中的两个独立语句时。 `_scan_fetch_pipelines` 只有在 fetch 是下游解释器的生产者时，才会与 fetch 进行关联 *相同的*  `pipeline` 节点。 当 fetch 位于早期 `;`/newline 声明，相关性丢失，列车通过。 基础正则扫描了拼接后的段落为纯文本，并关联了任何 `curl`/`wget` with any `\| interpreter`所以这是一段行为回归不仅仅是语法改变。 在本段落中演示过 `EnsembleSecurityAnalyzer([PolicyRailSecurityAnalyzer(), PatternSecurityAnalyzer()])` (default) `propagate_unknown=False`) 和 `ConfirmRisky`: - `v=$(curl -s URL); echo "$v" \| python3` — 基础钢轨 `HIGH` -> 轨头 `LOW`, pattern `LOW`, ensemble `LOW` (无确认)
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4253845544)：通过管道传输到 shell 的文字 shell 文本在轨道、`PatternSecurityAnalyzer` 和默认整体上从 `HIGH` 回归到 `LOW`。 管道扫描仅将左侧视为潜在的获取源； 右侧的 shell 运行程序（其 stdin 是文字命令字符串）永远不会作为嵌套程序进行扫描。 Base `acca181` 捕获了这些，因为纯文本正则表达式与引用的载荷内的 `curl`/`wget` 和 `\| bash` 匹配。 在这一点上： - `printf 'curl x \| node' \| bash` → `LOW` (base `HIGH`) - `echo 'wget x \| node' \| bash` → `LOW` (base `HIGH`) - `printf '%s' 'curl x \| node' \| bash` → `LOW` (base `HIGH`) - `cat <<'EOF' \| bash` + `curl x \| node` in the body → `LOW` (base `HIGH`) 这些命令确实执行了载荷：`printf 'echo PWNED\n' \| bash` 打印 `PWNED`，`printf 'dd of=/dev/null' \| bash` 退出 0。 的
- [review_comments; 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4253890722)：谢谢。 我在`5cd5532`中再次检查了这些案例。 该 Rail 遵循 #2721 中的相同管道范围。 尽管获取的输出永远不会达到 Python，但段范围内的相关性将产生 `curl x; echo y \| python` `HIGH`。 `v=$(curl -s URL); echo "$v" \| python3`是一个真实的跨语句数据流案例。 支持它需要价值跟踪，而不是更广泛的token相关性。 `$(curl -s URL) \| python3` 已经返回 `UNKNOWN`； 然后，默认集成将其替换为`LOW`，这是一个单独的融合策略决策。 第 2c 阶段是否应该继续限制于同一管道结构流，并在 #2721 上跟踪跨语句数据流和 `UNKNOWN` 融合？ 如果是这样，我将保留此 PR 的界限。 如果在合并之前需要跨语句跟踪，则会大大扩展此PR。
- [review_comments; 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4254060291)：在`a8a4ef5`中修复。 当 shell 从同一管道读取时，rail 现在遵循文字 `echo`、`printf` 和引用的heredoc 输出。 它还通过有界嵌套 shell 启动保留描述符别名和继承的输入。 未解析的生产者、动态重定向、不明确的阶段和不支持的 shell 选项返回 `UNKNOWN`。 替换标准输入或输出的重定向仍然存在`LOW`。 四种报告的形式现在返回`HIGH`在轨道和默认集合边界处。 该安全套件通过了 851 项测试，跳过了 7 项测试，预计失败 10 项。 测试检测到 PR 中的所有 20 个目标突变，包括 10 个管道源突变。 Harmless Bash 探测器还确认了描述符和继承输入路径。
- [review_comments; 评论； Fieldnote-Echo](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4254086241)：@enyst 我想听听您的指导。 这部分重构已经变得相当大了。 我建议我们跟踪 #2721 的后续行动，否则这将变得无法审查。
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5724#discussion_r4254247084)：哦，是的，当然！

<a id="5660-fixagent-server-treat-an-empty-oh_secret_key-as-unset"></a>

### ＃5660：fix(agent-server)：将空OH_SECRET_KEY视为未设置

- 提交：`7bd668c9ab74f62c85745cd95adb503f53e7228b` (2026-10-13T07:50:19+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5660).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5660)。 家庭：F01、F02、F03、F29、F31、F32。

陈述意图：

> - `Config.secret_key` 上的 `field_validator` 通过返回 `_default_secret_key()` 将空白值（仅空或空白）视为未设置，与变量不存在时使用的回退方案相同。 第一个会话密钥在设置时使用； 否则就没有密码并记录现有警告。 这涵盖了环境变量、JSON 配置文件和直接 `Config(...)` 构造。
> - `/api/init` 将 `secret_key` 与 `model_copy` 一起应用，从而跳过验证器，因此 `_build_initialized_config` 现在也忽略空白 `secret_key`，并且应用其现有会话密钥回退方案。
> - 在 deferred-init 服务器上，`OH_SECRET_KEY` 也是 `POST /api/init` 的凭据，并且当未配置密钥时，`check_init_api_key` 使端点保持打开状态。 因此，空白值不会将封闭的端点变成开放的，`Config`记住配置了空白键（私有属性，而不是已序列化或在模式中），`/api/init`当这种情况发生时返回401，并且没有会话密钥填充。 真正未设置的密钥保留了今天的行为，并且会话密钥回退方案仍然是初始化信条

更改的路径：

- `openhands-agent-server/openhands/agent_server/config.py`
- `openhands-agent-server/openhands/agent_server/init_router.py`
- `tests/agent_server/test_config.py`
- `tests/agent_server/test_init_router.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5660#issuecomment-6076126751)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5660#pullrequestreview-5499136818)_这篇评论是由AI发布的智能体 (OpenHands)._ **范围检查：** 这个更改应该在这个仓库中。 `openhands-agent-server/` 拥有智能体-server `Config` 和 `/api/init` 生命周期，以及差异与之匹配 `#5660` umbrella issue #5688 ("treat a blank" `OH_SECRET_KEY` 如果无可用密钥，则缺失并关闭。 不需要存储库移动或产品/架构决策。 重新审核了新头版 `f736419141f7a76b084041499aadee77209edf85` (我的先前批准是 ) `253572c0`; 头部随着移动 `/api/init` 失败关闭的更改加上测试清理，因此需要一次全新的审查 **空白键处理仍然正确。**  `Config._empty_secret_key_is_unset` (config.py513) 使用 `_is_blank_secret`, so `""`, `" "`, `"\n"` 从环境变量中，有 JSON 配置文件，以及 di
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5660#discussion_r4242969634)只有真正空值才会被拒绝。 对于 env-var 和 JSON paths `load_config()` feeds `OH_SECRET_KEY` 通过 `Config.model_validate`, so `_default_secret_key()` 永远不会到达，这验证器这是唯一的一个检查 -- 一个只包含空白字符的值，例如 `OH_SECRET_KEY=" "` (e.g. 一个渲染了多余空格的模板传到这里来 `Config.cipher` 仍然构建 `Cipher(" ")`弱密情况 PR 目标。 已验证如下： `OH_SECRET_KEY=" "` 和 JSON  `{"secret_key": " "}` 两者都有效 `Cipher`, while `""` yields `None`. 问题 #5688 将仅限空白范围视为未设置。 考虑 `if value is not None and not value.get_secret_value().strip():`.
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5660#discussion_r4251636759)我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 已在 253572c0 中确认并修复。 `OH_SECRET_KEY=" "` 已经构建了一个 `Cipher` 从空白处，#5688将空白字符视为未设置，因此之前的“匹配”解释如下 `_default_secret_key`描述中的注释有误。 的验证器和 `/api/init` 现在路径在空值检查之前被去除。 测试覆盖了环境变量 [ ]`" "` 和 `"\n"`), the JSON 配置文件，直接 `Config(...)` 和初始化； 如果没有改变，六个新案例就会失败。 在协调事项 #5659 已落地，合并后留下了一个单个空初始化密钥保护的拷贝 `InitService.initialize`. --- 由生成的 [Claude Code](https://claude.ai/code)_

<a id="5520-fixsubagent-let-scoped-sub-agents-keep-conversation-local-tools-like-task_tracker"></a>

### ＃5520：fix(subagent)：让作用域子智能体保留像task_tracker这样的对话本地工具

- 提交：`c1dfd9c52cd3a1d87589b5054c8181d041d88859` (2026-10-13T14:29:07+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5520).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5520)。 家庭：F27、F33。

陈述意图：

> - **新`ToolDefinition.conversation_local`类标志**（默认`False`）。 它标记只读取和写入自己对话状态的工具。
> - **`SubAgentScope.missing_from` 忽略了会话本地工具。** 它是任务工具列表后面的唯一检查，`TaskManager` 开始检查和两个工作流工具，因此它们一起改变。
> - **`TaskTrackerTool` 设置标志。**所有其他工具仍像以前一样进行检查。

更改的路径：

- `openhands-sdk/openhands/sdk/subagent/scope.py`
- `openhands-sdk/openhands/sdk/tool/tool.py`
- `openhands-tools/openhands/tools/task_tracker/definition.py`
- `tests/tools/task/test_sub_agent_scope.py`

链接问题接受上下文：

- [#5519](https://github.com/OpenHands/software-agent-sdk/issues/5519)：[缺陷]：受范围约束的配置因缺少 task_tracker 而无法委派给通用智能体；当前状态为已关闭，关闭时间为 2026-10-13T12:29:09Z。

> - [ ] 工具可以声明它们只触及自己的对话状态，`task_tracker` 确实如此。 - [ ] `SubAgentScope.missing_from` 对于定义（列表）和构建子智能体（开始）都忽略此类工具。 - [ ] 提供 `general-purpose` 具有 `terminal`、`file_editor` 和任务工具但没有 `task_tracker` 的配置文件，并且子智能体与 `task_tracker` 一起运行。 - [ ] 子智能体需要委托智能体缺乏的任何其他工具仍然被拒绝。 ###安装方法uv/pip ###SDK版本1.53.0---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5520#issuecomment-5996780731)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5520#pullrequestreview-5495011899)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## PR #5520 范围检查的评论：此更改属于 `OpenHands/software-agent-sdk`。 它修改了SDK工具定义元数据和子智能体范围约束，这两个都属于这个仓库。### 我验证了 - **标题和正文匹配**: `32f5c6e7f805e54101f390f1a20a2953cce5fde1`（标题和正文未改变）。 链接问题 #5519 已通过 `bug`、`priority:medium`、`ready-for-dev` 开放。 - **CI**：当前头上没有运行失败/超时/需要操作的检查。 - **测试（在工作区中）**：`tests/tools/task/test_sub_agent_scope.py`（15个通过）、`tests/sdk/subagent`、`tests/sdk/tool`、`tests/sdk/profiles`、`tests/tools/task`、`tests/tools/workflow` — 614个通过。 两个新测试和更新的 `general-purpose` 期望通过。 有一个无关的失败，tests/sdk/subagent/test_subagent_loa
- [讨论； 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/5520#issuecomment-6127994465)：@simonrosenberg 我重新基于`main`（`e3a2682`，1.54.0），从头到尾检查了更改，CI 是绿色的：通过了 48 个检查。 3 个跳过的检查是 `Validate PR description`（不在草稿上运行）和两个 `.pr/` 清理作业。 **验证** - 单元测试：741 条通过了`tests/tools/task`、`tests/tools/workflow`、`tests/sdk/subagent`、`tests/sdk/tool` 和`tests/sdk/profiles`。 `main`和`scope.py`的`.pr/conversation_local_e2e.py`和智能体-服务器和Agent Canvas 模拟对象 LLM分支上的3个新或更改的范围测试失败，因此它们确实捕获了错误。 `main` 的 `scope.py` 显示原始拒绝，`Agent 'general-purpose' uses task_tracker, which this agent does not have.` - 子智能体的 `TASKS.json` 被写入 `conversations/<parent>/subagents/<sub-agent>/`。 即确认
- [讨论评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5520#issuecomment-6128021507)我重新合并了分支 PR 第5520条 `main` 并且端到端检查通过了 CI 是绿色的。 我没有做的事情就是填入  HUMAN 章节：该仓库的规则说 AI 智能体必须不要写，所以你需要自己添加这个注释。 **合并分支：** 分支现在在 `main` at `e3a2682` (1.54.0). 它重新建立基础，没有冲突，我强行推动了它。 **测试** - **单元测试：** 741 项任务和工作流通过子智能体，工具和配置测试套件。 当我重新放回 `main`在范围检查的版本中，这3个新的或更改的范围测试失败了，因此它们发现了错误 **实时检查：** 的 PR's script (`.pr/conversation_local_e2e.py`) 运行真实地智能体-server with Agent Canvas's scripted 模拟对象  LLM. 在此分支上，所有 6 项检查均通过。 与 `main`检查范围已放回，但仍然以原始错误： `智能体通用用途的使用 task_tr

<a id="5744-fixprofiles-preserve-disabled-skills-when-seeding-default"></a>

### ＃5744：fix(profiles)：默认播种时保留禁用技能

- 提交：`d6165a51cb158c0fd80eeb6ffac9cee2b4ce73e5` (2026-10-13T13:30:53Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5744).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5744)。 家庭：F21。

陈述意图：

> 将现有拒绝列表复制到种子配置文件中。 内联技能仍然不会成为积极的参考，未知的禁用名称仍然无害。

更改的路径：

- `openhands-sdk/openhands/sdk/profiles/seed.py`
- `tests/sdk/profiles/test_resolver.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5744#issuecomment-6146217379)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5744#pullrequestreview-5504221402)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论 ** 范围 ** — 属于此处。 该缺陷存在于该存储库拥有的 `openhands-sdk/openhands/sdk/profiles/seed.py` 中（SDK 配置文件/解析器/种子）。 问题 #5398 `ready-for-dev` 在这个仓库中。 OpenHands/OpenHands#17991 是下游画布启动症状。 没有必要进行跨回购移动。 **正确性** — 一行更改将硬编码的 `disabled_skills=[]` 替换为 `list(context.disabled_skills)`，将全局设置拒绝列表复制到种子 `OpenHandsAgentProfile` 中。 这符合解析器已建立的拒绝列表模型：`_build_openhands_settings`将`profile.disabled_skills`传递给解析后的`AgentContext`，`_apply_disabled_skills`过滤发现的目录，而目录中不存在的名称被视为文档中的无操作。 它

<a id="5409-feat-launch-inline-agent-profiles-and-per-launch-llm-overrides"></a>

### ＃5409：壮举：启动内联智能体配置文件和每次启动 LLM 覆盖

- 提交：`4011cb5d4fd508964fe210df9a50af7d2f19d29d` (2026-10-13T13:42:51Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5409).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5409)。 族：F01、F04、F05、F06、F07、F10、F12、F16、F18、F19、F20、F21、F22、F27、F29、F30、F31、F32、F33、F34。

陈述意图：

> - `StartConversationRequest.agent_profile` 启动未保存的配置文件。 它的解析与存储的一模一样，从未保存，并记录为`launched_agent_profile.inline`。 它与其他智能体来源是相互排斥的。
> - `AgentLaunchAdditions.llm_profile_ref` 启动一个 OpenHands 配置文件和另一个 LLM 配置文件，而不修改该配置文件。 其记载于`launched_agent_profile.llm_profile_ref`。 对于 ACP 配置文件和非配置文件源，它被拒绝。
> - OpenAI 网关启动活动的智能体配置文件，在首次使用时播种 `default`。 OpenHands 配置文件获取模型的 LLM 配置文件作为覆盖。 ACP 配置文件运行自己的模型，就像之前的 ACP 设置一样。 无论哪种类型，未知型号仍然是 404。
> - Docker：主机解析内联配置文件及其存储的覆盖，并且仅转发 `agent_settings`。
> - `/server_info` 报告 `agent_launch_pipeline_v1`，因此画布可以对这些字段进行门控。
> - `SendMessageRequest` 移动到 `openhands.sdk.conversation.message_request`，并且仍然从 `request` 重新导出。 这让请求模型 i

更改的路径：

- `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `openhands-agent-server/openhands/agent_server/docker_runtime/routers.py`
- `openhands-agent-server/openhands/agent_server/launch.py`
- `openhands-agent-server/openhands/agent_server/openai/service.py`
- `openhands-agent-server/openhands/agent_server/server_details_router.py`
- `openhands-sdk/openhands/sdk/conversation/message_request.py`
- `openhands-sdk/openhands/sdk/conversation/request.py`
- `openhands-sdk/openhands/sdk/launch/resolve.py`
- `openhands-sdk/openhands/sdk/profiles/agent_profile.py`
- `openhands-sdk/openhands/sdk/settings/model.py`
- `tests/agent_server/docker_runtime/test_mediation.py`
- `tests/agent_server/test_agent_profile_conv_start.py`
- `tests/agent_server/test_launch_architecture.py`
- `tests/agent_server/test_launch_parity.py`
- `tests/agent_server/test_openai_gateway_launch.py`
- `tests/agent_server/test_openai_gateway_settings.py`
- `tests/agent_server/test_server_details_router.py`
- `tests/cross/test_remote_conversation_live_server.py`
- `tests/sdk/launch/test_resolve.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5409#issuecomment-5962076201)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews COMMENTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5371963931)_这篇评论是由AI发布的智能体 (OpenHands)._ ## 判决：需要更改 OpenAI 网关了 ACP  智能体  `_create_conversation_request` (openhands-agent-server/openhands/agent_server/openai/service.py现在，换行符 ~252-273 也总是构建 `AgentLaunchAdditions(llm_profile_ref=<model profile>)` 并将其与之配对 *active*  智能体通过  `agent_profile_id`. `resolve()` 拒绝 `llm_profile_ref` 对于任何非-OpenHands profile (agent_launch_additions.llm_profile_ref 只适用于  OpenHands  智能体 Profile) 当活动智能体 Profile is ACP-kind (an ACP profile是从的 `ACPAgentSettings` by `build_seed_profile`, 所以这是一个第一类支持的配置），每  `/v1/chat/completions` 和 `/v1/responses` 现在请求失败了 422。 我在真正的发布中复制了这个
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5398998714): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 结论：先前的阻塞发现已解决； 没有新的材料问题审查了新的头`23e3cb72`（分支在`35410b3af`处合并了`main`）。 我之前的 `CHANGES REQUESTED` 标记 `_create_conversation_request` 无条件地将活动 `agent_profile_id` 与 `AgentLaunchAdditions(llm_profile_ref=...)` 配对，因此 ACP 活动配置文件 422 到 `/v1/chat/completions` 和 `/v1/responses`。 这是固定的：现在仅为 `OpenHandsAgentProfile` (openai/service.py:277) 提供覆盖，并且 `simonrosenberg` 在线程中确认了这一点。 我再次核实了这个环节，与实际的发布管道进行了对比。### 验证已完成 - **ACP 门路恢复。** 重现了 `_create_conversation_request` 和 `launch_source`，使用了一个 ACP 活动的配置和一个现有的模型
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5399108736)_这篇评论是由AI发布的智能体 (OpenHands[已弃用] `d3a4b3a3` 自头版以来唯一的变化是 `23e3cb72`) 是自动的 `chore: Remove PR-only artifacts` commit，删除了四个 `.pr/*.py`/`.pr/*.md` 证据脚本。 源代码树未发生变化。 `git diff 23e3cb72..d3a4b3a3 -- . ':(exclude).pr'` 因为为空，所以之前审查过的每条代码路径在这里都相同。 这是重新确认，不是新的代码审查。 [### 本段验证] **CI 为了 `d3a4b3a3`.** 所有检查都通过了 `sdk-tests`, `agent-server-api`, `agent-server-tests`, `cross-tests`, `integration-test`, `REST API (OpenAPI)`, `Persisted settings`, `public-type-budget`, `security`, `acp-live-tests`, `unresolved-review-threads`; 仅 `cleanup-*` are skipped. - **聚焦的套件。**  `tests/sdk/launch`, `tests/sdk/conversat
- [评论； COMMENTED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5403366068): PR 描述了运行中的智能体-服务器和 Docker 运行，但我无法找到一个附带的截图/视频或当前头运行时的可独立验证的成果。 此功能跨越配置文件解析、网关/ACP 启动和 Docker 传输层路径。 请附上当前头证据，显示真实支持的入口，前后失败或行为，以及相关模型/模式请求和证明结果。 存储库审查指南需要面向生产的运行时证据，而不是单独的声明或单元测试。 此评论由 AI 智能体 (OpenHands) 代表 Graham Neubig 生成。
- [评论； DISMISSED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5409086070): 🟡 **口味评分：可接受**——启动路径整合方向一致，当前检查为绿色，但Canvas面向的启动变更的接受证据尚不完整。 **[SECURITY / SUPPLY-CHAIN SCREEN]** - 我检查了 PR-头 `AGENTS.md` 和 `.agents/skills/custom-codereview-guide.md`，以及完整的更改文件列表和补丁，以及 CI/工作流表面，这些输入被认为是不可信的。 我在此差异中没有发现提示词注入载荷、硬编码凭据、依赖源更改、恶意脚本或不安全的 CI 权限扩展。 **[TESTING / EVIDENCE GAP]** - [PR描述 / `.pr/inline_profiles_e2e.md`] 文本报告了API和Docker运行，但没有实际Agent Canvas界面启动内联配置并应用每次启动的LLM覆盖。 这改变了续
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5494992744)：_此审查由 AI智能体（OpenHands）发布。_ ## 最新提交 `f6605362` 中无实质性代码缺陷；此版本重放到更新的 `main`（`e3a26821`）之上，并新增一个提交 `fix(agent-server): launch the global settings through the gateway when no profile is active`。 PR 自己与新基础的差异是 20 个文件。 我重新阅读了代码，重新运行了聚焦的测试套件，并检查了当前-头 CI。### 与上一次审查的头相比，有什么变化新提交的提交解决了我的上一次通过的非阻塞观测结果：当存在配置文件但没有活动指针时，网关不再返回 `409`。 `_create_conversation_request` 现在启动 `stored or build_seed_profile(settings.agent_settings, settings.active_profile)` — 全局设置作为未保存的内联配置文件 (openai/service.py:265-282) — 并由新测试 `test_without 覆盖
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5409#pullrequestreview-5504342300): _这篇评论是由人工智能发布的智能体 (OpenHands)._ ## 对 head `8e961107` 的重新审查该 head 从我上次批准的修订版 (`9b5a5b0c`) 中通过两个非产品提交 — `979a81e1`（记录配置文件 API/Docker QA）和 `8e961107`（自动 `.pr/` 清理）推进 — 并且作者发布了后续证据评论。 我重新核实了当前状态，而不是依赖之前的通过。### 我核实的内容 - **产品代码未改变。** `git diff 9b5a5b0c 8e961107`为空，且两个提交都指向相同的树（`47eaae64`）。 唯一的增量是`.pr/`证据及其删除。 所以我批准的代码就是这个分支的代码。 - **之前的阻断发现仍然固定。** `_create_conversation_request`仍然阻止了重置：`llm_profile_ref=llm_profile if isinstance(profile, OpenHandsAgentProfile) else None`，所以ACP仍然活跃
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5409#discussion_r4149317769)：`_create_conversation_request` 现在始终将 `AgentLaunchAdditions(llm_profile_ref=<model profile>)` 与活动配置文件的 `agent_profile_id` 设置在一起。 `resolve()` 拒绝任何非 OpenHands 配置文件的 `llm_profile_ref`（“agent_launch_additions.llm_profile_ref 仅适用于 OpenHands 智能体配置文件”）。 ACP 类型的活动智能体配置文件是受支持的配置（`build_seed_profile` 从 `ACPAgentSettings` 中种子一个），因此针对它的每个 `/v1/chat/completions` 和 `/v1/responses` 请求现在都会失败 422。 根据真实的启动管道进行复制（`launch_source`，ACP`agent_profile_id`加上`llm_profile_ref`引发`AgentLaunchError`）； 在基础修订版上，网关将模型的 LLM 折叠到 `agent_settings` 中，并且从未触及配置文件，因此 ACP 启动有效。 网关没有 ACP 防护，现场网关测试
- [review_comments; 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/5409#discussion_r4153497671)已修复。- 一个 ACP 现在，活跃的配置文件通过网关启动 `llm_profile_ref`由于其服务器运行自己的模型。 安 OpenHands 配置文件仍然得到模型的 LLM 将 profile 作为覆盖项。- 请求的模型在前端与之前相同的 404/503/400 映射进行检查，因此未知模型对于任何类型都保持为 404 `tests/agent_server/test_openai_gateway_launch.py` 运行网关的请求 `launch_source` 对于两种情况。 修复已撤销，  ACP 测试失败了 `AgentLaunchError` 你报告了。- 检查 canvas 模拟对象  ACP 服务器 (`.pr/gateway_acp_e2e.py`): `/v1/chat/completions` 返回 200 对应 #5406，返回 422 对应 `a2507336`和在这一方面。 未知模型返回 404、422 和 404。
- [讨论； 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/5409#issuecomment-6127607991)：@OpenHands 变基并解决所有评审意见，并对功能分支进行完整的 e2e 验证
- [讨论； 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/5409#issuecomment-6146465809)：将实际的 PR 头刷新到当前的 main 上，而无需强制推送：`9b5a5b0c8`（main `c1dfd9c52`）。 更新后的分支上的 QA： - 通过了 154 项重点启动、配置文件、网关和 Docker 中介测试； 相关预提交钩已通过。- 本地真实Agent Server，保存OpenHands `claude-sonnet-4-6` 凭据，真实标准输入FastMCP `qa_echo`：存储`default`，相同`default-copy`，以及内联配置都完成了MCP次调用(`QA_MCP_ECHO:PROFILE_API_LIVE_OK`)。 每条线路智能体都具有完全相同的 `tools=[glob]`、相同的单个 MCP 服务器和角色以及相同的机密范围。 记录了内嵌源代码`inline=true`。 - 真实 `/v1/chat/completions` 返回 200 / `GATEWAY_PROFILE_QA_OK`。 阅读其对话可确认活动配置文件的 `glob` 工具、角色和 `llm_profile_ref=qa-live` 覆盖已保留。 - 当前
- [讨论； 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/5409#issuecomment-6146690724)：当前运行时证据现在可以在 [agent-profile-api-qa.json](https://github.com/OpenHands/software-agent-sdk/blob/979a81e11/.pr/agent-profile-api-qa.json) 处独立读取，已固定，因此自动 `.pr/` 清理无法破坏链接。 该记录在来源 `9b5a5b0c8` 处支持 API 入口，具有真实的 Sonnet 和真实的 MCP/终端执行。 新的 Docker 运行使用当前头的 arm64 最小图像（`9b5a5b0-python-minimal-arm64`，摘要 `sha256:ae5ebd3a9983fcb3012dccb336acb47bee607301e0a6ba85fa3f72dbd7bbbb9d`）。 存储的配置文件要求终端+浏览器； 预览版和正在运行的容器都只有终端。 真实终端以 exit 0 运行 `printf DOCKER_PROFILE_API_OK`，并且保留角色/后缀/出处。 这直接执行主机解析→加密传输层→容器最终确定。 `979a81e11` a

<a id="4960-featagent-server-accept-additional-skills-when-launching-an-agent"></a>

### ＃4960：feat(agent-server)：启动智能体时接受额外技能

- 提交：`27308a4b3f23a40177c9f444f9e35136c8a0d3fb` (2026-10-13T18:08:44+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/4960).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-4960)。 家庭：F04、F06、F21、F30、F33、F34。

陈述意图：

> - `AgentLaunchAdditions.skills: list[Skill] | None` — 部署提供的技能，在已经承载部署上下文的通道上，在 `system_message_suffix_append` 之后的 `finalize` 中应用。
> - `finalize` 按名称合并它们，并使用两条规则来防止其成为后门：
>   - **resolved 智能体赢得碰撞** — 它的技能来自其简历和服务器本身的来源，权威的观点（和 `AgentContext` 因为不允许重复的名称，合并时必须去重，而不是拼接。
>   - **重新应用上下文的`disabled_skills`拒绝列表**，因此添加无法恢复配置文件关闭的某些内容。
> - 默认为`None`； 没有上下文的智能体仍然会收到它们。
> 
> 这是故意的*渠道*，而不是关于哪个目录获胜的决定。 #3979 是解决这个问题的地方——评论中的选项 (2)。 如果服务器克隆最终拥有该目录，则该字段无需花费任何费用即可闲置。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `4011cb5d4fd5` 相比。
> 
> ```差异
> ---基础公共O

更改的路径：

- `openhands-sdk/openhands/sdk/conversation/request.py`
- `openhands-sdk/openhands/sdk/launch/finalize.py`
- `tests/agent_server/docker_runtime/test_mediation.py`
- `tests/agent_server/test_agent_launch_additions.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/4960#issuecomment-5637730385)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/4960#pullrequestreview-5506363353)_这篇评论是由AI发布的智能体 (OpenHands)._ 评审过的头部 `62e783c` 匹配了请求的 SHA). 范围检查：更改已部署到此仓库的分支 SDK/agent-server surface (`openhands.sdk.conversation.request.AgentLaunchAdditions` + `openhands.sdk.launch.finalize`), 是累加的，不会改变 OpenAPI  `/api/**` 超出一个可选的合同模式 property. `#3979` 已被关闭并被取代 `#4018`, and this PR 故意只针对渠道，而不是库-兼容决策，因此没有跨仓库移动或维护审查。 [已验证] 工作区代码：- ** `skills`.**  `Field(default=None, exclude_if=lambda v: v is None)` drops `skills` 从两个方面 `model_dump()` 和 `model_dump(mode="json")` 当未设置时，非空时会序列化它。 我在此基础上进行了实证验证 Pydantic 2.13.5 (the 工作区
- [讨论； 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/4960#issuecomment-6146467628)：刷新到主目录，然后修复了`a638c0ec5`中的两个具体错误：1。 重复的新提供的技能名称绕过了初始碰撞集。 `POST /api/conversations` 添加两个 `duplicate` 返回 500 (`Duplicate skill name found`)。 在尊重已解决的技能和拒绝列表之后，合并现在保留第一个提供的技能。 2. ACP 原生采购在添加之前运行，因此客户端技能是在之后注入的。 阅读与`include_skills=true`的实际对话显示了本机模式下提供的技能。 本地采购现在在合并后运行并将其剥离； 托管采购保留了它。 HTTP 实际上，ACP 之前/之后：- 重复添加：500 → 201，保留一个技能。- 自然生成的技能：1 → 0（未修剪的对话响应）。- 两个回归在修复之前失败。 集中发布/添加/奇偶校验
- [讨论； 评论； 所有手都机器人](https://github.com/OpenHands/software-agent-sdk/pull/4960#issuecomment-6147319790): ### ⏳ 等待检查的审查当前头`62e783c4db80`仍然有检查尚未完成，因此没有开始审查对话： - `agent-server-tests` - `cross-tests` - `sdk-tests` 无需采取行动。 每次对头部进行检查后，定期扫描重试都会报告结论。 _这是一个自动检查 - 没有使用人工智能来生成此comment._

<a id="5727-verify-agent-server-a-daily-maintenance-pass"></a>

### ＃5727：验证-智能体-服务器：日常维护通行证

- 提交：`733f06edac353d595f0dadac476ee5011b53586f` (2026-10-13T22:19:08+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5727).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5727)。 系列：无需产品运行时间。

陈述意图：

> - 新的 `references/daily.md`，链接自 `SKILL.md`、`maintenance.md` 和 `adaptation.md`。
> - `map baseline [--set]` 读取或移动基线； `map check` 验证了它（现在是 `main@<sha> (<date>)`）。
> - `map owners` 不带参数与基线不同并列出了系列。
> - `evidence report --baseline` 列出新失败的、新通过的、未检查的和冲突的行。 账本按尝试时间进行比较，因此 `--runs` 顺序不会改变判决。

更改的路径：

- `.agents/skills/verify-agent-server/SKILL.md`
- `.agents/skills/verify-agent-server/references/adaptation.md`
- `.agents/skills/verify-agent-server/references/daily.md`
- `.agents/skills/verify-agent-server/references/feature-map/README.md`
- `.agents/skills/verify-agent-server/references/maintenance.md`
- `.agents/skills/verify-agent-server/scripts/control_agent_server.py`
- `tests/cross/test_verify_agent_server_skill.py`

链接问题接受上下文：

- [#5751](https://github.com/OpenHands/software-agent-sdk/issues/5751): verify-智能体-server: 智能体-server 特征图的日常维护通行证 — 当前状态已关闭，已于 2026-10-13T20:19:10Z 关闭。

> - [ ] `references/daily.md` 描述该通道并与 `SKILL.md`、`maintenance.md` 和 `adaptation.md` 链接。 - [ ] `control-agent-server map baseline [--set SHA]` 读取并移动基线，`map check` 验证它。 - [ ] `control-agent-server map owners`，不带参数，列出自基线以来更改的系列。 - [ ] `control-agent-server evidence report --baseline <run>` 列出新失败的、新通过的、未检查的和冲突的行，无论运行的顺序如何。 - [ ] `tests/cross/test_verify_agent_server_skill.py` 涵盖了这些命令。 ### 优先级/严重性中 ### 估计范围中 ### 功能区域 - [x] 测试/开发工具 ### 附加上下文在 #5727 中实现。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5727#issuecomment-6132087316)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5727#pullrequestreview-5508491678)：**审查：COMMENT — 将批准决定交由维护者**（仓库审查指南禁止 REQUEST_CHANGES，因此遇到实质性问题时应使用此信号）。 对照 `.agents/skills/custom-codereview-guide.md` 审查了标题 `cd5ab84`。 **在当前头验证** - `uv run pytest tests/cross/test_verify_sdk_skill.py tests/cross/test_verify_agent_server_skill.py -q` → 67 通过。 - `sdk-map check` / `owners` / `baseline` / `rotation` 和 `control-agent-server map check --no-routes` / `baseline` / `rotation` 全部返回干净 JSON。 新的 `Maintenance baseline: main@<sha> (<date>)` 行进行解析，轮换覆盖所有 21 个 SDK 系列（以及所有 34 个智能体服务器系列），一周内没有重复。 这些技能是非产品工具，因此兼容性/安全检查点不适用。 **材料发现——当前头CI是r
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5727#pullrequestreview-5509411476)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对 `.agents/skills/custom-codereview-guide.md` 审查了头 `6d1c160`。 `enyst` 在之前的机器人审查后回复，所以这是一个新的通行证。 **在当前头验证**-`uv run --frozen pytest tests/cross/test_verify_agent_server_skill.py -q`→45通过。 - `ruff check` 两个已更改的 Python 文件 → 清理。 - `control-agent-server map check` → `ok: true`，34 个文件，935 个 ID。 `map baseline` → `main@8ba966d1…`，此后提交了 43 次。 `map owners`（无参数）差异 `baseline..HEAD` 并列出 25 个更改的系列以及 `unowned_product_paths`。 - `evidence report --baseline` 适用于运行目录和裸 `ledger.jsonl`； 比较是按每行的 `at` 时间排序的，因此 `--runs` 顺序不能改变判决（由 `compare_ledgers` 确认并直接 CLI 运行
- [讨论评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5727#issuecomment-6153353825)我是人工智能智能体帮助 Engel Nyst (@enyst) 进行项目工作。 感谢您的评论。 这里就是每个点所站的位置：- **PR 描述检查（阻塞）：已解决。** 现在，署名行位于  `AGENT:`, so `HUMAN:` 这是第一个可见的行，Issue Number部分链接到#5751`Fixes #5751`, labeled `ready-for-dev`). 验证 PR 描述“现在生效了，” CI 当前分支是绿色的 **S18 易出错的测试和未托管的 `utils/redact.py`.** 两者都来自 SDK 已经移出这个的 map PR 因此，它们将在那里处理。 `redact.py` 将得到所有者或一句话的原因。 的 S18 失败 (`test_exit_preserves_parent_lifecycle_and_cleanup`, with `cleanup` 该事件发生了两次，但只发生了一次，然后在三次重播后消失。 有一次我还没有提交； 如果再次出现，将被归档。

<a id="5728-verify-agent-server-a-known-bug-reproduces-only-with-its-documented-failure"></a>

### ＃5728：verify-智能体-server：已知错误仅在其记录的故障中重现

- 提交：`dfd8fe8fb39e6f6d73ba35ce524cac83d94e0d96` (2026-10-13T22:28:54+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5728).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5728)。 系列：无需产品运行时间。

陈述意图：

> - **标记合约。**现在，每个标记都命名了 bug 自己的症状：`# bug: PREDICATE`，由 `PATH OP [VALUE]` 子句和 `&&` 连接组成。 它们像 `--check` 一样与该行上最后一个 `control-agent-server` 调用打印的 JSON 进行匹配。 `exit N` 仅作为最后手段保留。 这是之前和之后的`F08.secrets-bad-value`：
>   ```嘘
>   # 之前
>   控制-智能体-服务器 API POST "/api/conversations/$KID/secrets" --JSON '{"机密": {"QA_F08_NUMBER": 5}}' \
>     --expect 422 --save F08.secrets-bad-value/number # 错误
>   # 之后
>   控制-智能体-服务器 API POST "/api/conversations/$KID/secrets" --JSON '{"机密": {"QA_F08_NUMBER": 5}}' \
>     --expect 422 --save F08.secrets-bad-value/number # bug: status eq 500 && response.body.exception 包含“'int'对象没有属性'pop'”
>   ```
>   正确行为的 `--expect 422` 断言保持不变。
> - **`assert` 动词。** `control-agent-server assert --value|--json FILE|stdin --check ...` 检查配方计算的值并打印它。 过去只表示“jq 是 False”的比较线现在将值命名为 th

更改的路径：

- `.agents/skills/verify-agent-server/SKILL.md`
- `.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md`
- `.agents/skills/verify-agent-server/references/feature-map/F03-deferred-init.md`
- `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`
- `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md`
- `.agents/skills/verify-agent-server/references/feature-map/F06-conversation-events.md`
- `.agents/skills/verify-agent-server/references/feature-map/F07-session-socket.md`
- `.agents/skills/verify-agent-server/references/feature-map/F08-confirmation-security-secrets.md`
- `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`
- `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md`
- `.agents/skills/verify-agent-server/references/feature-map/F11-goals.md`
- `.agents/skills/verify-agent-server/references/feature-map/F12-runtime-and-credentials.md`
- `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`
- `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`
- `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`
- `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md`
- `.agents/skills/verify-agent-server/references/feature-map/F17-workspaces-registry.md`
- `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md`
- `.agents/skills/verify-agent-server/references/feature-map/F19-mcp.md`
- `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md`
- `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md`
- `.agents/skills/verify-agent-server/references/feature-map/F22-meta-profiles.md`
- `.agents/skills/verify-agent-server/references/feature-map/F23-llm-catalog-and-connections.md`
- `.agents/skills/verify-agent-server/references/feature-map/F24-openai-subscription.md`
- `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`
- `.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md`
- `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`
- `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`
- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md`
- `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`
- `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`
- `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`
- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `.agents/skills/verify-agent-server/references/maintenance.md`
- `.agents/skills/verify-agent-server/references/mapping.md`
- `.agents/skills/verify-agent-server/scripts/control_agent_server.py`
- `tests/cross/test_verify_agent_server_skill.py`

链接问题接受上下文：

- [#5726](https://github.com/OpenHands/software-agent-sdk/issues/5726): [Bug]: 验证 xfail 可以接受标记命令中的不相关错误 — 当前状态已关闭，已关闭 2026-10-13T20:28:57Z。

> - [  ] A `known bug` bullet声明了其文档中的失败身份（状态、字段/错误或可观察状态），以及保留的现有正确行为声明 [  ] 当标记的命令文档中描述的失败时，该圆点报告失败 `xfail`. - [  ] 当标记的命令因无关错误失败，且错误的状态/字段/错误/可观察状态与声明的失败不匹配时，将报告该星号 `fail` 并且不被计入已复制的 bug [  ] 匹配使用声明的失败身份，而不是整个转录：具有不同详情文本但相同声明身份的失败仍然计数，而其他内容不同则不会触发匹配 [  ] A `known bug` 报告了被标记的命令现在退出0（正确行为） `xpass` 和 `map run` 表明标记/食谱必须更新，因为今天 [  ] 在标记的命令（安排/设置步骤）之前出现的失败，以及一个食谱超时 are reported `fail`, not `xfail`. - [  ] 没有的点号 `known bug` 标签仍然分类 `pass`/`fail` 如之前一样 [  ]  `map check` 验证声明的失败标识，并拒绝缺失或格式不正确的谓词（而不是无声地接受标记） [  ] 验证技能的文档（标记合同在） `references/mapping.md` 和 `references/maintenance.md`) 描述了所需的谓词以及依赖于它的两次基线/两次修复程序 [  ] 代表性的食谱 (`F08.secrets-bad-value`已更新以声明其文档中的 500 错误AttributeError

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5728#issuecomment-6132726392)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5728#pullrequestreview-5496968245)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围该更改属于此存储库：它修改了 in-repo `.agents/skills/verify-agent-server/` 技能（其控制 CLI、特征图和文档）以及 `tests/cross/test_verify_agent_server_skill.py`。 #5726 这个链接的 issue 明确保留了这个仓库中的兄弟分支 `OpenHands/automation`，所以没有错位的范围。## 验证 - 重新获取的头 `6048c5bad8cfe51393a9892cb09153f1b988c9f3` 仍然符合审核要求。 PR 处于打开状态、不是草稿、没有标签，且此账号此前未发布审查或评论。- 当前提交的全部 GitHub Actions 检查结果为 `success`，仅 `cleanup-after-merge`/`cleanup-on-approval` 被跳过； 没有失败或待处理的所需检查。 - `uv run pytest tests/cross/test_verify_agent_server_skill.py` → 59 通过。 -`控制-智能体
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5728#pullrequestreview-5503188777): 架构看起来不错：跑步者保留了正确的行为断言，单独匹配了文档中的失败，捕获了观测结果，并在清理之前，以及在缺失路径和传递性先决条件缺失时，进行了保护。 当前头CI和受控服务器回归覆盖范围支持分类器更改。 这解决了一个有价值的中等优先级验证完整性问题。 非阻塞建议：添加一个代表性的真实基线/固定回放对（例如 F08.secrets-bad-value），显示未修复服务器的 xfail，修复服务器的 xpass，使用相同的命令和前置条件。 这将完成部分现场重播和受控 HTTP 测试之外最强有力的验收证据。 审查了头 c3b8af88bfd4a258f941ad6bf06e25b4db57f89c。 本次审查中未执行独立测试。 [RISK ASSESSMENT]
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5728#issuecomment-6154544004)：感谢您的评论。 这是您为 `F08.secrets-bad-value` 建议的基线/固定对，在 c3b8af8 上使用 PR 的 CLI 运行，并且两侧具有相同的配方、标志和先决条件（SKILL.md 中的 2+2 规则，“验证现有修复”）： ```sh control-agent-server map run --file F08 --only F08.secrets-bad-value --fresh --repeat 2 --checkout <unfixed checkout> # baseline control-agent-server map run --file F08 --only F08.secrets-bad-value --fresh --repeat 2 # fixed ``` \| 服务器 \| 尝试 1 \|尝试 2 \| 标记的调用观察到 \| \|---\|---\|---\|---\| \| 未修复（此分支，服务器代码与 `main` 相同） \| `xfail` \| `xfail` \| 500、`"exception": "'int' object has no attribute 'pop'"` \| \| 固定（下面有划痕补丁） \| `xpass` \| `xpass` \| 422、`value_error` 位于 `body.secrets` \| 在所有四次运行中都通过了先决条件。 “固定”的

<a id="5754-fixsdk-skip-sub-agents-whose-skill-is-missing-instead-of-failing"></a>

### ＃5754：fix(sdk)：跳过技能缺失而不是失败的子智能体

- 提交：`a430c778bd8a720234ce4674014ac292a0326670` (2026-10-13T23:39:48+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5754).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5754)。 家庭：F27。

陈述意图：

> - `register_file_agents` 和 `register_plugin_agents` 现在通过一个辅助工具 `_register_definition` 来注册每个定义，该工具捕获 `ValueError` 从 `agent_definition_to_factory`，记录 `Skipping <file-based|plugin> agent '<name>' from <source>: <error>`，跳过该定义并继续注册其他定义。 有效技能分辨率不变。
> - `openhands-sdk/openhands/sdk/subagent/AGENTS.md` 表示不变量（注册失败不是致命的，就像解析失败一样）。
> - 单元测试基于文件的路径和插件路径； `F27.subagents-bad-skill` 地图项目符号失去其 `# bug` 标记，现在还检查第二条消息和警告。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`
- `openhands-sdk/openhands/sdk/subagent/AGENTS.md`
- `openhands-sdk/openhands/sdk/subagent/registry.py`
- `tests/sdk/subagent/test_subagent_registry.py`

链接问题接受上下文：

- [#5630](https://github.com/OpenHands/software-agent-sdk/issues/5630): [Bug]: 子智能体缺少的技能导致第一个消息返回500错误，而不是跳过——当前状态已关闭，关闭于2026-10-13T21:39:50Z。

> - [ ] 命名缺失技能的智能体文件不再使消息 `POST` 或使用 `initial_message` 创建返回 500。 - [ ] 错误的智能体被跳过，并带有命名其文件和技能的警告（或者请求是命名它们的 4xx）； 其他有效的智能体仍然被注册。 - [ ] 单元测试涵盖 `register_file_agents`，其中定义了一项缺失的技能。 - [ ] 地图项目符号 `F27.subagents-bad-skill` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### Version main at 2804c12 ### 附加上下文 - `LocalConversation.send_message` 在第一条消息 (`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1822-1823`) 上初始化智能体； `_ensure_agent_ready` (:1569) 达到 `register_file_agents(self.workspace.working_dir)` (:1533)。 - `register_file_agents` (`openhands-sdk/openhands/sdk/subagent/registry.py:288-333`) 为每个项目和用户定义 (:319-320) 构建一个工厂，而不进行错误处理，并且 `agent_definition_to_factory` 为未知技能 (:198-203) 提出 `ValueError`。 - `event_router.py:227` 没有捕获到它，因此路线回答 500。 `_agent_ready` 仅在末尾（`local_conversation.py:1598`）设置，因此后面的每个消息都会再次失败。 - `conversation_service.py` 在发送初始消息 (:1671) 之前存储对话 (:1663)，因此剩下 `idle` 对话。 - 目录（`sub_agents_router.py:117-140`）仅验证前置元数据； 加载器会跳过无效文件并发出警告（`subagent/load.py:213-220`）。 建议的修复：在`register_file_agents`中，catc

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5754#issuecomment-6154887542)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5754#pullrequestreview-5510111238)_这篇评论是由AI发布的智能体 (OpenHands## 范围这个更改应该在这个仓库中进行。 Issue #5630 (linked via ) `Fixes #5630`) 是可访问的 `bug`, `priority:low`, and `ready-for-dev`; 其 AI 诊断将针对文件基础和插件的定义注册进行修复范围智能体在 `openhands-sdk/openhands/sdk/subagent/registry.py`, 这就是这个 PR touches. 的 `F27.subagents-bad-skill` 子弹在地图上生活 `.agents/skills/verify-agent-server/` 在本仓库中，和  `POST /api/sub-agents` ## 评估修复方案正确、最小且针对性强 `_register_definition` (`registry.py:326`) 包含只 `agent_definition_to_factory` 在 `try/except ValueError`, logs `Skipping <file-based\|plugin> agent '<name>' from <source>: <error>`, and returns `False

<a id="5759-fixagent-server-re-probe-a-canvas-app-backend-after-a-missed-health-probe"></a>

### ＃5759：fix(agent-server)：在错过运行状况探测后重新探测 Canvas 应用程序后端

- 提交：`6a298a48fcdb06c3bf5835d648a7d8b4d3d31cf5` (2026-10-14T00:37:50+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5759).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5759)。 家庭：F28。

陈述意图：

> - `status()` 现在也重新探查一个正在运行的进程 `unhealthy` 只有因为探针失败（不是那种退出或未能启动的探针），才设置了 `ready` 当探针成功时。
> - `start()` 在实时进程上具有相同修订版会返回刷新状态而不是缓存状态。
> - 单元测试具有真正的后端子进程（缓慢的探测，仍然很慢，恢复，然后通过 `start` 进行相同的操作）； `F28.status-probe-latch` 地图项目符号失去了已知错误标记。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`
- `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`

链接问题接受上下文：

- [#5646](https://github.com/OpenHands/software-agent-sdk/issues/5646): [Bug]Canvas 应用后端在进行一次慢健康探针后仍然处于“不健康”状态，而不是返回“就绪”状态——当前状态已关闭，关闭时间：2026-10-13T22:37:52Z。

> - [ ] 健康路径再次及时响应的实时后端是下一个 `GET .../backend` 上的 `ready`。 - [ ] 持续失败的探针或其进程退出的后端仍然是 `unhealthy`。 - [ ] 使用真实的子进程进行的测试覆盖了一个缓慢的探针，然后进行恢复。 - [ ] `F28.status-probe-latch` 地图项目符号通过并且其已知错误标记被删除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 2804c12 ### 附加上下文在 `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py` 中： - `status()` 仅在 `runtime.state == "ready"`（第 454 行）时进行探测。 `_probe`（1秒超时，540-545行）失败了，`unhealthy`（465-466行）随后跳过探针。- `start()` 当同一修订的进程存活时，返回当前状态（596-602行）。- `ready_endpoint()` 需要`ready`（779-783行），因此`_ready_endpoint`（`canvas_extensions/bridge.py:345-356`行）回答503。 建议的修复方法：在`status()`中，还应该探查一个标记为`unhealthy`的活跃进程（不是那个已经退出或无法启动的进程），并在探查成功时设置`ready`。 或者，仅在连续几次失败后才标记 `unhealthy`。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5759#issuecomment-6155278112)

<a id="4814-fixsdk-keep-fork-titles-out-of-local-conversation-tags"></a>

### ＃4814：fix(sdk)：将分叉标题保留在本地对话标签之外

- 提交：`6e7a8532ef4426da08b5c06dd57cf4795303be01` (2026-10-14T01:49:09+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/4814).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-4814)。 族：F04、F05、F08、F09、F10、F12、F31、F32、F33。

陈述意图：

> - 保留 `title` 关键字以实现兼容性，但弃用保留在本地并停止添加或覆盖标签。 `LocalConversation` 不存储标题。
> - 保留智能体-server 和 `RemoteConversation` 标题到 `StoredConversation.title`，并在省略标签时保持分叉元数据标签与状态一致。
> - 合并当前 `main` (`c0471362d340ade1e334595ba98417108b415e88`)，保留其并发-fork 生命周期锁，并将未发货的弃用计划更新为 `1.54.0` → `1.60.0`。
> 
> 配套文档： https://github.com/OpenHands/docs/pull/926

更改的路径：

- `examples/01_standalone_sdk/48_conversation_fork.py`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `openhands-sdk/openhands/sdk/conversation/base.py`
- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`
- `openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`
- `tests/cross/test_remote_conversation_live_server.py`
- `tests/sdk/conversation/local/test_fork.py`

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/4814#pullrequestreview-5083197839)：谢谢！
- [reviews COMMENTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/4814#pullrequestreview-5299952118)_这篇评论是由AI发布的智能体 (OpenHands)._ ## 评估核心修复是正确的，我在本地进行了验证 `04c1796`: - `LocalConversation.fork(title=...)` 不再写 `{"title": ...}` into `state.tags`. 直接重现截图 `fork.state.tags == {}` 之后 `src.fork(title="My Fork")`, and a `DeprecatedWarning` 被发出 `local_conversation.py:808` with message "LocalConversation.fork() title 参数是已弃用自 1.44.1 起，并将在 1.50.0 中删除。 ...” — 更改后的测试 `match="title parameter is deprecated"` 断言有效弃用计划满足了仓库的5分钟小版本周期： `deprecated_in="1.44.1"` → 最小值 `removed_in` 是 `1.49.0`, and `1.50.0` 清除它（）`.github/scripts/check_deprecations.py::_runway_error`). 的 `stacklevel=2` 直接调用模式匹配现有情况
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4814#pullrequestreview-5494526348)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评估审核头 `5376633aca2608e10a718858d86e6de3f4ec7cfb`（早期的机器人审核 `04c1796` 已被取代 - 该头添加了元数据一致性修复和 `1.54.0 → 1.60.0` 弃用时间表）。 更改正确且完整： - **已验证错误修复。** `LocalConversation.fork(title=...)`不再写入`state.tags`。 `src.fork(title="My Fork", tags={"title": "user tag", "p": "1"})`直接在此处重置会得到`state.tags == {'title': 'user tag', 'p': '1'}`——用户的`title`标签被保留，而不是覆盖——并从`local_conversation.py:838`发出`DeprecatedWarning`，用`1.54.0 → 1.60.0`的措辞。 参数化的`test_fork_with_title_is_deprecated`（空/普通/用户`title`标签）恰好涵盖了这一点。 - **没有API签名
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4814#issuecomment-5498661304): 👋 **在 OpenHands 可以查看它之前，此 PR 需要修复一些问题：** - PR 描述的 `HUMAN:` 部分需要至少 20 个字符来描述您测试的内容，而不仅仅是模板占位符。一旦解决此问题，此检查将自动重新运行，推送更新。 _这是一个自动检查 - 没有使用人工智能来生成此comment._
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4814#issuecomment-5500277016)：🚦 **CI 目前在 PR 的最新提交上失败。**请在 OpenHands 审核之前修复失败的检查 - 一旦您推送新的提交，就会自动重新检查。 （维护者还可以请求 `@all-hands-bot` 作为审阅者对其进行审阅，无论 CI 状态如何。）_这是一项自动检查 - 没有使用 AI 来生成此 comment._
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/4814#issuecomment-5502384711)：嗨 - 我是 **OpenHands-GPT-5.6，enyst 的 AI 智能体**。 检查因真实且非常具体的原因而失败：Griffe 发现 `LocalConversation.fork(title)` 从已发布的 `openhands-sdk` API 中消失。 删除该关键字意味着调用 `conversation.fork(title="...")` 的现有独立 SDK 代码现在将引发 `TypeError`。 [作业注释](https://github.com/OpenHands/software-agent-sdk/actions/runs/33544984395/job/100030894998)为： > `LocalConversation.fork(title)`：参数已删除 > 不兼容变更检测到 (1)； 至少需要从1.44.x版本增加最小版本号，但新版本是1.44.1。所以**的检测是正确的**，我不应该让检测器忽略这种情况。 错误修复应该停止将标题写入 `state.tags`，但这并不需要立即删除接受的关键字。 对问题影响最小的修复
- [讨论； 评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/4814#issuecomment-5502391090)：直接在 PR #4814 上发布响应： https://github.com/OpenHands/software-agent-sdk/pull/4814#issuecomment-5502384711  我解释说 API 中断检测是有效的，而可选检查/审查机器人交互可以合理地变得更加宽松。 没有进行任何代码更改。

<a id="5478-add-newly-released-llm-models-to-verified-lists"></a>

### ＃5478：将新发布的 LLM 模型添加到验证列表中

- 提交：`c3ecd82c7807a80796d95a6fdb83b7865d04413d` (2026-10-14T06:32:33-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5478).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5478)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - 将`gpt-6.1-sol`添加到`VERIFIED_OPENAI_MODELS`、`VERIFIED_OPENROUTER_MODELS`
>   （`openai/gpt-6.1-sol`）和`VERIFIED_OPENHANDS_MODELS`。
> - 将 `claude-sonnet-5-5` 添加到 `VERIFIED_ANTHROPIC_MODELS`，
>   `VERIFIED_OPENROUTER_MODELS` (`anthropic/claude-sonnet-5.5`)，以及
>   `VERIFIED_OPENHANDS_MODELS`.
> - 将`gemini-4-argon`添加到`VERIFIED_GEMINI_MODELS`和`VERIFIED_OPENROUTER_MODELS`
>   (`google/gemini-4-argon`); 尚未在 `openhands/` 提供商下出现。
> - 仅追加； 没有删除或重命名现有模型 ID。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `84d4470acd85` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -26,0 +27 @@
> +运算GET/api/canvas-extensions/installed/{extension_name}/iconoperationId=get_canvas_extension_icon_endpoint_api_canvas_extensions_installed__extension_name__icon_get
> @@ -95,0 +97 @@
> +运算POST/api/acp/modelsoperationId=discover_models_api_acp_models_post
> @@ -100,0 +103 @@
> +运算POST/api/bash/bash_commands/{command_id}/stopoperationId=stop_bash_command_api_bash_bash_commands__comm

更改的路径：

- `openhands-sdk/openhands/sdk/llm/utils/verified_models.py`
- `tests/sdk/llm/test_model_list.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5478#issuecomment-5967623805)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5478#pullrequestreview-5407472932)：_此评论由 AI 智能体 (OpenHands) 发布。_ 已评论头 `66b9bc76b9d2bc4a4b33ffc3ce0ffba04411396f`（+6/-0，一个文件）。 `uv run pytest tests/sdk/llm/test_model_list.py -q` -> 12 通过。 除了 `Validate PR description` 之外，头部的检查是绿色的，由于不相关的缺失 `## Issue Number` 部分而失败。 **发现 - Sonnet 行现在拥有三个版本，违反了记录的两个最新规则。** `openhands-sdk/openhands/sdk/llm/utils/AGENTS.md`（以及模块文档字符串）要求：对于每个模型行仅保留两个最新版本，并且“当您添加新版本时，请删除同一行中出现的每个列表中最旧的版本。”在此之前 PR，十四行诗行是 `claude-sonnet-5` 和 `claude-sonnet-4-6`（两个条目）。 添加 `claude-sonnet-5-5` 等于 3，因此 `claude-sonnet-4-6` 现在是最古老的
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5478#discussion_r4178749262): The `llm/utils/AGENTS.md` curation rule 要求每行模型线只保留最新版本的两个版本，并且当添加新版本时删除最旧的版本。 十四行诗行有两处记录 (`claude-sonnet-5`, `claude-sonnet-4-6`); 添加 `claude-sonnet-5-5` 译文：做出了三件事。 `claude-sonnet-4-6` 现在是最老的，应该被移除 `VERIFIED_ANTHROPIC_MODELS` 和 `VERIFIED_OPENHANDS_MODELS` (行 148) 这相当于#5311，已删除 `claude-opus-4-8` when adding `claude-opus-5-5`. 只验证了 Opus 元素 Anthropic所以它不会捕获这个。
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5478#issuecomment-6096224305)：使用新检测到的模型更新了此滚动 PR： - **`claude-haiku-5-5`** (Anthropic) — 添加到 `VERIFIED_ANTHROPIC_MODELS`、`VERIFIED_OPENROUTER_MODELS` (`anthropic/claude-haiku-5.5`) 和 `VERIFIED_OPENHANDS_MODELS`。 OpenRouter 已确认可用，LiteLLM 的`model_cost` 注册表包含。 - 已删除**`claude-sonnet-4-6`**，从Anthropic 和OpenHands 列表中移除，每个模型行保留其最新的两个版本（5.5, 5）。 来源：OpenRouter 模型目录 —  https://openrouter.ai/api/v1/models  (`anthropic/claude-haiku-5.5`)。 无 ACP 供应商白名单更改： `_CLAUDE_MODELS` 使用版本无关 CLI 昵称 (`sonnet`, `haiku`, `opus[1m]`)。_此评论由 AI 智能体 (OpenHands) 代表 user._ 创建
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5478#issuecomment-6165418297)：🤖 每周两次的 LLM 模型列表自动化更新 (2026-10-14)。 **添加：** `gemini-4-argon` (Google) — 新的 Gemini 4 系列，于 2026 年 10 月 13 日发布。 - `VERIFIED_GEMINI_MODELS` → `gemini-4-argon` - `VERIFIED_OPENROUTER_MODELS` → `google/gemini-4-argon` 通过 LiteLLM `model_cost` (`gemini/gemini-4-argon`) ** 和 ** 公众 OpenRouter `/api/v1/models` 端点确认可公开调用（`google/gemini-4-argon`，创建于 2026 年 10 月 13 日）。 未添加到 `VERIFIED_OPENHANDS_MODELS` — `openhands/` 代理尚未为其提供服务。 **此外：**将当前的`main`（`6e7a8532`）合并到这个分支中，该分支在`84d4470a`处已经过时了； 合并是干净的。 **跳过**（在LiteLLM但尚未确认为新的公共前沿发布版本，或比最近的两个已整理版本更老）：`gemini-3.5-flash`，`gemini-3.6-flash`（都比t

<a id="4926-docsacp-clarify-client-surfacing-contract"></a>

### ＃4926：docs(acp)：澄清客户表面合同

- 提交：`7f7f0520920007b2c135e7bd0ef06e637032860b` (2026-10-14T13:09:23+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/4926).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-4926)。 族：F04、F09、F18、F19、F20、F21、F22、F23、F30、F33、F34。

陈述意图：

> - 在 Python 和 TypeScript 注册表模块中澄清它们携带元数据，而不是部署策略。
> - 记录单向 `SURFACED_ACP_PROVIDERS ⊆ ACP_PROVIDERS` 不变量并拒绝补充隐藏提供者列表。
> - 在`AGENTS.md`中记录跨存储库合约； 修改 #4841 和 #4833 以匹配最新的更正。

更改的路径：

- `AGENTS.md`
- `clients/typescript/src/models/acp.ts`
- `openhands-sdk/openhands/sdk/settings/acp_providers.py`

链接问题接受上下文：

- [#4841](https://github.com/OpenHands/software-agent-sdk/issues/4841)：每个客户端分别声明提供哪些 ACP 执行框架；在 SDK 中新增框架时，不得自动影响 Cloud 或 Replicated；当前状态为已关闭，关闭时间为 2026-10-14T11:09:25Z。

> - [  ] 云宣布其集合，过滤 `/api/options` 在开始对话时，返回 400 错误码，其他情况则跳转到它 OpenHands/enterprise#315 - [  ] Bumping `openhands-sdk` 注册新挂载器的版本不会产生任何可观察的云更改：没有 `/api/options` diff，没有图像变化，没有新的代码路径 [  ]  `DEFAULT_PREINSTALLED_ACP_PROVIDERS` 被测试冻结，因此默认图像的生长是故意的 PR (#4643, #4820) - [  ] Canvas声明了 `SURFACED_ACP_PROVIDERS` 独立地并仅断言 `SURFACED_ACP_PROVIDERS ⊆ ACP_PROVIDERS`因此，重命名或移除会导致失败，而添加则无影响 [  ]  基准测试和评估都基于它们 ACP 从注册表 (#4833) - [  ] 没有添加部署策略字段 `ACPProviderInfo`  **开放性问题。** 云的文本云 `acp_command` 字段启动任何 ACP 无论允许白名单。 把它关起来，或者接受列表控制选择器，而不是逃生舱口——产品调用。 

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/4926#issuecomment-5600024056)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4926#pullrequestreview-5398725459): _此评论由 AI 智能体 (OpenHands) 发布。_ ## PR #4926 的评论 — `docs(acp): clarify client surfacing contract` **范围：** 该更改属于此存储库。 它编辑了SDK的ACP 注册表文档（`openhands-sdk/openhands/sdk/settings/acp_providers.py`），其TypeScript镜像（`clients/typescript/src/models/acp.ts`），以及仓库内存（`AGENTS.md`）——所有这些都在这里，且它遵循了`ACP_PROVIDERS`已记录的`AGENTS.md`指导。 它仅是文档：没有行为、公开符号、已序列化事件、已持久化设置或REST合约更改。 ### 在主分支上进行的验证：`b3179e5` - **Python聚焦测试：** `uv run --frozen pytest tests/sdk/settings/test_acp_install_catalog.py tests/sdk/settings/test_acp_providers.py -q` → **81通过**。 - **TypeScript聚焦测试：** `npx vitest run src`
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/4926#pullrequestreview-5516945130)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## APPROVE — `docs(acp): clarify client surfacing contract` 已评论头 `77ea167c4e1d95bde1157790e01a6a8335af357f`。 所有检查运行均成功完成，没有失败（预提交，SDK-测试，TypeScript客户端，CI验证-ACP-提供商，API和REST断开检查，已持久化设置，端点审计，Windows/Mac二进制构建，安全）。 这是仅限文档的更改，仅限于三个文件中的文本：`openhands-sdk/openhands/sdk/settings/acp_providers.py` 中的模块文档字符串、`clients/typescript/src/models/acp.ts` 中的标题注释和一个 `AGENTS.md` 条目。 没有行为、公共符号、已序列化事件、已持久化设置或REST合约的变化，因此除了现有的ACP提供者检查之外，没有什么可以回归测试。 所述合同与代码匹配：`ACP_PROVIDER

<a id="5981-featsdk-let-agent-profiles-select-public-skills-read-them-locally-and-use-the-global-critic-key"></a>

### ＃5981：feat(sdk)：让智能体配置文件选择公共技能，在本地读取它们并使用全局评论家密钥

- 提交：`d332f8156f12014df1b3522ab01c2508eabf6e8b` (2026-10-14T13:09:44+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5981).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5981)。 族：F01、F04、F21、F25、F27、F29、F30、F33、F34。

陈述意图：

> - `OpenHandsAgentProfile.public_skills`: `null` 保留所有公共目录技能，就像今天一样； `[]`保留None； 列表仅保留这些名称，未知名称将被忽略。 用户和项目技能不受影响，并且 `disabled_skills` 仍然适用于一切。
> - `LaunchStores.public_skill_names` 告诉解析器哪些目录技能是公共的。 智能体-服务器从与目录相同的加载器中派生它，因此隐藏公共技能的用户技能仍然是用户技能。 对于设置 `public_skills` 的配置文件，它是只读。 实现、预览和遗留 `resolve_agent_profile`/试运行应用相同的选择。
> - `EXTENSIONS_PATH` 使 `load_public_skills()` 读取扩展存储库的本地副本，例如已安装的 `@openhands/extensions` 包，而不是克隆它。 自定义 `repo_url` 不受影响。
> - 保存在服务器全局验证设置中的批评者 API 密钥现在可以到达每个 OpenHands 配置文件启动到 `LaunchStores.critic_api_key`。 之前，批评家又回到了LLM键。 配置文件保持机密免费。 当配置文件时应用密钥

更改的路径：

- `openhands-agent-server/openhands/agent_server/launch.py`
- `openhands-agent-server/openhands/agent_server/server_details_router.py`
- `openhands-agent-server/openhands/agent_server/skills_service.py`
- `openhands-sdk/openhands/sdk/launch/preview.py`
- `openhands-sdk/openhands/sdk/launch/resolve.py`
- `openhands-sdk/openhands/sdk/profiles/agent_profile.py`
- `openhands-sdk/openhands/sdk/profiles/resolver.py`
- `openhands-sdk/openhands/sdk/skills/skill.py`
- `tests/agent_server/test_launch_parity.py`
- `tests/agent_server/test_server_details_router.py`
- `tests/agent_server/test_skills_service.py`
- `tests/sdk/launch/fakes.py`
- `tests/sdk/launch/test_field_ownership.py`
- `tests/sdk/launch/test_preview.py`
- `tests/sdk/launch/test_resolve.py`
- `tests/sdk/profiles/test_resolver.py`
- `tests/sdk/skills/test_load_public_skills.py`

链接问题接受上下文：

- [#5980](https://github.com/OpenHands/software-agent-sdk/issues/5980)：[智能体配置]：允许配置选择公共技能，并从本地扩展副本读取目录；当前状态为已关闭，关闭时间为 2026-10-14T11:09:46Z。

> - [ ] `OpenHandsAgentProfile.public_skills` 仅过滤公共层； `null` 保留现有配置文件的当前行为。 - [ ] 启动、具体化/预览和遗产 `resolve_agent_profile` / 试运行就已解决的技能达成一致。 - [ ] 通过名称隐藏公共技能的用户技能被视为用户技能。 - [ ] `EXTENSIONS_PATH` 使 `load_public_skills()` 读取该目录并且从不克隆； 自定义 `repo_url` 不受影响。 - [ ] 配置文件启动使用全局 `verification.critic_api_key`，包括通过 Docker 主机，而不将其暴露在具体化中。 - [ ] `/server_info` 报道 `profile_public_skills_v1`。 - [ ] 内联 `default` 和 id 启动的等效配置文件为模型提供了相同的技能、工具和系统提示词。 ### 考虑的替代方案 - Canvas 采用服务器的拒绝列表。 这反转了 OpenHands/OpenHands#16302 并将每个新的目录技能放入每个提示词中。 - `agent_launch_additions.skills` 加上一个删除服务器公共目录的标志。 家庭启动将匹配，但相同配置文件的网关和自动化启动仍将获得完整目录。 ### 优先级/严重性中：它阻止Agent Canvas中的智能体配置文件启动统一。 ### 估计范围小：一个配置文件字段、`LaunchStores` 上的层名称挂钩、环境变量和一项功能。 ### 功能区域智能体个人资料、技能 ### 附加上下文遵循 #3979、#4017 和 #4960。 画布面：OpenHands/OpenHands#17991 和 OpenHands/OpenHands#18419。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5981#issuecomment-6165373021)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5981#pullrequestreview-5516939267)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## APPROVE — `feat(sdk): let Agent Profiles select public skills, read them locally and use the global critic key` 评论头 `37110ec7b25f19b30125ff666a5edbf80e72e66b`。 所有检查运行均成功完成，没有失败 (SDK-测试，智能体-服务器测试，工具测试，跨端测试，集成测试，预提交，OpenAPI/REST 问题，端点-审计，验证-ACP-提供商，Windows/Mac 二进制构建，安全性)。 我验证了差异中的内容：**`public_skills`的语义。** `_select_skills`将`null`视为整个目录，将`[]`视为None，并将列表视为仅对公众层应用的允许列表。 目录中不存在的名称是无操作的，因此 #4017 no-dangle 属性被保留。 `disabled_skills`仍然适用于每一层。 - **分层是合理的。** ``discover_public_skill_names

<a id="5747-fixsubagent-sub-agents-inherit-exactly-the-parents-mcp-servers"></a>

### #5747: fix(subagent): 子智能体完全继承父级的 MCP 服务器

- 提交：`0bd5cc2d322d61f785816a29ef1f2e4c86db2460` (2026-10-14T08:16:28-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5747).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5747)。 家庭：F05、F08、F09、F10、F21、F27、F33。

陈述意图：

> - **`inherit_mcp_config(parent, sub_agent)`** (`openhands.sdk.subagent.scope`) 返回构建的子智能体 with exactly `parent.agent.mcp_config`. 这是代理对话的 *resolved* 配置：插件服务器已合并 `${VAR}`  机密已经展开，工具过滤和头部保持完整。 声明的子服务器从未合并过，且是一个 INFO 它们命名它们（只命名，不配置）。 `TaskManager` (该端点已弃用。) `task`, `workflow_tool_set` 和 `workflow`, 包括简历)和 `DelegateExecutor` 应用到 **构建子节点**因此，文件、插件、程序化和内置定义都理解它。 规则是嵌套的，所以孙子们会得到同样的一套。
> - **子对话按原样使用继承的配置。**新的私有 `LocalConversation(_mcp_config_from_parent=True)` 跳过第二个插件合并和第二个 `${VAR}` 扩展。 孩子也重复使用父母的`mcp_tool_provider`。
> - **`SubAgentScope` 现在仅限制工具。** `mcp_servers` 标志保持为已弃用、忽略、排除字段，因此存储的工具参数仍然加载。 `missing_from`、列表和 Eli

更改的路径：

- `openhands-agent-server/openhands/agent_server/sub_agents_router.py`
- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`
- `openhands-sdk/openhands/sdk/profiles/resolver.py`
- `openhands-sdk/openhands/sdk/subagent/AGENTS.md`
- `openhands-sdk/openhands/sdk/subagent/schema.py`
- `openhands-sdk/openhands/sdk/subagent/scope.py`
- `openhands-tools/openhands/tools/delegate/impl.py`
- `openhands-tools/openhands/tools/task/definition.py`
- `openhands-tools/openhands/tools/task/manager.py`
- `tests/sdk/profiles/test_resolver.py`
- `tests/sdk/subagent/test_subagent_scope.py`
- `tests/tools/task/mcp_echo_server.py`
- `tests/tools/task/test_mcp_inheritance.py`
- `tests/tools/task/test_sub_agent_scope.py`

链接问题接受上下文：

- [#5743](https://github.com/OpenHands/software-agent-sdk/issues/5743): [智能体 Profile] 子智能体必须完全继承父级 MCP 工具 — 当前状态已关闭，已关闭 2026-10-14T12:16:30Z。

> - [  ] 由一个家长指定的儿童 MCP 配置文件包含一个可以由子进程调用的服务器，该服务器提供工具。 该孩子的请求包括了家长的 MCP tools (e.g. 的 `qa_echo` 现在，工具显示在子窗口中 [  ] 声明额外的子定义 MCP 父配置文件中服务器从未出现在有效配置中：没有连接建立，也没有出现该工具 [  ] 声明同名服务器但配置不同的（命令/参数/头/传输/工具过滤）的子定义永远不会覆盖父定义。 子使用父的配置 [  ] 声明了 0 或更少的孩子 MCP 服务器仍然接收每  MCP 允许的父工具 [  ] 当父元素的生效状态 MCP scope 为空，子元素没有被给予 MCP 服务器或工具 [  ] 一个从孩子继承的孙子继承了相同的有效值 MCP 将其设为父级 [  ] 该行为适用于 `task`, `workflow_tool_set`, and `workflow`, 用于文件驱动、插件、程序化和内置的智能体定义； 资格/上市`missing_from` / `_offered`它既不拒绝继承父配置的子代，也不扩展父配置 [  ]  MCP 凭证/头信息在日志中未以明文出现，却到达了子节点已持久化会话/设置附件 [  ] 策略适用于儿童重新启动和本地 Docker, 云启动； ACP外部委托是明确检查的，而不是假设受可见工具列表的约束 [  ]  验证使用真实的委托路径并执行相应的操作 MCP 服务器和 PR

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5747#issuecomment-6149957004)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5747#pullrequestreview-5516944296)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## APPROVE — `fix(subagent): sub-agents inherit exactly the parent's MCP servers` 评论头 `facd58d71b68b338992de8e72cb76b55e63ce5fe`。 所有检查运行均成功完成，没有失败 (SDK-测试，智能体-服务器测试，工具测试，跨端测试，集成测试，预提交，OpenAPI/REST 问题，已持久化设置，窗口/macos 二进制构建，安全性)。 这里需要 `.pr/` QA 目录，并且存储库的工件工作流程拥有批准后的删除权。 我针对差异验证的内容： - **继承在两个方向上都是准确的。** `inherit_mcp_config(parent, sub_agent)` 返回构建的子级，其内容与 `dict(parent.mcp_config)` 完全相同 - 委托对话的已解析配置（插件服务器合并，`${VAR}` 扩展，工具过滤器/标头完好无损）。 声明的服务器是

<a id="5926-fixagent-server-read-an-unreachable-openai-refresh-as-disconnected"></a>

### ＃5926：fix(agent-server)：将无法访问的OpenAI刷新读取为已断开连接

- 提交：`4bb57df68465868c2ec13388acd6a6b1e14af651` (2026-10-14T15:48:46+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5926).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5926)。 家庭：F23、F24。

陈述意图：

> - `get_openai_subscription_status` 现在在 `refresh_if_needed()` 周围捕获 `httpx.HTTPError` 和 `RuntimeError`，因此无法访问的 OpenAI 读取为 `200 connected: false`，就像拒绝的刷新一样。 凭据文件未受影响，因此一旦网络恢复，状态就会刷新它。
> - `tests/agent_server/test_llm_router.py` 中的单元测试用于引发 `httpx.ConnectError` 的刷新。
> - 地图：`F24.status-offline` 项目符号丢失了其 `# bug` 标记和“已知错误”标签，其散文现在描述了预期的行为，并且它读回存储的文件以证明离线调用使其保持不变。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F24-openai-subscription.md`
- `openhands-agent-server/openhands/agent_server/llm_router.py`
- `tests/agent_server/test_llm_router.py`

链接问题接受上下文：

- [#5925](https://github.com/OpenHands/software-agent-sdk/issues/5925): [Bug]: OpenAI订阅状态在无法离线刷新过期登录时返回未处理的500错误 — 当前状态已关闭，关闭于2026-10-14T13:48:48Z。

> - [  ] 登录已过期 `auth.openai.com` 不可达的 `GET /api/llm/subscription/openai/status` 答案 `200`  `connected: false` 不记录任何未处理异常的堆栈跟踪 [  ] 拒绝的刷新仍然回答 `200`  `connected: false`，并且一个未过期的登录仍然显示为连接状态 [  ] 存储的凭据文件留存在那里，因此，稍后调用状态时，网络返回时可以刷新它 [  ] A 单元测试在 `tests/agent_server/test_llm_router.py` 覆盖了一个刷新操作，该操作引发了一个 httpx 传输层错误 [  ] 地图弹珠 `F24.status-offline` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文原因：- `get_openai_subscription_status` (`openhands-agent-server/openhands/agent_server/llm_router.py:181-188`) 只捕获 `RuntimeError` around `auth.refresh_if_needed()`. - `_refresh_access_token` (`openhands-sdk/openhands/sdk/llm/auth/openai.py:376-390`) raises `RuntimeError` 仅对非2xx响应。 一个 `httpx.ConnectError` / `httpx.TimeoutException` 从 `client.post` 不变地传递下去 `refresh_if_needed` (第507行) 路径上，再转向通用500处理器。 相关：  https://github.com/OpenHands/software-agent-sdk/issues/5880  覆盖相同的内容传输层错误类错误 `device/start` 和 `device/poll` （预期会有网关错误，因为这些调用无法成功） OpenAI); 状态有所不同，因为“现在未连接”是有效答案。 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5926#issuecomment-6159182702)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5926#pullrequestreview-5512555396)_这篇评论是由AI发布的智能体 (OpenHands## 作用域在仓库内。 更改在  `openhands-agent-server`'s `/llm` router (`openhands-agent-server/openhands/agent_server/llm_router.py`该仓库拥有的一些资源，以及其自身的测试和文档 `verify-agent-server` 特征图它发货了。 无需跨仓库移动和无需产品/架构决策。## 接收证据（在运行的、真实的服务器上）我重新运行了地图的子弹 PR 它还与该仓库的自身测试 harness 对抗了两次修订：- `control-agent-server map run --file F24 --only F24.status-offline --fresh --checkout <main @ 6e7a853>`: **失败** 在状态上 GET - `500 {"detail":"Internal Server Error","exception":"All connection attempts failed"}`匹配关联问题报告的症状。 - 在这个分支上，同样的命令（）`631afe2`): **通过** - 200 {"vendor":}OpenAI, connect

<a id="5923-fixagent-server-forward-path-on-the-bare-canvas-app-backend-root-route"></a>

### #5923: fix(agent-server): 在裸 Canvas 应用程序后端根路由上转发 ?path=

- 提交：`1a0fd91ad03d6a9f51ea38aa53fb60b848b56d20` (2026-10-14T16:02:14+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5923).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5923)。 家庭：F29。

陈述意图：

> - `canvas_extensions_bridge_router.py`：根 HTTP 和 WebSocket 路由有自己的处理程序，不带 `path` 参数并始终代理到 `/`； 子路径处理程序现在需要 `path`（始终从 URL 绑定）。 `bridge.py` 未受影响。
> - 新的重点测试 `tests/agent_server/canvas_extensions/test_canvas_extension_bridge_routes.py` 检查每个路由形式通过哪个上游路径到达网桥，对于 HTTP (GET/POST) 和 WebSocket。
> - 地图：`F29.proxy-root-path-query` 失去了三个 `# bug` 标记和“已知错误”标签； 散文现在描述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `openhands-agent-server/openhands/agent_server/canvas_extensions_bridge_router.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_bridge_routes.py`

链接问题接受上下文：

- [#5919](https://github.com/OpenHands/software-agent-sdk/issues/5919)：[缺陷]：Canvas 应用后端代理的根路由从 ?path= 查询参数中获取上游路径；当前状态为已关闭，关闭时间为 2026-10-14T14:02:16Z。

> - [ ] 在 `/app-backends/{name}`（无尾部斜杠）上，HTTP 所有方法的请求都到达后端的 `/`，并且 `path` 查询参数在查询中原样转发。 - [ ] `/app-backends/{name}?path=...` 上的根 WebSocket 的目标是后端的 `/`，而不是查询值。 - [ ] 子路径路由 (`/app-backends/{name}/{path}`) 和尾部斜杠根保持不变，包括遍历检查。 - [ ] 聚焦的单元测试涵盖了 HTTP 和 WebSocket 的路由绑定。 - [ ] 地图项目符号 `F29.proxy-root-path-query` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 其他上下文根本原因，在 `openhands-agent-server/openhands/agent_server/canvas_extensions_bridge_router.py` 中：一个处理程序同时服务于 `/app-backends/{extension_name}` 和 `/app-backends/{extension_name}/{path:path}`（第 80-95 行，HTTP； 第 98-104 行，WebSocket）并声明`path: str = ""`。 在根路由上没有`{path}`段，因此FastAPI将`path`视为查询参数并将`?path=`绑定到它； 然后该值成为 `proxy_app_backend_http` / `proxy_app_backend_websocket` (`canvas_extensions/bridge.py:448`, `:475`) 中的上游路径，其中遍历检查 (`bridge.py:340-342`) 拒绝 `..`。 影响仅限于删除尾部斜杠的链接，并且绑定值仍然通过遍历检查。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5923#issuecomment-6159205881)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5923#pullrequestreview-5512470680): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围此更改放置正确。 `/app-backends/{name}`裸 Canvas 应用后端根路由（Agent Server REST/WebSocket 行为）属于本仓库（`openhands-agent-server/openhands/agent_server/canvas_extensions_bridge_router.py`），并链接的 issue #5919 是 `bug`/`ready-for-dev`/`priority:low`. 无需跨仓库移动。## 我验证了 - 差异将共享处理器拆分为独立的根处理器，这些处理器声明无 `path` 参数，并始终将 `""` 传递给桥接，而子路径 HTTP/WebSocket 处理器现在需要 `path: str`。 在具有 `{path:path}` 段的路由上，`path` 始终与 URL 绑定，因此将其设置为必需不会导致缺少参数错误； 在裸根上，FastAPI没有`path`参数

<a id="5920-fixagent-server-stop-bridging-to-a-crashed-canvas-backend"></a>

### ＃5920：fix(agent-server)：停止桥接到崩溃的 Canvas 后端

- 提交：`1c34a84ccea3aa3f7bdc44ba7a19a88f872fcf08` (2026-10-14T17:45:37+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5920).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5920)。 家庭：F28、F29。

陈述意图：

> - 一旦后端进程退出，`CanvasExtensionBackendManager.ready_endpoint` 返回 `None`，因此 HTTP 代理、WebSocket 桥和引导程序在没有状态轮询的情况下回答 503 未就绪。
> - `proxy_app_backend_http` 将连接失败重命名为 `502 Canvas App backend unreachable`。
> - F29地图：`F29.backend-crash-detected`掉落其`# bug`标记； 它的散文和陷阱线现在描述了固定的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`
- `openhands-agent-server/openhands/agent_server/canvas_extensions/bridge.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_bridge.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5912](https://github.com/OpenHands/software-agent-sdk/issues/5912): [Bug]: Canvas桥接器仍然标记为'就绪'，并回答502 '会话容器不可达'，直到状态检查 — 当前状态关闭，关闭于2026-10-14T15:45:40Z。

> - [ ] 当准备好的后端进程退出后，桥接的 HTTP 代理、 WebSocket 桥接和会话启动器会 `503 Canvas App backend is not ready` 无先前提醒的状态检查。- [ ] 一个存活但拒绝连接的后端会返回一个 502 错误，其详情指明的是 Canvas 应用后端，而不是会话容器； Docker运行时代理自己的消息没有改变。 - [ ] F28 状态路由仍将崩溃报告为 `unhealthy` (`Backend exited with code ...`)，并且重新启动仍然有效。 - [ ] 单元测试涵盖 `CanvasExtensionBackendManager.ready_endpoint` 中的退出进程情况和桥接错误措辞。 - [ ] 地图项目符号 `F29.backend-crash-detected` 通过，其 `# bug` 标记被删除。 ### 检查 main 时的安装方法 uv 同步 ### 版本 main 位于 6e7a853 ### 附加上下文根本原因： - 只要设置了 `runtime.state == "ready"` 和端口，`CanvasExtensionBackendManager.ready_endpoint` (`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py:814-819`) 就会返回端点。 它从不检查 `runtime.process.returncode`，`runtime.state` 只在 `_refresh_unlocked`（第 457 行）变化，从 F28 `status` `start` 和 `stop` 路由到达。- 因此，桥 (`canvas_extensions/bridge.py:345-361` `_ready_endpoint`) 将死掉的端口交给 `proxy_http` (`docker_runtime/proxy.py:142-152`)，其连接错误分支回答 `502 Conversation container unreachable`。 相关： https://github.com/OpenHands/software-agent-sdk/issues/5637 （后端超出了SIGKILLed服务器的生命周期）是一个不同的生命周期问题。 F

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5920#issuecomment-6159120042)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5920#pullrequestreview-5512615371): 这条评论是由一个AI发布的智能体 (OpenHands)。Agent Server Python行为（Canvas App后端生命周期和`/app-backends`桥接），这是这个仓库拥有的行为。 没有必要进行跨回购移动。 链接的问题 #5912 已在 `bug`、`priority:low`、`ready-for-dev` 中开放，其接受标准由当前负责人解决。 结果：不存在重大正确性、安全性、兼容性或验收标准缺陷。 我在 `0ee038dd61abcfc94798c92ad1c5224d8b155ed2` 上验证的内容： - 核心修复。 `CanvasExtensionBackendManager.ready_endpoint` (`canvas_extensions/backend.py:814-824`) 现在返回 `None`，当 `runtime.process is None` 或 `runtime.process.returncode is not None` 时，因此所有三个桥接消费者 —— 代理 HTTP、桥 WebSocket 和会话启动器，它们都通过 `_ready_endpoint` (

<a id="5944-fixagent-server-report-a-failed-skills-sync-fetch-as-an-error"></a>

### ＃5944：fix(agent-server)：报告失败的技能同步获取错误

- 提交：`2ec5b9ed4a675e01f0d33192be57a4f9834cfd2b` (2026-10-14T17:49:41+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5944).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5944)。 家庭：F15、F25。

陈述意图：

> - 添加选项开关 `strict` flag to `try_cached_clone_or_update` (threaded through `_update_repository`) 和 `update_skills_repository`当设置为失败的 fetch，或在请求的 ref 之后失败的 checkout 时，返回 `None` 而不是陈旧的路径。 默认（`strict=False`）对其他所有调用者都保留回退到缓存的行为。
> - `sync_public_skills` 使用 `strict=True`，因此路由器报告 `status: error`。 本地已存在的固定标签/SHA 仍会跳过提取并报告成功。
> - 地图项目符号 `F25.sync-offline`：`# bug` 标记被删除，散文被重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`
- `openhands-agent-server/openhands/agent_server/skills_service.py`
- `openhands-sdk/openhands/sdk/git/cached_repo.py`
- `openhands-sdk/openhands/sdk/skills/utils.py`
- `tests/agent_server/test_skills_service.py`
- `tests/sdk/git/test_cached_repo.py`

链接问题接受上下文：

- [#5933](https://github.com/OpenHands/software-agent-sdk/issues/5933): [Bug]: POST  /api/skills/sync 当公共技能仓库无法获取时，报告成功——当前状态关闭，关闭于2026-10-14T15:49:43Z。

> - [  ]  `POST /api/skills/sync` reports `status: error` 当现有公共技能仓库的克隆无法获取（或在获取后请求的分支无法检出） [  ] 滞后的克隆体被保留，并继续用于技能加载`load_public_skills`, 市场和插件目录), 保持其当前的回退到缓存行为 [  ] 成功获取，本地已存在一个 pinned ref，仍然报告 `status: success`. - [  ] A 单元测试覆盖了同步对抗一个不可达的克隆版本 [  ] 地图弹珠 `F25.sync-offline` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文原因：- `sync_public_skills` (`openhands-agent-server/openhands/agent_server/skills_service.py:473-479`) calls `update_skills_repository` 并且会将任何返回的路径视为成功 `update_skills_repository` (`openhands-sdk/openhands/sdk/skills/utils.py:590-609`) 调用 `try_cached_clone_or_update(..., update=True)`, whose `_update_repository` (`openhands-sdk/openhands/sdk/git/cached_repo.py:371`) 返回无声地 `_try_fetch` (`cached_repo.py:391-398`) logs `Failed to fetch updates: ... Using cached version.` 然后返回更新后的仓库路径`openhands-agent-server/openhands/agent_server/skills_router.py:322-326`) maps `success=False` to `status: error`因此，只有服务结果需要改变。 fallback-to-cache行为对于其他调用者来说是正确的update_skills_repositor

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5944#issuecomment-6159480441)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5944#pullrequestreview-5512699239)：_此审查由 AI智能体（OpenHands）发布。_ ## 审查 PR #5944 — 将技能同步获取失败报告为错误。**范围与归属：** 属于范围内。 这会更改此存储库拥有的 Agent Server 技能同步端点和 SDK git 缓存助手。 链接的问题 #5933 已开放并包含 `bug`、`priority:low` 和 `ready-for-dev`； 其接受准则和明确的非目标（保持其他调用者的缓存回退行为，不改变HTTP/schema/参数，保持脏克隆）与实现相匹配，因此尽管PR的“决策需要”注释，没有需要的产品决策。 **正确性** - `strict`通过`try_cached_clone_or_update` -> `_do_clone_or_update` -> `_update_repository`和`False`默认值进行线程化，因此每个现有的调用者（`load_public_skills`，市场目录

<a id="5725-fixagent-server-re-vendor-pips-urllib3-and-msgpack-to-patched-versions"></a>

### ＃5725：fix(agent-server)：重新供应商 pip 的 urllib3 和 msgpack 到修补版本

- 提交：`9c0b99ec00775d454d19b9567cf1e1bd61e85a75` (2026-10-14T11:07:37-05:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5725).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5725)。 家庭：F01、F12、F16、F31。

陈述意图：

> - 添加 `pip-revendored` 构建阶段。 它获取 pip 26.2.1 的标记源（使用 `ADD --checksum` 检查），将 `vendor.txt` 切换到 urllib3 2.8.0 和 msgpack 1.2.1，并运行 pip 自己的 `vendoring sync`。 这将应用 pip 的导入重写及其 `tools/vendoring/patches`（包括三个 urllib3 补丁）并重新生成 `bom.cdx.json`。 然后阶段会构建一个 pip 轮。 使用 GitHub 源存档是因为 PyPI sdist 省略了 `tools/vendoring/patches`。
> - 从 `python-node-runtime` 中的轮子重新安装 pip。 安装步骤会根据基础镜像的当前 pip 版本查找轮子，因此如果基础镜像曾经发布过不同的 pip，则构建会失败。 这迫使人们重新评估，而不是默默降级。
> - 添加一名退休警卫，`tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py` (`docker_live`)。 它从 Dockerfile 中读取 `python-runtime` 镜像并检查其中未修改的上游 pip。 它通过了，而上游 pip 仍然提供未修补的 urllib3 或 msgpack。 一旦两者都达到固定版本，或者如果 pip 的

更改的路径：

- `.github/workflows/pip-revendoring-retirement.yml`
- `openhands-agent-server/openhands/agent_server/docker/Dockerfile`
- `tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py`

链接问题接受上下文：

- [#5988](https://github.com/OpenHands/software-agent-sdk/issues/5988): [Bug]: 智能体-服务器图片包含已知漏洞的 vendored urllib3 2.7.0 和 msgpack 1.1.2 — 现状已关闭，关闭于 2026-10-14T16:07:40Z。

> - [ ] 在`python-node-runtime`阶段，`pip._vendor.urllib3.__version__`至少是`2.8.0`，`pip._vendor.msgpack.version`至少是`(1, 2, 1)`，pip的`_vendor/bom.cdx.json`列出了相同的版本。 - [ ] 该修复使用 pip 自己的供应商工具（`vendoring sync` 和 pip 的 `tools/vendoring/patches`），而不是直接复制到 `_vendor` 的文件，因此 pip 的导入重写和补丁保持不变。 所有其他捆绑包与上游 pip 保持不变。 - [ ] pip 仍然可以在构建的映像中工作：PyPI 中的 `pip install` 成功，从 pip 的 msgpack 支持的 HTTP 缓存重新安装成功，并且 `pip check` 是干净的。 - [ ] 与 `main` 相比，对重建图像进行 Trivy 扫描，准确显示 CVE-2026-97687/97688/97689 和 GHSA-6v7p-g79w-8964 已被删除，并且没有新的发现。 - [ ] 如果基础镜像提供了不同的 pip 版本，则构建会失败，因此没有人会默默地安装旧的 pip。 - [ ] `docker_live` 测试检查 `python-runtime` 图像中未修改的上游 pip。 在上游 pip 搭配固定版本进行打包时会失败，并且该端点在 CI 上单独运行。### 安装方法 Docker (发布智能体-server 镜像) ### SDK 版本 `main` (智能体-server Dockerfile at e3a26821f) --- 提出的解决方案：#5725 _此问题由 AI 智能体 (OpenHands) 代表 @aivong-openhands._ 创建_---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5725#issuecomment-6129956174)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5725#pullrequestreview-5504275927)：我们可以为这个临时解决方法添加一个退休测试吗？ 它应该检查 `python-runtime` 图像 ** 中的 ** 未修改的上游 pip，而不是 PR 已修补 pip 的最终图像。 这是一个草案集成测试。 它从 Dockerfile 读取实际的上游镜像引用，因此未来的 Python 镜像更新会自动重新评估解决方法。 它通过了，但任一供应商的依赖项仍需要修补； 一旦两者都达到固定版本，它就会失败并显示删除指令。 缺少供应商的软件包需要重新评估，而不是默默地通过。 建议位置：`tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py`。 ```Python导入JSON从pathlib导入路径导入重新导入子进程从packaging.version导入版本导入pytest@pytest.mark.docker_livedef test_upstream_pip_
- [评论； COMMENTED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5725#pullrequestreview-5508667549): _该评论由一个AI发布智能体 (OpenHands)._ ## 范围仅更改Dockerfile的`openhands-agent-server/openhands/agent_server/docker/` — 对智能体-服务器镜像的pip重新包装 workaround。 这属于此存储库（智能体-服务器打包工件属于此处），因此技术审查继续进行。 ## 我在当前头 (`c92a8a47`) 上验证的内容 - 差异仅限于一个文件和一个问题：一个新的 `pip-revendored` 阶段加上 `python-node-runtime` 中的重新安装步骤。 没有 SDK、API 或已持久化状态的表面被触及。- `ADD` 校验和锁定的 `sed` + `grep -qx` 断言在 `vendor.txt` 上（如果锁定的字符串改变则会失败构建），pip 自己的 `vendoring sync`，以及 `pip-${pip_version}` 轮子查找在 PR 描述中是内部一致且正确地推理的
- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5725#pullrequestreview-5521335271)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围 Dockerfile + CI + `openhands-agent-server/openhands/agent_server/docker/` 下的测试更改。 智能体-服务器打包工件及其 Docker 图像归此存储库所有，因此此更改属于此处。 没有触及 SDK、REST 或已持久化状态表面，并且没有突出的产品/架构决策（问题 #5988 包含 `ready-for-dev`、`bug`、`priority:low`）。 ## 我在当前头 (`46d146ba`) 上验证的内容我获取了确切的头并在工作区中检查了 `46d146ba1bfda1c57aad1fbe0bbf8395bef8e0d3`。 - **sed/grep 重写与真实的 pip 源匹配。**我从 pip `26.2.1` 标签中拉出 `src/pip/_vendor/vendor.txt`：第 0 列（第 4 行）处的 `msgpack==1.1.2` 和缩进的 ` urllib3==2.7.0`（第 11 行）。 Dockerfile 的两个 `sed -E` 表达式完全重现
- [讨论评论； aivong-OpenHands](https://github.com/OpenHands/software-agent-sdk/pull/5725#issuecomment-6170510678)@neubig 我在 b6c4e8a3f 中添加了退休测试 `tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py` 你的草稿已经进行了小的修正，位于模块级别 `pytestmark = pytest.mark.docker_live`找到一个固定版本的 Dockerfile `parents[3]` 路径而不是向上搜索，探针和阈值保持为常量。 行为是一样的。 它读取了  `python-runtime` 从 Dockerfile 中提取的图像，使用了 `--pull=always --network=none`如果 vendoring 布局发生变化，会失败，并且一旦 urllib3 和 msgpack 都达到固定版本，会提示移除指令。- 新的 `.github/workflows/pip-revendoring-retirement.yml` 将它从图像构建中分离出来，正如您所建议的那样，因此精确的pip版本轮子查找不能失败并隐藏消息。 它运行在 PR 该测试会触及Dockerfile

<a id="5986-fixgit-keep-azure-devops-clone-urls-without-a-git-suffix"></a>

### #5986: fix(git) 保留 Azure DevOps 副本 URLs 不带 .git 后缀

- 提交：`95cb37b7f04ff281e92bfb3c3fc66573db2df38a` (2026-10-14T13:43:04-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5986).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5986)。 家庭：F14、F15。

陈述意图：

> - `normalize_git_url` 不保留 DevOps 副本 URLs (任何包含 `/_git/`: dev.azure.com, `*.visualstudio.com`, Azure DevOps 服务器) 的 `.git` 后缀。 它仍然会删除尾部斜杠。 其他主机不变。

更改的路径：

- `openhands-sdk/openhands/sdk/git/utils.py`
- `tests/sdk/extensions/test_fetch.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6169077335)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5986#pullrequestreview-5521290152)_这篇评论是由AI发布的智能体 (OpenHands)._ 已经审核过 `f79cf5050ee916d6aaeb4440a0ad67c34440586c`; 的 PR 头匹配了请求的提交。### 范围改动属于本仓库。 扩展、市场和插件获取，以及 Git URL 归于  SDK, 修复仅限于 `normalize_git_url` 与回归 tests. 无产品或架构决策是必要的，且没有仓库移动适用 `"/_git/" in urlparse(url).path` 关闭 Azure 锁定 DevOps"clone-route marker rather than a host allowlist, so it also covers" `*.visualstudio.com` and Azure DevOps 服务器。 使用 `urlparse(...).path` (不是原始字符串)表示一个 `_git` 在查询或片段中无法触发它。 斜杠后的去重仍然在早期返回之前运行 URLs 已经结束 `.git` 跳过
- [评论； COMMENTED; hieptl](https://github.com/OpenHands/software-agent-sdk/pull/5986#pullrequestreview-5521678995)：Hello Alona，**总体：非阻塞。**我这边没有阻挡者。 谢谢，这是一个小而有针对性的修复。 检查解析路径中的 `/_git/` 涵盖 dev.azure.com、`*.visualstudio.com` 和 Azure DevOps 服务器，无需主机白名单。 碰巧包含 `_git` 段的非 Azure URL 只会丢失 `.git` 后缀，大多数 git 主机无论如何都接受该后缀。 `normalize_git_url` 在当前的 `main` 上也没有变化，因此尽管以 v1.50.1 为基础，但修复应该完全适用。 我在文档字符串上留下了一个非阻塞的问题。 非常感谢：祈祷：
- [评论； APPROVED; hieptl](https://github.com/OpenHands/software-agent-sdk/pull/5986#pullrequestreview-5521699773)：谢谢！ 🙏
- [review_comments; 评论； hieptl](https://github.com/OpenHands/software-agent-sdk/pull/5986#discussion_r4273863970)你好阿诺娜，输出中文简体译文 **非阻塞（nit）：** 感谢添加示例。 摘要行（确保 .git 后缀） HTTPS  URLs") and the `Returns:` 带有.git后缀的行 HTTPS/HTTP  URLs") 仍然描述之前的规则。 你介意提到 Azure 吗 DevOps  `/_git/` 此外，也出现了异常，读者不需要查阅示例就能找到它。 非常感谢：祈祷：
- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6169094498): @OpenHands /codereview-roasted 准确审查提交 f79cf5050ee916d6aaeb4440a0ad67c34440586c。 如果 PR 头发生变化，请报告该情况并且不批准另一次提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性、回归覆盖范围以及PR验证主张是否与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 用VERDICT代替CHANGES_REQUESTED，当需要更改时，选择REVIEWED_HEAD：f79cf5050ee916d6aaeb4440a0ad67c34440586c，REVIEW_REQUEST：237df9de2fa64e459510b4ca217c682c，VERDICT：APPROVED。 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6169922113): ## 审核 — `fix(git): keep Azure DevOps clone URLs without a .git suffix` 准确审核了分支 `alona/azure-devops-marketplace-git-suffix` 上的提交 `f79cf5050ee916d6aaeb4440a0ad67c34440586c`。 PR 头部与请求的审查提交版本相同。 Diff 与父文件 (`1e1390a`) 正好是两个文件：`openhands-sdk/openhands/sdk/git/utils.py` (+6) 和 `tests/sdk/extensions/test_fetch.py` (+24)。 _(Review generated by an AI agent via `/codereview-roasted` on behalf of the requesting user.) ### 正确性 `normalize_git_url` 现在返回 HTTPS/HTTP URLs，其中 `/_git/`（克隆-URL 标记，用于 `dev.azure.com`、`*.visualstudio.com` 和 Azure DevOps 服务器）包含在解析路径中，但不附加 `.git`，同时仍去除尾部斜杠。 我追踪了数据流的全过程：`normalize_git_url` → `parse_extension_source` → `fetch_with_resol`
- [讨论评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6170990043): @OpenHands  /codereview-roasted 审查提交 f79cf5050ee916d6aaeb4440a0ad67c34440586c。 如果 PR 头部更改，报告并拒绝另一提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性回归覆盖率，以及是否   PR  验证声明与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 以这些简洁的行结束实质性审查（不要使用代码框），选择一个裁决：   REVIEWED_HEADf79cf5050ee916d6aaeb4440a0ad67c34440586c REVIEW_REQUEST0002b53946cc45c18e6b3823f333ab26 VERDICT: APPROVED 使用 VERDICT: CHANGES_REQUESTED 而是当发现需要更改时。 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6172505956)很好。 已审核 `f79cf5050ee916d6aaeb4440a0ad67c34440586c`; 的 PR 头部仍然匹配请求的提交。 差异数量有限于 `normalize_git_url` and focused extension-source 回归 tests. 无材料发现。 正确性 The `urlparse(url).path` 检查 Azure 资源 DevOps' `/_git/` 无需依赖云主机白名单，因此也覆盖了 `*.visualstudio.com` and Azure DevOps 服务器。 返回之前仍会删除尾部斜杠。 我追踪了受影响的路径 `parse_extension_source` 在扩展获取中，发现没有后续的规范化步骤可以追加 `.git` again. 现有的非`/_git/`  HTTP(S) 行为未改变验证此评论者的结算页面已独立复制：- `tests/sdk/extensions/test_fetch.py`: **52通过**. - 仅新 `/_git/` early return
- [讨论； 评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6172588635)：审查了确切的提交`f79cf5050ee916d6aaeb4440a0ad67c34440586c`并发布了实质性审查： https://github.com/OpenHands/software-agent-sdk/pull/5986#issuecomment-6172505956 判决：**APPROVED**。 没有实质性发现。 GitHub 拒绝了正式批准事件，因为可用的 token 属于 PR 作者 (`Review Can not approve your own pull request`)，因此判决被发布为 PR 讨论评论，并具有所需的标题和请求 token。

<a id="5929-fixagent-server-tie-uvicorn-proxy_headers-to-trust_forwarded_headers"></a>

### ＃5929：fix(agent-server)：将 uvicorn proxy_headers 绑定到 trust_forwarded_headers

- 提交：`4dc42d3a2b65c4f674ad0fc149477a583a9c4419` (2026-10-14T20:28:07+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5929).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5929)。 家庭：F02、F27。

陈述意图：

> - `__main__.py`：通过一个小的 `_load_server_config()` 帮助程序（与 `_auth_enabled` 共享）解析智能体-服务器配置一次，并将 `proxy_headers=_trust_forwarded_headers()` 传递给 uvicorn 的 `Config`。 桥接代理代码没有更改。
> - 测试：`test_preload_modules.py` 检查每个标志设置的 `proxy_headers` 值 `main()` 是否通过； `canvas_extensions/test_canvas_extension_bridge.py` 使用启动器的 `proxy_headers` 值在实时 uvicorn 服务器上运行网桥，并针对普通 HTTP 入口（引导和代理 GET 答案 200）以及针对通过普通 HTTP (421) 到达的 HTTPS 入口发送 `X-Forwarded-Proto: https`，如问题分类所要求的那样。
> - F29 地图：从 `F29.session-forwarded-proto` 中删除 `known bug` 标记，重写其散文和 uvicorn 陷阱行作为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `openhands-agent-server/openhands/agent_server/__main__.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_bridge.py`
- `tests/agent_server/test_preload_modules.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5928](https://github.com/OpenHands/software-agent-sdk/issues/5928)：[缺陷]：trust_forwarded_headers 关闭时，X-Forwarded-Proto 仍会改变 Canvas 桥接请求的来源，使预期的 200 变为 421；当前状态为已关闭，关闭时间为 2026-10-14T18:28:10Z。

> - [  ] 与 `trust_forwarded_headers` off, `X-Forwarded-Proto: https` 从回环客户端无法改变桥接的请求来源：bootstrap和代理 GET 在平地上---HTTP ingress answer `200`. - [  ] 与 `trust_forwarded_headers` 在转发头决定原点（`F29.trusted-forwarded-headers` 仍然有效 [  ] A 单元测试涵盖了修复 [  ] 地图弹珠 `F29.session-forwarded-proto` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因：服务器启动 uvicorn `openhands-agent-server/openhands/agent_server/__main__.py:313-326`) 不设置 `proxy_headers`因此，uvicorn 0.54 仍然使用默认配置 `proxy_headers=True` 与 `FORWARDED_ALLOW_IPS` 默认为 `127.0.0.1`. 其 `ProxyHeadersMiddleware` 重写 `scope["scheme"]` (and) `scope["client"]`) from `X-Forwarded-Proto`/`X-Forwarded-For` 在应用程序运行之前，对于回环对等体， `_request_origin` (`openhands-agent-server/openhands/agent_server/canvas_extensions/bridge.py:274`在第290行的不可信分支： `scheme = request.url.scheme`它已经读取了客户端提供的方案，和 `_require_ingress_host` (第299行) 回答 421。 桥接器无法恢复原始方案本身，因为 uvicorn 会改变适当的范围。 `trust_forwarded_headers` 已文档化 `openhands-agent-server/openhands/agent_server/config.py:374`. 启动中 `FORWARDED_ALLOW_IPS=192.0.2.1` （没有信任的回环对等体）使得 bootstrap 成功，这将原因归咎于 uvicorn 配置。 可能 

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5929#issuecomment-6159246348)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5929#pullrequestreview-5512505178)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 摘要将 uvicorn 的 `proxy_headers` 与 `Config.trust_forwarded_headers` 联系在 `python -m openhands.agent_server` 启动器 (`openhands-agent-server/openhands/agent_server/__main__.py`) 中。 `ProxyHeadersMiddleware` 默认情况下，uvicorn的`scope["scheme"]`不再对/`scope["client"]`进行重写，`X-Forwarded-Proto` /`X-Forwarded-For`的`FORWARDED_ALLOW_IPS`客户端（默认为回环）`_request_origin`读取请求的自身方案。 设置打开后，行为不会改变。 这与`config.py`（第374行）文档一致，与`bridge.py`和`_request_origin`在不受信任分支中实现的内容一致。## 验证 - 范围：该更改存在于Agent Server和入口这个仓库拥有的内容中。 画布桥代理代码是 u

<a id="5909-fixsdk-accept-the-documented-githubownerrepopath-install-source"></a>

### ＃5909：fix(sdk)：接受记录的GitHub：owner / repo / <path>安装源

- 提交：`98c97e6f18cecdaec96c011efb00f43db5b63bcc` (2026-10-14T20:28:41+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5909).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5909)。 家庭：F25、F26、F28。

陈述意图：

> - `openhands.sdk.extensions.fetch`：GitHub 简写在 `owner/repo` 之后采用可选路径，`fetch_with_resolution` 使用该路径作为 `repo_path`。 现有的遏制检查仍然适用，因此`github:o/r/../..`被拒绝。
> - 安装源描述：技能描述删除了树 URL 示例，并显示了 git URL 和 `repo_path`。 现在两个描述都说简写可以命名路径。
> - verify-智能体-server 映射：`# bug` 标记已从 `F25.install-documented-sources` 和 `F26.install-documented-source` 中删除。 `F26.install-errors` 现在使用 `github:qa` 来表示其离线无效速记情况，因为 `github:qa/f26/extra` 现在将尝试克隆。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`
- `.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md`
- `openhands-agent-server/openhands/agent_server/plugins_router.py`
- `openhands-agent-server/openhands/agent_server/skills_router.py`
- `openhands-agent-server/openhands/agent_server/skills_service.py`
- `openhands-sdk/openhands/sdk/extensions/fetch.py`
- `tests/sdk/extensions/test_fetch.py`

链接问题接受上下文：

- [#5895](https://github.com/OpenHands/software-agent-sdk/issues/5895)：[缺陷]：技能和插件安装会拒绝其 OpenAPI 描述中明确支持的来源形式，并返回 400；当前状态为已关闭，关闭时间为 2026-10-14T18:28:43Z。

> - [ ] `InstallSkillRequest.source` 和 `InstallPluginRequest.source` 中记录的每个源表单都会安装（或不再记录）。 - [ ] 无效的 GitHub 简写 (e.g. `github:owner` 没有 repo）仍然是没有网络调用的 400。 - `tests/sdk/extensions/test_fetch.py`中的[]单元测试涵盖了已接受的表格。 - [ ] 地图项目符号 `F25.install-documented-sources` 和 `F26.install-documented-source` 通过，`# bug` 标记被移除。 ### 安装方法 uv 同步在 main 的检查中 ### Version main at 6e7a853 ### 附加上下文根本原因： - `parse_extension_source` (`openhands-sdk/openhands/sdk/extensions/fetch.py:60-69`) 在 `github:` 之后恰好接受一个 `/`，否则引发 `ExtensionFetchError`； 安装路由映射到400。- `https://github.com/<owner>/<repo>/tree/<ref>/<path>` URL 被视为纯 Git URL 和 `normalize_git_url`，然后 `.git` (`openhands-sdk/openhands/sdk/git/utils.py:584-587`)。- 描述：`openhands-agent-server/openhands/agent_server/skills_router.py:150-158`、`openhands-agent-server/openhands/agent_server/plugins_router.py:97-103` 和文档字符串的 `service_install_skill` (`skills_service.py:502-506`)。- `_fetch_catalog_entries` 在 `skills_service.py:749-756` 也构建 `github:owner/repo[@ref]/<path>` 源，附有注释说安装可以解析它们； `tests/agent_server/test_skills_router.py`也使用`github:owner/repo/skills/test-skill`来源。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5909#issuecomment-6158916549)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5909#pullrequestreview-5512487380): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围此更改属于此存储库。 缺陷位于`openhands.sdk.extensions.fetch`（SDK的OpenAPI路径，该路径支持技能、插件和Canvas扩展安装），该缺陷属于本仓库，且`POST /api/skills/install`和`POST /api/plugins/install`的描述来自同一个源。 问题 #5895 已打开且带有 `ready-for-dev`，因此没有产品/架构决策在进行中。## 当前状态已重新核实 - 头部为 `a696ae47aaf0c91c58be0648aaa9b073caa01a7f`，与请求的 SHA 匹配。 PR是开放的，非草稿，无标签。 - 此帐户之前没有任何评论，也没有对此头的评论评论； 唯一的 PR 评论是机器人的 REST-API 损坏报告，并且没有未解决的评论线程。 - 该头的所有检查运行都是“成功”

<a id="5945-fixagent-server-remove-the-per-server-tmux_tmpdir-on-shutdown"></a>

### ＃5945：fix(agent-server)：在关闭时删除每个服务器TMUX_TMPDIR

- 提交：`d60b176ce32b45daec8127f134aa715f911d9637` (2026-10-14T20:30:40+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5945).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5945)。 家庭：F01、F03、F05、F30、F31、F32。

陈述意图：

> - 关闭时，`api_lifespan` 会删除每个服务器的 tmux 目录，但仅限于此进程创建的目录。 尽最大努力进行删除：将故障记录为警告并继续关闭。 用户提供的 `TMUX_TMPDIR` 或已存在的默认目录永远不会被删除。 环境恢复不变。
> - 测试：生命周期测试断言退出后该目录已消失。 新测试涵盖以下情况：
>   - 保留用户提供的`TMUX_TMPDIR`；
>   - 保留预先存在的默认目录；
>   - `TMUX_TMPDIR`过长，用户价值被恢复并保留，替代品被移除；
>   - 记录失败的删除并且不会中止关闭。
> - 地图：从 `F31.tmux-dir-cleanup` 中删除 `# bug` 标记和“已知错误”标签，并将其散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`
- `openhands-agent-server/openhands/agent_server/api.py`
- `tests/agent_server/test_api.py`

链接问题接受上下文：

- [#5932](https://github.com/OpenHands/software-agent-sdk/issues/5932): [Bug]: Agent Server 离开其进程 TMUX_TMPDIR (OpenHands-智能体-server-PID） 在优雅的关闭后 — 当前状态已关闭，关闭时间：2026-10-14T18:30:43Z。

> - [ ] 当服务器默认其自己的 `TMUX_TMPDIR` 时，正常关闭会删除该目录（并像今天一样恢复环境变量）。 - [ ] 服务器保留的用户提供的 `TMUX_TMPDIR` 永远不会被删除。 - [ ] `tests/agent_server/test_api.py` 中的单元测试断言该目录在 `api_lifespan` 退出后被删除，并保留为用户提供的值。 - [ ] 地图项目符号 `F31.tmux-dir-cleanup` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 其他上下文根本原因，在 `openhands-agent-server/openhands/agent_server/api.py` 中： - `_ensure_server_tmux_tmpdir`（第 143 行）使用 `mkdir(parents=True, exist_ok=True)`（第 149 行）创建默认目录并设置 `TMUX_TMPDIR`。 - `api_lifespan`的最后一个块（第351-357行）仅弹出或恢复`os.environ`中的`TMUX_TMPDIR`； 没有任何内容会删除该目录。 - `test_lifespan_defaults_and_restores_tmux_tmpdir` 仅检查环境变量。 相关：每服务器目录在 https://github.com/OpenHands/software-agent-sdk/pull/2970; 中引入， https://github.com/OpenHands/software-agent-sdk/pull/5559. 中的太长回退方案由verify-智能体-server的第一次完整智能体式运行找到； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5945#issuecomment-6159493648)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5945#pullrequestreview-5520265372)：_此评论由 AI 智能体 (OpenHands) 发布。_ **范围：** 此更改属于此存储库。 它涉及智能体-服务器生命周期代码（`openhands-agent-server/openhands/agent_server/api.py`中的`_ensure_server_tmux_tmpdir`/`api_lifespan`）、其单元测试和`verify-agent-server`特征图。 它不应移动存储库或关闭。 **为什么要停止做出决定：** PR机构直接要求做出决定（“需要做出决定...... 维护者应该确认他们更喜欢哪个门”），并且两个候选门在行为上并不等同。 在“此过程创建了目录”中移除门禁，会留下一个同名的默认目录，而建议的issue-triage（env-restore）则会移除它。 在共享`/tmp`-跨PID-命名空间情况下，这种差异是真实的，链接问题（#5932）c
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5945#pullrequestreview-5520674668)_这篇评论是由AI发布的智能体 (OpenHands代表请求方 user._  **判决： APPROVE.**  **范围。**  Agent Server 生命周期/清理 — 应该在这个仓库中。 `shutil` 这是 stdlib，所以没有打包更改。 `_ensure_server_tmux_tmpdir` 私有化的 `api_lifespan` 作为唯一发起方，且无公开渠道 API默认值、或网络合同更改。 **决策门已解决。** 作者的“决策需要”（在新系统中移除决策门） `created` 维护者（enyst，2026-10-14 14:30）回答了关于flag vs the env-restore guard的问题。 *让我们创建的吧。*  头部实现了那个选择，所以开放的问题已经关闭了。 **已验证 `4cecf3a4`** - `uv run pytest -q tests/agent_server/test_api.py` -> **51通过** (已本地化) CI所有53个在头上的检查运行都成功了`agent-server-tests`, `smoke-test`, `cross-tests`,

<a id="5918-fixagent-server-keep-the-clients-body-framing-in-proxied-requests"></a>

### ＃5918：fix(agent-server)：在代理请求中保留客户端的正文框架

- 提交：`1045bdffdb8dfc30f575645c7d2dfccf61f8e644` (2026-10-14T20:45:37+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5918).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5918)。 家庭：F12、F29。

陈述意图：

> - `proxy_http` (`docker_runtime/proxy.py`) 现在当客户端既不发送 `Content-Length` 也不发送 `Transfer-Encoding` 时不发送正文，重新添加客户端的 `Content-Length`，同时仍然流式传输正文（httpx 然后不会分块），并保持分块的客户端正文分块。 `body=` 替换作为字节传递，因此 httpx 设置其 `Content-Length`。
> - `tests/agent_server/docker_runtime/test_proxy.py` 中的新参数化单元测试检查 GET、固定长度 POST 和分块 POST 情况的上游框架和主体。
> - 地图项目符号 `F29.proxy-request-framing` 删除了其 `# bug` 标记和“已知错误”标签，其散文和匹配的陷阱行现在描述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py`
- `tests/agent_server/docker_runtime/test_proxy.py`

链接问题接受上下文：

- [#5913](https://github.com/OpenHands/software-agent-sdk/issues/5913)：[Bug]：代理 Canvas 应用程序后端请求始终到达后端分块，没有内容长度（包括 GET） - 当前状态已关闭，已关闭 2026-10-14T18:45:39Z。

> - [ ] 没有正文（无 `Content-Length`、无 `Transfer-Encoding`）的代理请求到达上游，无正文且无 `Transfer-Encoding`。 - [ ] 具有 `Content-Length: N` 的代理请求到达具有 `Content-Length: N` 且没有 `Transfer-Encoding` 的上游，仍然流式传输（未缓冲）。 - [ ] 分块客户端请求仍然被转发，Docker 运行时代理使用的 `body=` 替换仍然有效。 - [ ] `tests/agent_server/docker_runtime/test_proxy.py` 涵盖了这些情况的上游框架。 - [ ] 地图项目符号 `F29.proxy-request-framing` 通过，其 `# bug` 标记被删除（并且 `F29-app-backend-bridge.md` 中匹配的陷阱行被更新）。 ### 安装方法 uv 同步在 main 的检查中 ### 主版本位于 6e7a853 ### 其他上下文根本原因，在 `openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py` 中： - `_HOP_BY_HOP_HEADERS`（第46-49行）包括`content-length`（它不是RFC 7230中的逐跳），因此客户端的`Content-Length`被`_filter_headers`丢弃。 - `proxy_http` 始终将异步生成器 `_request_body()`（第 125-131 行）作为 `content=` 传递到 `client.stream(...)`（第 142 行）。 对于没有 `Content-Length` 标头的异步可迭代对象，对于每个方法，httpx 将主体构造为 `Transfer-Encoding: chunked`。 - Canvas 桥从 `proxy_app_backend_http` (`openhands-agent-server/openhands/agent_server/canvas_extensions/bridge.py:467`) 调用它； Docker运行时代理（`docker_runtime/routers.py:102`）共享它。 建议修复：保留流式传输，但客户端发送 nei 时不发送任何内容

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5918#issuecomment-6159091165)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5918#pullrequestreview-5512667954)：_此评论由 AI 智能体 (OpenHands) 发布。_ 针对 `main`（基础 `6e7a853`）审查了头 `53a93bcc`。 ## 范围更改属于此存储库：`openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py` 中的 `proxy_http` 是 Canvas 应用程序后端桥 (`canvas_extensions/bridge.py:467`) 和 Docker 会话代理 (`docker_runtime/routers.py:102`) 共享的智能体服务器代码。 无需产品/架构决策。## 我验证的内容（套接字级别，上游请求的原始 TCP 抓取）- 基础 `6e7a853`：`GET` 通过 `transfer-encoding: chunked` 并且没有内容到达上游； `POST` 和 `Content-Length: 13` 到达时分块，没有 `Content-Length`。 两者都与报告的错误 (#5913) 匹配。 - 头部 `53a93bcc`：`GET` 到达上游，没有主体，也没有帧头； `POST` 与 `Content-Length: 13` ar

<a id="5907-fixagent-server-dont-advertise-a-vs-code-url-while-vs-code-is-not-running"></a>

### #5907: fix(agent-server): 当 VS Code 未运行时不要宣传 VS Code URL

- 提交：`4e32a3adb05250477e936481acc77b403c48cba7` (2026-10-14T20:48:49+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5907).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5907)。 家庭：F16。

陈述意图：

> - `VSCodeService.get_vscode_url` 返回 `None`，除非服务器正在运行。 `get_vscode_service()` 在 `start()` 运行之前从 `session_api_keys[0]` 播种 token，因此 token 本身并不意味着服务器在那里（并且 `start()` 也在其端口检查之前创建 token）。
> - 单元测试：未运行的情况，带有 token，失败的 `start()`（端口已占用）不留下 URL； 现有的 URL 形状测试现在将服务标记为正在运行。
> - 地图 (F16)：`F16.vscode-url-not-running` 丢弃其 `# bug` 标记并获得缺失的 `Requires: F16.vscode-enabled-status`（没有它 `--only` 会出现 503“VS 代码已禁用”）。 `F16.vscode-url-shape` 和 `F16.vscode-folder-encoding` 被标记为 `blocked`（请参阅需要的决策），并且形状配方在空闲端口上启动 VS Code 并将保留的端口放回原处。 更新了散文和陷阱。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md`
- `openhands-agent-server/openhands/agent_server/vscode_service.py`
- `tests/agent_server/test_vscode_service.py`

链接问题接受上下文：

- [#5900](https://github.com/OpenHands/software-agent-sdk/issues/5900): [Bug]: /api/vscode/url 返回一个 URL 在 VS Code 不运行时携带会话密钥 — 当前状态已关闭，关闭于 2026-10-14T18:48:52Z。

> - 当服务器未运行时，[ ] `VSCodeService.get_vscode_url` 返回 `None`，即使设置了连接 token。 - [ ] `GET /api/vscode/url` 和 `GET /api/conversations/{conversation_id}/vscode/url` 在 VS Code 未启动的有密钥服务器上回答 `{"url": null}`，与无密钥和 `POST /api/init` 情况匹配。 - [ ] 正在运行的服务器仍然返回与今天相同的 URL（形状、`base_url`、`workspace_dir`、`vscode_base_path`）。 - [ ] `tests/agent_server/test_vscode_service.py` 中的单元测试用 token 组覆盖未运行的情况。 - [ ] 地图项目符号 `F16.vscode-url-not-running` 通过，其 `# bug` 标记被移除，并获得 `Requires: F16.vscode-enabled-status`。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 其他上下文根本原因：`get_vscode_service()` 在构建服务时从 `session_api_keys[0]` 播种连接 token (`openhands-agent-server/openhands/agent_server/vscode_service.py:287-289`)，在`start()`运行并失败之前，并且仅当token为`None`时`get_vscode_url`返回`None`(`vscode_service.py:125-126`)； 它从不检查`is_running()`。 一个延迟初始化服务器通过 `set_connection_token` 获取密钥，从而跳过一个未运行的服务器，因此有不同的答案。 在运行着 OpenVSCode 二进制的机器上， `start()` 也会在端口检查之前生成一个随机 token，因此，如果端口被占用，没有密钥的服务器会广播一个 URL，而不是运行中的服务器。 同样的修复也适用于这种情况。 相关： https://github.com/OpenHands/software-agent-sdk/issues/5845 （文件夹编码

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5907#issuecomment-6158892290)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5907#pullrequestreview-5512564786)_这篇评论是由AI发布的智能体 (OpenHands[_] [## Scope In-repo:] `openhands-agent-server` 拥有智能体-server REST  API, and `VSCodeService` / `vscode_router` 在这里生活。 无需跨仓库移动。## 评估根因问题 #5900 相符。 `get_vscode_service()` 种子 `connection_token` 从 `session_api_keys[0]` 之前 `start()` 运行，所以 `get_vscode_url`'s token-只有守卫通告了 URL （携带会话密钥）从未启动的 VS Code。 该变化做了 `get_vscode_url` return `None` 除非 `self.is_running()` — 一个最小且正确的门。 [已验证与当前主干：- 基线] `origin/main` (6e7a853) 重现了该 bug。 `VSCodeService(port=8001, connection_token='session-key')` → `is_running()=False`, `get_vscode_url()='http://localhost:8001/?tkn=session-key&folder=workspace'`- 头部返回 `None` for th

<a id="5787-fixagent-server-treat-ipv6-loopback-host-as-a-secure-context"></a>

### #5787: fix(agent-server): 将 IPv6 环回主机视为安全上下文

- 提交：`f67cba804501fb95af486ccb9f8157b81a283dae` (2026-10-14T20:56:25+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5787).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5787)。 家庭：F02。

陈述意图：

> - `_request_is_secure_context` 仅从括号内的主机或仅带有一个冒号的主机中去除 `:port` 后缀，因此裸露的 IPv6 主机名保持完整。
> - 测试：`Host: [::1]` 和 `Host: [::1]:8000` 薄荷糖获得 `Secure; Partitioned`； 带括号的 `X-Forwarded-Host: [::1]:8000` 继续工作。
> - 地图：`F02.workspace-session-ipv6-loopback` 失去其 `# bug` 标记和“已知错误”标签； 它的散文现在陈述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md`
- `openhands-agent-server/openhands/agent_server/auth_router.py`
- `tests/agent_server/test_workspace_cookie_auth.py`

链接问题接受上下文：

- [#5785](https://github.com/OpenHands/software-agent-sdk/issues/5785): [Bug]: 工作区-通过主机 [::1]:PORT 创建的会话 cookie 不安全（IPv6 环回不被视为安全上下文） — 当前状态已关闭，已关闭 2026-10-14T18:56:27Z。

> - [  ] A plain-HTTP mint with `Host: [::1]` 或 `Host: [::1]:PORT` gets `Secure; Partitioned`. - [  ]  `localhost`, `127.0.0.1` (带或不带端口)和括号 `X-Forwarded-Host: [::1]:PORT` still get `Secure`; 非回环的纯文本HTTP 主机仍然没有 [  ]  `tests/agent_server/test_workspace_cookie_auth.py` 覆盖 IPv6 回环 `Host` header. - [  ] 地图弹珠 `F02.workspace-session-ipv6-loopback` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6a298a4 的 checkout 中， 上下文根本原因，在 `openhands-agent-server/openhands/agent_server/auth_router.py`, `_request_is_secure_context` (42行) - 无 `X-Forwarded-Host`主机来自 `request.url.hostname` (第58行)，由 Starlette 返回 **未括号的** (`::1`- 标记处理（第60行）只匹配了标记 `X-Forwarded-Host` form 否则，代码会剥离一个端口 `host.split(":")[0]` (第63行)，这导致了 `::1` into `''`因此，回环检查失败。 建议的修复：只去除一个 `:port` 当主机恰好有一个冒号（多个冒号的未括号主机是一个裸 IPv6 地址）时，后缀。 相关：  https://github.com/OpenHands/software-agent-sdk/issues/4562  (private-)LAN  HTTP cookies 不同的主机类，不是这个错误）。 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5787#issuecomment-6157103305)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5787#pullrequestreview-5511285919): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 摘要此 PR 修复了一个真正的错误：`_request_is_secure_context` 在 `:` 上拆分 `request.url.hostname`，但 `request.url.hostname` 返回不带括号的 IPv6 地址 (`::1`)，因此 `Host: [::1]:PORT` 薄荷被减少为空字符串，并且环回检查失败。 结果是一个缺少`Secure`的`SameSite=None`cookie，浏览器会拒绝，破坏了IPv6回环中的cookie-authenticated工作区嵌入。## 评估我对比了工作区和当前的主干：- **正确性。** 新的`elif host.count(":") == 1`保护只对单冒号主机进行`:port`后缀的剥离。 裸露的 IPv6 主机名 (`::1`) 现在保留所有冒号并匹配 `_LOOPBACK_HOSTS`，而真正的 `host:port` 仍解析为其主机。 我重播了基础与头部逻辑：`[::1]`/`[::1]:800

<a id="5774-fixagent-server-reap-canvas-backends-orphaned-by-a-crashed-server"></a>

### ＃5774：fix(agent-server)：收获因服务器崩溃而孤立的 Canvas 后端

- 提交：`91b89bdc6f33d185a1da85e9da54c521e53fcdec` (2026-10-14T20:59:17+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5774).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5774)。 家庭：F01、F03、F05、F28、F30、F31、F32。

陈述意图：

> - `CanvasExtensionBackendManager` 现在为每个启动的后端写一个小记录 `backends/run/<pgid>.json`进程组，领导者的启动时间（`/proc/<pid>/stat`), 和服务器自己的进程 ID 和启动时间。 `_terminate_runtime` 一旦组停止，就删除记录。
> - 新的 `reap_orphans()`，在路由服务之前从 API 生命周期中调用。 对于服务器不再运行的每个记录，它会使用现有的 SIGTERM-then-SIGKILL 逻辑停止该组。 只有当记录的领导者仍然匹配（相同的开始时间，`artifacts/<name>/`下的命令行）时才发出信号，因此回收的进程和无关进程将被忽略。 然后它会删除该记录。 服务器仍处于活动状态的记录将被跳过，因此同一状态目录上的第二个服务器不会杀死另一个服务器的后端。
> - REST 合约、TypeScript 客户端和 Docker 行为保持不变。 地图项目符号 `F28.hard-restart-orphan` 删除了其 `known bug` 标记，现在描述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`
- `openhands-agent-server/openhands/agent_server/api.py`
- `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`

链接问题接受上下文：

- [#5637](https://github.com/OpenHands/software-agent-sdk/issues/5637): [Bug]Canvas 后端存活于  SIGKILLed  智能体-server; restart 报告它已停止并启动第二个 — 当前状态已关闭，已关闭 2026-10-14T18:59:19Z。

> - [ ] 在 SIGKILL 后并在相同的 `OH_PERSISTENCE_DIR` 上重新启动，一旦提供路由，死服务器的后端就不再活动。 - [ ] `start` 永远不会为一个应用程序留下两个进程，并且 `DELETE .../backend/data` 在其后端处于活动状态时永远不会成功。 - [ ] 使用真实的子进程进行的测试涵盖了崩溃和重新启动路径。 - [ ] 地图项目符号 `F28.hard-restart-orphan` 通过并删除了其已知错误标记。 ### 安装方法 uv 同步在 main 的签出中 ### Version main at 2804c12 ### 附加上下文在 `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py` 中： - 第 642-649 行使用 `start_new_session=True` 生成后端。 没有任何东西将它与服务器的生命周期联系起来。 - 内存中 `self._runtimes` (127) 是正在运行的后端的唯一记录。 `_status_unlocked`(409-442)报告`backends/run/<name>.json`中的`stopped`/`pid:null` when it has no entry. - `shutdown()` (786-790) runs only from the lifespan's `finally` (`api.py:344-346`), and a SIGKILL skips it. - `start` (589) and `delete_data` (768-777) check only the in-memory runtime. Suggested fix: on start, record the pgid and the leader's start time (`/proc/<pid>/stat`)，并删除停止时的记录。 在启动时，之前服务之前，杀死每个仍然匹配其记录的剩余组（相同的启动时间，`artifacts/<name>/`下的cmdline）SIGTERM-然后-SIGKILL逻辑。 单独 `PR_SET_PDEATHSIG` 是不够的，因为当分叉线程退出时它会触发。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5774#issuecomment-6156527226)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5774#pullrequestreview-5511721198)_这篇评论是由AI发布的智能体 (OpenHands## 适用于本仓库的范围：[ ] Agent Server 拥有 Canvas 应用后端生命周期 `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`. 更改与链接问题的有限范围相匹配（主机进程崩溃/重新启动； 无 REST 合同 TypeScript, 或 Docker -  **请输出简体中文译文。** 头还在这里 `c0b007e8dd8fbd6d3110d2af1ef1576826bb7074`, all GitHub 在那个确切的头颅上检查动作，没有经过任何审查或评论。 问题 #5637 打开且包含 `bug`, `priority:low`, `ready-for-dev`. - **独立繁殖（行为，真实） 子进程):** 启动了一个真正的 `CanvasExtensionBackendManager` 后端（领导者 + 分叉） `sleep` with `start_new_session=True`, `kill -9`然后运行了服务器 `reap_orphans()`

<a id="5891-fixsdk-keep-edge-whitespace-on-the-original-side-of-a-git-diff"></a>

### ＃5891：fix(sdk)：在 git diff 的原始一侧保留边缘空白

- 提交：`dc897208faae41296f9bee3ac6cc147a25a5f11a` (2026-10-14T22:01:26+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5891).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5891)。 家庭：F14、F15。

陈述意图：

> - `run_git_command` 获得仅关键字 `strip: bool = True`。 所有现有的调用者都保留剥离的输出。
> - `get_git_diff` 使用 `strip=False` 读取 `git show` blob，并按照已标准化修改侧的方式对其进行标准化，因此未更改的文件具有相同的侧。 CRLF 文件的行为与以前一样。
> - 地图：`F15.diff-whitespace` 项目符号删除了其 `# bug` 标记和“已知错误”标签，散文和陷阱现在描述了固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`
- `openhands-sdk/openhands/sdk/git/git_diff.py`
- `openhands-sdk/openhands/sdk/git/utils.py`
- `tests/sdk/git/test_git_diff.py`

链接问题接受上下文：

- [#5888](https://github.com/OpenHands/software-agent-sdk/issues/5888): [Bug]: git diff 显示以缩进开头或以空行结尾的未更改文件的虚拟更改 — 当前状态已关闭，已于 2026-10-14T20:01:29Z 关闭。

> - [  ] 未更改文件的工作区差异返回相同 `original` 和 `modified`包括带有首行缩进的文件、首行空白行、末行空白行和末行空白行 CRLF 行末 [  ] 双方继续使用当前的规范化`"\n".join(text.splitlines())`, 所以 CRLF 文件和现有的 diff 测试未改变 [  ]  `run_git_command`其其他调用者（refs，)的输出保持脱敏 SHAs- 名称状态列表 [  ]  `tests/sdk/git/test_git_diff.py` 覆盖这些形状不变的文件 [  ] 地图弹珠 `F15.diff-whitespace` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因，在 `openhands-sdk/openhands/sdk/git/git_diff.py`: - `original` 来自 `run_git_command(["git", "show", f"{current_rev}:{path}"], ...)` (lines 111-113)，并且 `run_git_command` 返回 `result.stdout.strip()` (`openhands-sdk/openhands/sdk/git/utils.py:115`), 会删除第一行的首缩进和每行末尾的空白行 `modified` 是 `"\n".join(f.read().splitlines())` (第121行)，既保留了所有行的终止符，又只保留了最后一个终止符。 提交模式的差异（）`get_commit_file_diff`, `openhands-sdk/openhands/sdk/git/git_commits.py:173`它会去除两边，所以没有虚的改变，虽然它也失去了第一行的缩进和尾部的空白行。 相关：#5857（已删除文件的工作树差异）更改了相同的功能，但保留了双方的读取方式不变。 由第一完整发现的智能体式 run of v

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5891#issuecomment-6158624498)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5891#pullrequestreview-5518414873)：_此评论由 AI 智能体 (OpenHands) 发布。_ **Scope.** In-repo：更改修复了 `openhands-sdk/openhands/sdk/git/git_diff.py` 中的 `get_git_diff`，该问题归此处所有，链接的问题 #5888 是 `bug` / `priority:low` / `ready-for-dev`。 不需要产品或架构决策。 **我核实的`0ac9d3c`。** - 根本原因确实存在，并且与问题相符：基础侧来自`run_git_command`，而磁盘侧来自`.strip()`，后者是git的stdout，而磁盘侧是`"\n".join(text.splitlines())`。 我通过真实的 `get_git_diff` 入口使用实际的 git 存储库复制了它。 在`origin/main`中，`lead.txt`给出`original="indented line\nbody"`与`modified=" indented line\nbody"`，`trail.txt`给出`"body"`与`"body\n\n"`。 在此头上，两个文件返回相同的边（`" indented line\nbody"` 和 `"body\n\n"`），匹配 th

<a id="5903-fixagent-server-clear-the-skills-marketplace-cache-on-sync"></a>

### ＃5903：fix(agent-server)：清除同步上的技能市场缓存

- 提交：`923ff2de5fd670941da3b8c0c6b8d6d0d4028e8e` (2026-10-14T22:14:36+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5903).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5903)。 家庭：F25。

陈述意图：

> - `sync_public_skills` 成功时清除市场目录缓存（新的 `_invalidate_catalog_cache` 帮助程序）； 失败的同步保留它。
> - `service_get_marketplace_catalog` 仅缓存非空结果，与 `plugins_service` 已使用的规则相同。
> - 单元测试两者； `F25.marketplace-stale-cache` 地图项目符号失去了其已知错误标记，其散文和陷阱行现在描述了固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`
- `openhands-agent-server/openhands/agent_server/skills_service.py`
- `tests/agent_server/test_skills_service.py`

链接问题接受上下文：

- [#4665](https://github.com/OpenHands/software-agent-sdk/issues/4665)：[错误]：技能市场针对当前扩展清单布局返回空 - 当前状态打开、关闭 -。

> - [ ] 当 `marketplaces/default.json` 不存在时，技能会从真实的 `.plugin/marketplace.json` 布局中加载。 - [ ] 自定义显式市场路径仍然支持回退方案。 - [ ] TTL 中的技能和插件使用相同的获取/解析快照。 - [ ] 瞬时获取/解析失败不会缓存空目录。 - [ ] 现有插件优先级名称优先级、插件过滤、安装状态新鲜度和 REST 模式保持不变。 ### 当前版本 `main` 位于 `6d3881035`。 存储库布局于2026-08-27通过GitHubAPI独立验证； 现有问题搜索未发现重复项。

- [#5893](https://github.com/OpenHands/software-agent-sdk/issues/5893): [Bug]: GET  /api/skills/marketplace 它在保持其缓存目录（包括空目录）的同时继续提供服务 POST  /api/skills/sync — 当前状态已关闭，关闭时间：2026-10-14T20:14:38Z。

> - [ ] 成功的 `POST /api/skills/sync` 会清除市场目录缓存，因此下一个 `GET /api/skills/marketplace` 会列出同步引入的条目。 - [ ] 不会缓存空目录结果（与插件目录的规则相同），因此暂时性故障不会清空 TTL 的选项卡。 - [ ] A 单元测试涵盖两者。 - [ ] 地图项目符号 `F25.marketplace-stale-cache` 通过，其 `# bug` 标记被删除。 ###安装方法`uv sync`在main的checkout中。 ### 主版本位于 6e7a8532ef4426da08b5c06dd57cf4795303be01 ### 其他上下文根本原因： - `openhands-agent-server/openhands/agent_server/skills_service.py:462-484` (`sync_public_skills`) 仅在成功时调用 `_invalidate_public_skills_cache()`； 目录的 `_catalog_cache` (`skills_service.py:659`) 被保留。 - `skills_service.py:688-692` (`service_get_marketplace_catalog`) 存储 `_fetch_catalog_entries` 返回的任何内容，包括 `[]`； Compare `plugins_service.py:282-285`，仅缓存非空结果。 相关： https://github.com/OpenHands/software-agent-sdk/issues/4665 （针对当前清单布局的空市场）。 这是那里提到的单独的缓存失效情况（ https://github.com/OpenHands/software-agent-sdk/issues/4665#issuecomment-6112142654 ）； 仅修复清单布局并不会使新同步的条目可见。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5903#issuecomment-6158830354)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5903#pullrequestreview-5512443918)：_此审查由 AI智能体（OpenHands）发布。_ ## 审查：PR #5903 — 在同步时清空技能市场缓存。**范围：**属于范围内。 更改仅限于该存储库拥有的 Agent Server 包 (`openhands-agent-server/openhands/agent_server/skills_service.py`)、其单元测试和 `verify-agent-server` 特征图。 不需要跨仓库移动。 **评估：**该修复符合链接问题的接受标准（#5893 - `bug`、`priority:low`、`ready-for-dev`）并反映了现有的`plugins_service`先例。 - `sync_public_skills` 现在在成功时调用 `_invalidate_catalog_cache()`（第 479 行），因此下一个 `GET /api/skills/marketplace` 会重新读取刷新的克隆，而不是提供陈旧的 5 分钟条目。 失败的同步使缓存保持完整，与现有的`_invalidate_public_skills_cache`汉一致

<a id="5905-fixsdk-name-a-manifest-less-git-repository-plugin-after-the-repository"></a>

### #5905: fix(sdk): 在存储库之后命名一个无清单的 git 存储库插件

- 提交：`7bb4be18ca42bf0e44748183baa6a56eb329621a` (2026-10-14T22:17:13+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5905).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5905)。 家庭：F25、F26、F28。

陈述意图：

> - `InstallationManager.install` 现在加载了一个未从远程源获取的远程源 `repo_path` 从一个临时副本（没有 ） `.git`) 以仓库命名的`extract_repo_name`, 该助手命名缓存目录)，因此一个从目录中推断名称的加载器会看到 `<repo>`对于本地目录。 本地源和 `repo_path` 如之前一样，安装在位。 安装的文件仍然从获取的路径复制。 `update` 加载安装名称下的根目录（见需决策）。
> - 测试：无清单 `file://` git 存储库安装为 `qa-src`（在 main 上安装失败，为 `qa-src-<hash>`）； 以其他名称安装的 root 使其保持更新； 网络测试 `test_install_document_skills_plugin` 断言 `github:anthropics/skills` 的旧缓存目录名称，现在需要 `skills`。
> - 地图：`F26.install-repo-root-name` 失去其 `# bug` 标记和“已知错误”标签； 散文和克劳德代码布局明白了预期的名称。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md`
- `openhands-sdk/openhands/sdk/extensions/installation/manager.py`
- `tests/sdk/plugin/test_installed_plugins.py`

链接问题接受上下文：

- [#5896](https://github.com/OpenHands/software-agent-sdk/issues/5896): [Bug]: 没有清单的 git 插件，没有 repo_path 安装，以其缓存目录 (repo-HASH) 而不是存储库命名 - 当前状态已关闭，已关闭 2026-10-14T20:17:15Z。

> - [ ] 没有 `repo_path` 且没有根清单安装的 git 源以存储库（URL 的 `extract_repo_name`）命名，并安装在该目录下。 - [ ] 具有清单的源、具有 `repo_path` 的源和本地路径保留其当前名称。 - [ ] `tests/sdk/extensions/` （或 `tests/sdk/plugin/`）中的单元测试涵盖了安装无清单 git 存储库根。 - [ ] 地图项目符号 `F26.install-repo-root-name` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因： - `InstallationManager.install` (`openhands-sdk/openhands/sdk/extensions/installation/manager.py:89-97`) 直接从路径 `fetch_with_resolution` 返回加载扩展。 对于没有 `repo_path` 的远程源，即由 `get_cache_path` 构建的 `cache/extensions/<repo>-<sha256[:16]>` 的克隆根（`openhands-sdk/openhands/sdk/extensions/fetch.py:209-228`，在第 257 行使用）。- 没有 manifest 时，Claude 代码格式会回退到目录名（`openhands-sdk/openhands/sdk/plugin/format/claude_code.py:106-115`），因此缓存目录名变为插件名。 `Plugin.load` 解析路径，因此具有正确名称的符号链接不会有帮助。 相关：#4520（GitHub简写解析），#5496（并发`.installed.json`写入）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5905#issuecomment-6158821345)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5905#pullrequestreview-5512583491)_这篇评论是由AI发布的智能体 (OpenHands)._ ## 评估变更解决了报告的问题，并且保持在本仓库的控制范围内SDK 插件/技能/扩展安装）。 经过当前主干验证 `53bd765abebf7982ae1b56ed721bd61bfedadfaa`; 头部没有移动，也没有事先对其进行审查。 我已经检查了：- **根本原因和解决方案。**  `InstallationManager._load_fetched` 现在远程源被无条件获取了 `repo_path` 将数据转换为一个名为仓库的临时副本`extract_repo_name(url)`, 或者安装名称下的 `update`) 并从那里加载，所以一个没有 manifest 的插件会看到 `<repo>` instead of the `<repo>-<hash>` 克隆缓存目录。 `repo_path` 安装和 `SourceType.LOCAL` 源代码仍然按预期加载，与问题中提到的未变情况匹配。 名称来源 (`extract_repo_name`) is th

<a id="5921-fixagent-server-leave-web-researcher-out-of-sub-agents-when-the-browser-is-disabled"></a>

### #5921: fix(agent-server): 当浏览器被禁用时，将 web-researcher 排除在子智能体之外

- 提交：`4804aa0be06f3a90e88037a3a580e7c069a2195b` (2026-10-14T22:19:54+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5921).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5921)。 家庭：F27。

陈述意图：

> - `get_sub_agents` 通过 `enable_browser=configured_browser_available(config) is not False` 到 `discover_builtin_agents`。 该函数已经过滤了`web-researcher`； 只是从来没有被告知这样做。
> - `tests/agent_server/test_sub_agents_router.py` 中的单元测试（在 `enable_browser` 上参数化）。
> - 地图：`F27.subagents-browser-disabled` 现在以 `enable_browser: false` 本身重新启动。 之前，它依赖于早期项目符号的重新启动，因此 `--only` 在启用浏览器的情况下运行它。 它的 `# bug` 标记被删除，散文描述了固定的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`
- `openhands-agent-server/openhands/agent_server/sub_agents_router.py`
- `tests/agent_server/test_sub_agents_router.py`

链接问题接受上下文：

- [#5911](https://github.com/OpenHands/software-agent-sdk/issues/5911): [Bug]: POST /api/sub-agents 列出 enable_browser 为 False 时仅浏览器的网络研究人员 — 当前状态已关闭，已关闭 2026-10-14T20:19:56Z。

> - 当服务器的配置禁用浏览器时，[ ] `POST /api/sub-agents` 会省略 `web-researcher`（`enable_browser: false`； 对于 Docker 会话运行时，每当配置的浏览器可用性为 False 时，- [ ] 启用浏览器后，内置列表保持不变（仍然包括 `web-researcher`）。 项目/用户智能体不受影响。 - [ ] `tests/agent_server/test_sub_agents_router.py` 涵盖两种配置。 - [ ] 地图项目符号 `F27.subagents-browser-disabled` 通过，其 `# bug` 标记被删除。 ### 检查 main 中的安装方法 uv 同步 ### 版本 main 位于 6e7a853 ### 附加上下文根本原因： - `get_sub_agents` (`openhands-agent-server/openhands/agent_server/sub_agents_router.py:129`) 不带参数调用 `discover_builtin_agents()`。 - 当 `enable_browser` 为 False（第 128 行）时，`discover_builtin_agents(enable_browser: bool = True)` (`openhands-tools/openhands/tools/preset/default.py:111`) 已经过滤了 `web-researcher`，但始终使用默认的 `True`。 - 工具目录路由已经从`configured_browser_available(config)`的配置中获取浏览器可用性（`openhands-agent-server/openhands/agent_server/launch.py:103`，在`tool_router.py:57`中使用）； 子智能体路线永远不会读取 `request.app.state.config`。 相关（单独的项目，不在范围内）：`/server_info` `usable_tools` 忽略 `enable_browser` (`F27.server-info-browser-disabled`)，以及 `tool_router.py` 中的导入时间 `register_builtins_agents(enable_browser=True)` 将 `web-researcher` 保留在委托注册表中。 由第一发现的

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5921#issuecomment-6159129204)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5921#pullrequestreview-5512470254): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论摘要范围正确：修复位于此存储库拥有的 Agent Server REST 路径中，匹配链接问题 #5911（开放，`bug` / `priority:low` / `ready-for-dev`）及其接受标准。 ### 我在头 `c5dc63d` - ** 上验证的内容和修复。** `get_sub_agents` 之前使用其默认值 `enable_browser=True` 调用 `discover_builtin_agents()`，因此具有 `enable_browser: false` 的配置仍然列出仅浏览器 `web-researcher`。 该路由现在读取 `http_request.app.state.config`（已在 `create_app` 中设置）并传递 `enable_browser=configured_browser_available(config) is not False`，该帮助器与工具目录路由使用的帮助器 (`tool_router.py`) 相同。 当 `enable_browser` 关闭时，`configured_browser_available` 返回 `False`，`container_browser_en

<a id="5931-fixagent-server-answer-uploads-onto-a-directory-or-below-a-file-with-400"></a>

### ＃5931：fix(agent-server)：答案上传到目录或文件下 400

- 提交：`75105bd40936f1962d8fa91506776a0c02ba957f` (2026-10-14T22:24:23+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5931).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5931)。 家庭：F14。

陈述意图：

> - `_upload_file` 现在将 `IsADirectoryError` 映射到 400 `Path is a directory`，将 `FileExistsError` / `NotADirectoryError`（当父级是文件时 `mkdir(parents=True)` 引发）映射到 400 `A parent of the path is not a directory`。 其他所有失败仍返回 500。 对话范围的路由 `POST /api/conversations/{id}/file/upload` 安装相同的处理程序。
> - 测试：一个覆盖全局路由的参数化测试，该测试覆盖了一个目录目标、一个直接父文件以及一个更上层的文件。 对话范围的测试涵盖了这两种冲突。 每个测试还断言磁盘上没有任何变化。
> - 特征图：`F14.upload-onto-directory` 不再具有其 `# bug` 标记，现在断言确切的 400 个细节。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`
- `openhands-agent-server/openhands/agent_server/file_router.py`
- `tests/agent_server/test_file_router.py`
- `tests/agent_server/test_runtime_router.py`

链接问题接受上下文：

- [#5930](https://github.com/OpenHands/software-agent-sdk/issues/5930): [Bug]: POST  /api/file/upload 返回500而不是400，表示当前状态已关闭，关闭时间：2026-10-14T20:24:25Z。

> - [  ] 上传到现有目录返回 400，并附有明确的错误信息 `detail`, 且目录未变 [  ] 上传到一个路径的父目录（直接或更上层）是一个普通文件时，返回状态码 400 并附有明确的错误信息 `detail`, 文件未改变 [  ] 其他上传失败（I/O错误等）仍然返回500 [  ]  `tests/agent_server/test_file_router.py` 涵盖了这两种情况 [  ] 地图弹珠 `F14.upload-onto-directory` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因，在 `openhands-agent-server/openhands/agent_server/file_router.py`: - `_upload_file` 运行 `target_path.parent.mkdir(parents=True, exist_ok=True)` (98) and `open(target_path, "wb")` (行 104) `mkdir` 提出了 `FileExistsError` / `NotADirectoryError` 当父文件是  `open` 提出了 `IsADirectoryError` 当目标是目录时。- 处理器的 `except Exception` （113-118）将每一条非-`HTTPException` into a 500. - `create_directory` (731-740) 已经映射了 `FileExistsError` / `NotADirectoryError` 到400 `Path exists and is not a directory`. 相关：相同 `_upload_file` 被开放的上传修复影响 `file_size` (F14.upload-size) 和原子覆盖 (F14.upload-atomic) 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5931#issuecomment-6159343821)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5931#pullrequestreview-5512691922): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围在范围内。 该更改属于 `openhands-agent-server`：它编辑 `openhands-agent-server/openhands/agent_server/file_router.py` 中的规范 REST 处理程序 `_upload_file`，该存储库根据 `AGENTS.md` 中的跨存储库边界拥有该处理程序。 无需做出产品/架构决策 — 链接的 issue #5930 (标签 `bug`, `priority:low`, `ready-for-dev`) 已修复预期的状态码为 400，与 `create_directory` 在同一文件中的描述一致。## 发现无实质性错误、安全或兼容性缺陷。 根据当前头 `0f38cdba` 进行验证： - 两个新的 `except` 分支是不相交的并且类型正确。 `IsADirectoryError` 映射到 400 `Path is a directory`； `(FileExistsError, NotADirectoryError)` 映射到 400 `路径的父级不是

<a id="5924-fixagent-server-apply-enable_browser-to-server_info-usable_tools"></a>

### ＃5924：fix(agent-server)：应用enable_browser到/server_infousable_tools

- 提交：`8efff8d3cf1a5a3fcf7ce5e3b97c7f00684d9547` (2026-10-15T03:24:31+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5924).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5924)。 家庭：F01、F29。

陈述意图：

> - `build_server_info` 采用 `browser_available` 且 `get_server_info` 通过 `configured_browser_available(config)`，与目录路由应用相同的决策； `None`（本地运行时，启用浏览器）保留 Chromium 探针。
> - 单元测试为 `enable_browser=False` 路线，`build_server_info` 为 `None`/`True`/`False`.
> - 地图：`F27.server-info-browser-disabled` 删除其 `# bug` 标记，声明 `Requires: F27.browser-probe, F27.browser-disabled`（其设置，因此 `--only` 单独工作），并且 `F27.catalog-docker-runtime` 现在断言 `usable_tools` 列出了库存图像的浏览器。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`
- `openhands-agent-server/openhands/agent_server/server_details_router.py`
- `tests/agent_server/test_server_details_router.py`

链接问题接受上下文：

- [#5915](https://github.com/OpenHands/software-agent-sdk/issues/5915): [Bug]: /server_info usable_tools 列出 browser_tool_set，而 enable_browser 为 False — 当前状态已关闭，已关闭 2026-10-15T01:24:33Z。

> - []与`enable_browser: false`、`GET /server_info``usable_tools`不包含`browser_tool_set`，匹配`GET /api/tools/catalog`。 - [ ] 对于 `enable_browser: true`（本地运行时），`usable_tools` 不变（仍然由 Chromium 探针决定）。 - [ ] `tests/agent_server/test_server_details_router.py` 中的单元测试涵盖了禁用的情况。 - [ ] 地图项目符号 `F27.server-info-browser-disabled` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因： - `ServerInfo.usable_tools` (`openhands-agent-server/openhands/agent_server/server_details_router.py:58`) 默认为 `list_usable_tools()` (`openhands-sdk/openhands/sdk/tool/registry.py:230`)，它仅运行每个工具的可用性检查（对于浏览器，Chromium 探针），并且永远不会看到 `Config.enable_browser`。 `get_server_info` (`server_details_router.py:152`) 也不通过配置的浏览器决定。 - 目录路由适用`configured_browser_available(config)`（`openhands-agent-server/openhands/agent_server/launch.py:103`，在`tool_router.py:57`中使用），并启动删除浏览器，因此只有`/server_info`不同意。 - 同一个助手还修复了对话图像中 `conversation_runtime: docker` 的浏览器； `/server_info` 也忽略了这一点（在地图的 `F27.catalog-docker-runtime` 项目符号中注明）。 相关： https://github.com/OpenHands/software-agent-sdk/issues/5899 （Chromium 探针忽略 `PLAYWRIGHT_BROWSERS_PATH`； 一个单独的探针问题）。 由第一次完整的智能体式运行发现

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5924#issuecomment-6159141443)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5924#pullrequestreview-5519991487)：_此评论由 AI 智能体 (OpenHands) 发布。_ 已评论的标题 `fc6ebe3`（与请求的 SHA 匹配）。 范围是正确的：Agent Server REST 表面属于此存储库，链接的问题 #5915 是 `ready-for-dev` (`bug`, `priority:low`)。 我当前主干上验证的： - 差异符合描述：`build_server_info` 取 `browser_available`，`get_server_info` 通过 `configured_browser_available(config)` — 与工具-目录路由使用的相同辅助工具。 `None`（本地运行时，启用浏览器）让 Chromium 探针负责进程，非浏览器工具保持不变。 - 重点测试：`uv run pytest tests/agent_server/test_server_details_router.py` → 14 个通过，包括新的禁用浏览器测试和 `build_server_info` 的 `None`/`True`/`False` 覆盖率。 - 与 Chromi 进行实时端点检查
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5924#issuecomment-6178130283)：我是一名 AI 智能体（Claude Code），帮助 Engel Nyst (@enyst) 进行项目维护。 合并 `main` 到这个分支 (c3f2a8e)。 唯一的冲突是在 F27 地图中，其中 main 的子智能体修复（`F27.subagents-browser-disabled`，不再是已知错误）和这个 PR 的 `/server_info` 修复触及了相邻的行； 两者都保留。 代码合并干净，路由器测试通过，并且 `map check` 和预提交是干净的。 `agent-server-stress-tests` 在合并提交上是红色的，但这不是由这个 PR 引起的：`test_concurrent_conversations_isolated_and_fast` 在 `main` 的头上以同样的方式失败（75105bd，0.59s 相对于 0.54s 预算），并且这个 PR 不触及对话并发。 我还没有找到现有的修复方法。 我已经重新运行一次失败的作业。 --- _由 [Claude Code](https://claude.ai/code) 生成_

<a id="5983-refactoragent-profiles-remove-inline-profile-launches-and-keep-a-profile-active"></a>

### ＃5983：refactor(agent-profiles)：删除内联配置文件启动并保持配置文件处于活动状态

- 提交：`818c161b534477849716d445b2927b433f9dd9ab` (2026-10-15T10:51:09+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5983).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5983)。 族：F04、F05、F06、F10、F12、F16、F18、F19、F20、F21、F22、F27、F30、F31、F32、F33、F34。

陈述意图：

> - **内联启动源已删除。** `StartConversationRequest.agent_profile` 和 `LaunchedAgentProfile.inline` 以及它们在启动时的处理、Docker 转发和存储的请求都消失了。 唯一智能体来源为 `agent_profile` 的请求现在会失败验证，并显示“必须提供 `agent`、`agent_settings` 或 `agent_profile_id` 之一”。 除了另一个来源之外，`agent_profile` 像任何未知字段一样被忽略。 `resolve()` 仍然接受配置文件对象，因为未保存草稿的具体化预览使用它。
> - **配置文件始终处于活动状态。**新锁定的助手 `_ensure_active_profile` 将丢失或悬空的指针移动到 `default`。 当 `default` 不存在时，它将从当前设置中播种。 列出配置文件、解析活动配置文件和删除活动配置文件都称为它。
>   - 删除活动配置文件现在会激活 `default`，而不是清除指针。 删除活动的 `default` 会重新播种它。
>   - 当 `default` 存在但无法加载，或者商店已达到 50 个配置文件限制而没有配置文件时，将激活第一个其他配置文件。

更改的路径：

- `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `openhands-agent-server/openhands/agent_server/docker_runtime/routers.py`
- `openhands-agent-server/openhands/agent_server/launch.py`
- `openhands-agent-server/openhands/agent_server/openai/service.py`
- `openhands-sdk/openhands/sdk/conversation/request.py`
- `openhands-sdk/openhands/sdk/launch/resolve.py`
- `openhands-sdk/openhands/sdk/profiles/agent_profile.py`
- `openhands-sdk/openhands/sdk/settings/model.py`
- `tests/agent_server/test_agent_profile_conv_start.py`
- `tests/agent_server/test_agent_profiles_router.py`
- `tests/agent_server/test_launch_architecture.py`
- `tests/agent_server/test_launch_parity.py`
- `tests/agent_server/test_openai_gateway_launch.py`
- `tests/sdk/launch/test_resolve.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5983#issuecomment-6167607191)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5983#pullrequestreview-5519317231)：已批准 - 可以安全合并。 **为什么这是安全的：** - 删除了 `StartConversationRequest.agent_profile` 和 `LaunchedAgentProfile.inline`，两者仅在 v1.54.0 之后出现，因此没有发布的客户端发送或读取它们。 - 使存储的智能体配置文件始终处于活动状态：丢失/悬挂指针移动到 `default`（不存在时从当前设置播种），删除活动配置文件会激活 `default`。 `_ensure_active_profile` 在商店锁下运行，因此并发首先请求种子一次。 - 网关现在启动存储的配置文件，并在 None 激活时返回 409，而不是退回到内联未保存的配置文件。 - 所有 CI 都是绿色的，包括 OpenAPI 破损检查 (PASSED)、sdk/agent-server/workspace/cross 测试、ACP 实时测试和智能体-服务器压力测试。 没有发现阻塞问题。 一个非阻塞注释
- [reviews CHANGES_REQUESTED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5983#pullrequestreview-5520703887): **REQUEST_CHANGES** 我追踪了当前分支上更改的路径`c67bfe4`) 并找到了一个可重复使用的材料回归。 其他一切 PR 检查完毕。 --- ### 阻止：一个损坏/不可读的 `default` 文件砖块了这个头像 API  `agent_profiles_router.py:266` (`_profile_to_activate`) 只能捕获 `FileNotFoundError` 从 `store.load(SEED_PROFILE_NAME)`: ```python try: profile = store.load(SEED_PROFILE_NAME) except FileNotFoundError: ...seed... ```  `AgentProfileStore.load()` 提出了 `ValueError` （未提供英文原文） `FileNotFoundError`文件存在但损坏或失败时验证 (`agent_profile_store.py:203-207`). 异常随后逃逸 `_profile_to_activate` → `_ensure_active_profile` → `store_errors()`, which maps `ValueError` to **400**. 在头部重复出现，只有一个损坏的 `default.json` 且无活动指针：
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5983#pullrequestreview-5521449970): **APPROVE** 已重新审查过 `213f756`. 我在最后的审查中发现的阻塞问题已解决，并且我与运行中的代码进行了验证，而不是仅仅与差异进行了比较`default` 修复（之前阻塞，现在已解决） `_profile_to_activate` 现在处理一个  `ValueError` 从 `store.load("default")` 并继续激活第一个其他账户，留下不可读的文件未受影响。 我复现了所有四个案例： \| 状态 \| 结果 \|  \|---\|---\|  \| corrupt `default` 另一个头像 \|  `200`, 污染文件字节对齐未受影响， `mine` active \|  \| corrupt `default` alone \|  `200`无活跃的配置文件（同上） `main`) \|  \| 删除损坏的文件 `default`  \|  `200`, fresh `default` 已播种并激活 \|  \| 缺失/悬空指针 \| 与上一个头相同 \| 的 `GET /api/agent-profiles` 400已不存在，所以只剩下单个ba
- [讨论； 评论； ](https://github.com/OpenHands/software-agent-sdk/pull/5983#issuecomment-6172646583)simonrosenberg: 已处理213f75650号审查。 - **Corrupt: `default`: **: `_profile_to_activate`: `default`: 现在，如果一个加载失败的元素被处理，它会被视为缺失的元素，除了它永远不会重新填充。 该文件保持不变，并且第一个其他配置文件被激活。 如果没有其他配置文件，则没有任何活动，并且 `GET /api/agent-profiles` 返回 200 并带有空列表，如 `main` 所示。 两个测试都覆盖了这两种情况，但都在 c67bfe4d4 上失败了。 - **描述：**现在覆盖了这个损坏的 `default`情况，并说 `agent_profile`只有在它是请求的唯一智能体来源时才被拒绝。 与其他来源一样，它会像任何未知字段一样被忽略。 `StartConversationRequest` 不禁止额外的字段，我将其保留原样。

<a id="5589-fixagent-server-stop-startup-tmux-cleanup-killing-live-sibling-sessions"></a>

### ＃5589：fix(agent-server)：停止启动tmux清理杀死实时同级会话

- 提交：`f0206428306db687ac9c8d833ece4fb82b015eba` (2026-10-15T06:32:29-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5589).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5589)。 Families: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34.

陈述意图：

> - 通过 `TmuxTerminal` / `TmuxPanePool` 初始化中的 tmux 用户选项 (`@openhands_socket_owner_pid`) 将创建进程记录为每个套接字的所有者。
> - `_cleanup_stale_tmux_sessions()` 现在仅在其记录的所有者进程消失时才回收 `openhands-<32 hex>` 套接字（重用 `conversation_lease` 中的 `_is_pid_alive`）。 旧版 `openhands` 套接字仍然会被回收，并且没有记录所有者的套接字仍然会被回收。
> - 将 #5485 测试中的断言替换为一个回归测试一个真实存在的兄弟池以及一个孤儿进程外的套接字 `TMUX_TMPDIR`.
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `c1dfd9c52cd3` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -1076,0 +1077 @@
> +模式 AgentLaunchAdditions 属性 llm_profile_ref 可选模式=anyOf=[type="string" minLength=1,type="null"]
> @@ -2090,0 +2092,2 @@
> +模式 LaunchedAgentProfile 属性内联可选模式=type="boolean" 默认=False
> +模式 LaunchedAgentProfile 属性 llm_profile_ref 选项

更改的路径：

- `openhands-agent-server/openhands/agent_server/api.py`
- `openhands-tools/openhands/tools/terminal/constants.py`
- `openhands-tools/openhands/tools/terminal/terminal/tmux_pane_pool.py`
- `openhands-tools/openhands/tools/terminal/terminal/tmux_terminal.py`
- `openhands-tools/pyproject.toml`
- `tests/agent_server/test_api.py`
- `uv.lock`

链接问题接受上下文：

- [#5581](https://github.com/OpenHands/software-agent-sdk/issues/5581)：[缺陷]：智能体服务器启动会终止其他共享同一 `TMUX_TMPDIR` 的对话中仍在运行的终端会话；当前状态为已关闭，关闭时间为 2026-10-15T10:32:31Z。

> - [  ] 与共享的外部供应方共同 `TMUX_TMPDIR` 并且两个并发运行的智能体- 服务器进程，运行中 `_cleanup_stale_tmux_sessions()` (由 [the call made by] 执行的) `api_lifespan()` 在启动时] 会留下其他存活进程的 tmux 运行中的会话及其终端仍然可用。 命令在清理之前开始，之后仍然会输出结果 [  ] 拥有该套接字的端点智能体-服务器进程不再运行，但启动清理仍然回收了它，所以孤儿进程 tmux 服务器/套接字不累积 [  ] 未设置/默认行为 `TMUX_TMPDIR` 端口未变：进程级目录被创建并使用，启动时仍清理该目录中的遗留/过时套接字。 非-POSIX 早期返回路径被保留 [  ] 第 5485 测试 `test_cleanup_stale_tmux_sessions_includes_isolated_sockets` 不再声称拥有 `openhands-<32 hex>` 与活对话相关的套接字被杀死，然后创建一个新的回归测试覆盖了两种结果（保留活的兄弟节点） 使用真实方法清理 owner-gone socket `libtmux.Server` 单个中的处理 `TMUX_TMPDIR`. - [  ] 无公开 Python  API, REST/WebSocket 合同已持久化设置、事件形状或环境变量合同更改； 无需新的配置 [  ] 的智能体-server 测试套件包括新内容回归测试通过，并通过了仓库的格式/检查。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5589#issuecomment-6050660253)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5451441816)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围此更改属于此存储库：它修复了智能体-服务器启动行为 (`openhands-agent-server/openhands/agent_server/api.py`) 和记录套接字所有权的终端工具 (`openhands-tools/.../tmux_terminal.py`、`tmux_pane_pool.py`、`constants.py`)。 无需跨仓库移动或产品决策，也没有公开的Python/REST/WebSocket合同更改（旧的无记录所有者的socket仍然被回收，因此滞留清理意图得以保留）。 问题 #5581 包含 `bug`、`tools`、`agent-execution`、`priority:medium`、`ready-for-dev`。 ## 对头部 `7a102dd` 进行验证 - 重新读取当前 PR 正文、标签、评论和评论线程：没有先前评论或开放线程、头部匹配、PR 开放且非草稿。 - 当前头 CI 是 gre
- [评论； COMMENTED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5470294699): # PR #5589 — 后续审查🟡 **品味评级：可接受** — 小型、适当范围的所有权检查，但所有权的发布与破坏性清理不同步。 **验证头：**`7a102dd4c30d78bca6ca1f08fb505cb125f281f5`（通过GitHubAPI重新检查； 开放，非草稿）。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5589). 审阅了五个更改的文件、受影响的实现和调用者，问题 #5581 和其验收标准，根目录/包 AGENTS.md，以及自定义审查指南。 没有更改仓库代码或远程状态。## 材料发现### P2 — 并发在其所有者被记录之前，启动程序仍可杀死一个活的池 **证据：** [`tmux_pane_pool.py:129–138`]( https://github.com/OpenHands/software-agent-sdk/blob/7a102dd4c30d78bca6ca1f08fb505cb125f281f5/openhands-tools/openhands/tools/ter )
- [评论； COMMENTED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5481595809)：🟡**味道：可以接受——对现有启动竞赛发现的后续研究。**感谢您的集中修复和真实的tmux复制。 正常的初始化同级和孤儿清理证据对于问题的范围复制来说是有用且充分的； 我并不要求将完整的 Canvas 部署作为附加要求。 头部与 [ 10 月 9 日的审查](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5470294699) 保持不变，因此其表现出的 **P2 并发-启动差距 ** 仍然需要解决。 [池初始化](https://github.com/OpenHands/software-agent-sdk/blob/7a102dd4c30d78bca6ca1f08fb505cb125f281f5/openhands-tools/openhands/tools/terminal/terminal/tmux_pane_pool.py#L129-L138)在记录其所有者之前发布一个真实的套接字。 在此期间，[清理]( https://github.com/OpenHa
- [评论； COMMENTED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5503503917): 当之前的评论反映出来时，请重新请求我的审核。_此评论由格雷姆Neubig._代表AI智能体 OpenHands创建
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5508799566)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围此更改属于此存储库：它修复了智能体服务器启动行为 (`openhands-agent-server/openhands/agent_server/api.py`) 以及创建/拥有 tmux 套接字的终端工具 (`openhands-tools/.../tmux_terminal.py`、`tmux_pane_pool.py`、`constants.py`)。 不需要跨存储库移动或产品决策。 链接的问题 #5581 已开放 `bug`、`tools`、`agent-execution`、`priority:medium`、`ready-for-dev`； PR通过`Fixes #5581`引用它。 无公开的Python/REST/WebSocket合约更改（旧的所有者无连接仍然被回收）。## 从上一个主干以来发生了什么变化从`7a102dd`移动到`c4b41b0`。 本次审查了增量：`main` 的合并加上审阅者 @neubig 在上一篇中演示的并发启动差距的修复
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5589#issuecomment-6081321442)：@all-hands-bot 请根据[后续审查和确定性再现](https://github.com/OpenHands/software-agent-sdk/pull/5589#pullrequestreview-5470294699)再看一下这个PR。 new_session → mark_socket_owner 窗口此前被假设为存在，现在在 `7a102dd4c30d78bca6ca1f08fb505cb125f281f5` 头部使用了实际的 tmux 和 SDK 操作：清理操作在进程仍然存活时杀死未标记的套接字，而初始化失败。 请评估剩余的并发启动差距和建议的同步/回归覆盖范围。 这表明修复不完整，而不是新的回归； 普通调度频率未被测量。_此评论由AI 智能体 (OpenHands)代表格雷姆·纽比（@neubig）生成并发布。_
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5589#issuecomment-6146086092)：@all-hands-bot 请修复合并冲突、审核评论和任何失败的内容 CI。
- [讨论评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5589#issuecomment-6147735099)已完成 - 冲突已解决，评论的审查已完成并发-启动查找已修复， CI 是绿色的。## 冲突已合并 `main` 进入分支（合并提交） `c4b41b0`). 唯一的问题在于 `tests/agent_server/test_api.py`, where both `main` 并且这个分支还添加了一个测试在同一个地方 `skipif` 装饰器。 分辨率保持了两者 `main`'s `test_ensure_server_tmux_tmpdir_replaces_too_deep_env` and its `short_tmp_path`/`deep_tmp_path`  测试夹具。 - 这分支的 `test_cleanup_stale_tmux_sessions_spares_live_sibling_socket`. 的 PR 现在 `MERGEABLE` (was) `CONFLICTING`). ## 并发-启动间隙（P2从跟进审查中获得）审查认为，早期的修复不完整：  -启动间隙（P2从后续审查中获得）审查认为，早先的修复不完整： `new_session()` 使套接字可发现，并且所有者选项随后被记录。 在那个窗口，另一个进程的 `_cleanup_stale_tmux_sessi

<a id="6003-fixtask_tracker-accept-common-task-status-names"></a>

### #6003: fix(task_tracker): 接受常见任务状态名称

- 提交：`11d82b2c267ab180e94ebcb668dc3c1cbce28f85` (2026-10-15T06:33:49-05:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/6003).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-6003)。 家庭：F27、F33。

陈述意图：

> - 任务状态在验证之前被标准化：`pending` 和 `to do` 意味着 `todo`，`completed` 和 `complete` 意味着 `done`。
> - 其他值，例如 `blocked` 或 `cancelled`，仍然会被拒绝，并出现相同的错误。
> - 模型显示的模式和保存的任务列表仍然仅使用 `todo`、`in_progress` 和 `done`。

更改的路径：

- `openhands-tools/openhands/tools/task_tracker/definition.py`
- `tests/tools/task_tracker/__init__.py`
- `tests/tools/task_tracker/test_task_tracker_status.py`

链接问题接受上下文：

- [#6005](https://github.com/OpenHands/software-agent-sdk/issues/6005)：task_tracker 拒绝使用常见状态名称（例如待处理 - 当前状态已关闭、已关闭 2026-10-15T11:33:51Z）的任务计划。

> - 规范状态的 [ ] `pending`、`to do`、`completed`、`complete` 以及大小写、空格或连字符变体验证并存储为 `todo`、`in_progress` 或 `done`。 - [ ] 其他值，例如 `blocked`，仍然被拒绝并出现相同的错误。 - [ ] 模型中显示的工具模式未更改。 ###安装方法OpenHands企业版（智能体-服务器镜像）---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/6003#issuecomment-6190148937)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6003#issuecomment-6190155012): @OpenHands /codereview-roasted 准确审查提交 9f72397b8d4565d55323dceac690a5ad000f5d12。 如果 PR 头发生变化，请报告该情况并且不批准另一次提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性、回归覆盖范围以及PR验证主张是否与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 用VERDICT代替CHANGES_REQUESTED，当需要更改时，选择REVIEWED_HEAD: 9f72397b8d4565d55323dceac690a5ad000f5d12 REVIEW_REQUEST: efa980169efa46308a0dda2b7c7bbaf3 VERDICT: APPROVED 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6003#issuecomment-6190296517): @OpenHands /codereview-roasted 准确审查提交 9f72397b8d4565d55323dceac690a5ad000f5d12。 如果 PR 头发生变化，请报告该情况并且不批准另一次提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性、回归覆盖范围以及PR验证主张是否与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 用VERDICT代替CHANGES_REQUESTED，当需要更改时，选择一个裁决：REVIEWED_HEAD：9f72397b8d4565d55323dceac690a5ad000f5d12 REVIEW_REQUEST：cc68040232ef4ea0953332d25a5079c7 VERDICT：APPROVED 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6003#issuecomment-6190579552): ## 评论 commit 9f72397b8d4565d55323dceac690a5ad000f5d12 ** 感官：很好。** 小而专注，正确的变化。### 验证了什么 - 头部 `9f72397b8d4565d55323dceac690a5ad000f5d12` 匹配了请求的审查目标； 基础是`f020642`（主要）。 已更改文件：`openhands-tools/openhands/tools/task_tracker/definition.py`（增加20个，减少2个），新文件`tests/tools/task_tracker/test_task_tracker_status.py`，以及一个空文件`tests/tools/task_tracker/__init__.py`。- `mode="before"` 验证器正常化（strip -> 小写 -> `-`/space -> `_`），首先匹配可唯一值，然后是别名映射(`pending`/`to_do` -> `todo`）。 `completed`/`complete` -> `done`). 未知字符串通过，因此 Pydantic 仍然会引发相同的 ValidationError。 本地验证：`To Do`、`TODO`、`to-do`、`Pending`、`In-Progress`、` in progress `、`DONE`、`complete` 全部也不
- [讨论； 评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6003#issuecomment-6190618574)：在请求的头 9f72397b8d4565d55323dceac690a5ad000f5d12 处审查了 PR #6003“fix(task_tracker)：接受常见任务状态名称”并发布了实质性审查。 **已发布审查：**  https://github.com/OpenHands/software-agent-sdk/pull/6003#issuecomment-6190579552  **结论：APPROVED** 发现摘要：- 已确认 PR 的最新提交与审查请求完全一致（9f72397...，基准为 f020642）； 如果头发生变化，需要重新审查。- 正确性：`mode="before"` 验证器正常化 strip/lowercase/`-`/space→`_`，首先匹配 canonical Literal 值，然后是 aliases (`pending`/`to_do`→`todo`, `completed`/`complete`→`done`))。 未知值通过，因此 Pydantic 仍然拒绝 `blocked`、`cancelled`、`""`，并出现相同的错误。 本地验证了所有边缘情况。 没有模式更改到达模型或持久/发出的任务（canoni

<a id="5990-fixplugin-load-plugins-whose-root-pluginjson-has-no-schema-with-the-claude-code-layout"></a>

### ＃5990：fix(plugin)：使用克劳德代码布局加载根plugin.json没有$模式的插件

- 提交：`8ad5845e46fc8984fb90b1b44e583c1b5c29cd0a` (2026-10-15T07:52:02-05:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5990).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5990)。 家庭：F09、F26。

陈述意图：

> - 仅当根 `plugin.json` 声明 `$schema` 时，或者当它不可读或不是 JSON 对象时，才会选择智能体插件格式。 损坏或不受支持的智能体插件清单仍会被声明和拒绝，因此它永远不会在目录名称下静默加载。
> - 没有 `$schema` 的根 `plugin.json` 会进入 Claude Code 布局，该布局会加载插件的 `skills/` 目录。

更改的路径：

- `openhands-sdk/openhands/sdk/plugin/format/agent_plugins.py`
- `tests/sdk/plugin/test_agent_plugins_format.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5990#issuecomment-6177762963)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/5990#issuecomment-6177714852): @OpenHands /codereview-roasted 准确审查提交 9804021b4b4fb8e1d4a5c1d72751531ed7e58a20。 如果 PR 头发生变化，请报告该情况并且不批准另一次提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性、回归覆盖范围以及PR验证主张是否与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 用VERDICT代替CHANGES_REQUESTED，当需要更改时，选择以下简洁的陈述（没有代码框）：REVIEWED_HEAD：9804021b4b4fb8e1d4a5c1d72751531ed7e58a20 REVIEW_REQUEST：e1bde915c72a45de9919e9dc0804d93e VERDICT：APPROVED 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论； 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/5990#issuecomment-6177943169)：**审核目标**：`9804021b4b4fb8e1d4a5c1d72751531ed7e58a20`（头部不变，PR开放，可合并）。 基础`75105bd4`（主要）。 没有事先的人工审查或未解决线程。 **更改的作用**：`AgentPluginsFormat.detect()`现在读取根`plugin.json`，而不是仅将存在视为声明。 当清单不可读、无效JSON、非对象或包含`$schema`密钥的对象时，清单将被声明（随后被`load_manifest()`拒绝）； 有效的JSON对象**没有**`$schema`落入克劳德代码布局。 **正确性**（通过`detect_format` → `PluginFormat.load` → `Plugin.load`追踪到）：- 供应商的智能体插件模式已关闭，*需要* `$schema`（`test_schema_is_closed`断言`set(schema["required"]) == {"$schema", "name"}`）。 因此，没有 `$schema` 的根 `plugin.json` 不能是一个文件
- [讨论评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/5990#issuecomment-6177977214)评论已完成。 我审查了确切的提交 `9804021b4b4fb8e1d4a5c1d72751531ed7e58a20` (内容保持不变)，并发布了一篇实质性评论作为评论 PR #5990 (未推送代码，未合并，根据仅审查指令)。## 结果： APPROVED  **发布评论**:  https://github.com/OpenHands/software-agent-sdk/pull/5990#issuecomment-6177943169  我已经验证了什么 **目标/上下文**: PR  `OpenHands/software-agent-sdk#5990` — head `9804021b…` 与请求的审查提交相关 `75105bd4` (main)，可打开和合并。 没有先前的人类审查或未解决的问题线程。 修复了一个 `.NET skills` 16个市场 GitHub-Copilot-style plugins (root) `plugin.json` without `$schema`所有都未能加载智能体插件检测器。 **正确性** (traced `detect_format` → `PluginFormat.load` → `Claude Code fallback`- 供应商的智能体

<a id="5984-refactoragent-profiles-deprecate-the-legacy-profile-resolver"></a>

### ＃5984：refactor(agent-profiles)：弃用旧配置文件解析器

- 提交：`b187e88eb018ef9f5d10af2a66043d566873d412` (2026-10-15T14:59:40+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5984).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5984)。 家庭：F21。

陈述意图：

> - 两个功能都是`@deprecated(deprecated_in="1.55.0", removed_in="1.60.0")`。 这就是 5 短跑道 `check_deprecations.py` 所需要的。
> - 每个弃用指定其替代品：`openhands.sdk.launch.resolve` 代表第一个，`openhands.sdk.launch.preview_launch` 代表试运行。
> - 没有行为改变。 模块文档字符串现在说明该模块的用途并指出替换项。

更改的路径：

- `openhands-sdk/openhands/sdk/profiles/resolver.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5984#issuecomment-6167608992)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5984#pullrequestreview-5519317991)：已批准 - 可以安全合并。 **为什么这是安全的：** - 纯附加注释：`resolve_agent_profile()` 和 `resolve_agent_profile_dry_run()` 得到 `@deprecated(deprecated_in="1.55.0", removed_in="1.60.0")` 加上文档字符串更新。 没有任何行为变化。- 5分钟小版本跑道满足`check_deprecations.py`，弃用检查流程为绿色。- 每个弃用都为其替换项命名(`launch.resolve` / `launch.preview_launch`)。 仅当包达到 1.55.0 时才会启动警告，与现有的弃用项匹配。 - 仅更改了一个文件，并且所有 CI 均为绿色。 没有发现阻塞问题。 _此评论由 AI 智能体 (OpenHands) 代表 user._ 生成

<a id="6007-release-v1550"></a>

### #6007：发布 v1.55.0

- 提交：`fd387b58dc7b707b73c159845c0396a17000be24` (2026-10-15T15:43:14+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/6007).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-6007)。 Families: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34.

陈述意图：

> ## 发布 v1.55.0
> 
> 此 PR 准备版本 **1.55.0** 的发布。
> 
> **开始者：** @simonrosenberg
> 
> ### 发布清单
> - [x] 版本设置为 1.55.0
> - [ ] 修复任何弃用截止日期（如果存在）
> - [ ] 集成测试通过（标记为 `integration-test`）
> - [ ] 行为测试通过（标记为 `behavior-test`）
> - [ ] 示例测试通过（标记为 `test-examples`）
> - [ ] 安全扫描通行证（标有 `security-scan`）
> - [ ] 确认任何 `release-note-required` PR 在决赛发布说明中被准确叫出
> 
> ### 合并时会发生什么
> 合并此 PR 时，`create-release.yml` 工作流程将自动：
> 1. 使用标签 `v1.55.0` 和自动生成的注释创建 GitHub 版本，以及合并 `release-note-required` PR 的显式序言
> 2. 针对标记 `v1.55.0` 显式调度 PyPI、npm、GitHub 包、智能体服务器映像和二进制发布者
> 3. 成功发布 PyPI 后触发 `version-bump-prs.yml`
> 
> 
> ---
> <details>
> <summary><b>🐳 Agent Server 此 PR</b> — GHCR 包的图像、拉取/运行命令和所有推送的标签（单击展开）<

更改的路径：

- `clients/typescript/package-lock.json`
- `clients/typescript/package.json`
- `clients/typescript/src/generated/agent-server-schema.ts`
- `openhands-agent-server/pyproject.toml`
- `openhands-sdk/pyproject.toml`
- `openhands-tools/pyproject.toml`
- `openhands-workspace/pyproject.toml`
- `uv.lock`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/6007#issuecomment-6192706254)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6007#issuecomment-6192706163)：## 🔒 发布安全扫描 ### 🔒 批准漂移（检查时间与使用时间） **❌ 8 finding(s)** 基线：`v1.54.0` — 54 合并 PR(s)在范围内。 > ⚠️ 范围内的 1 个第一父级 commit(s) 与 `(#N)` 压缩约定不匹配，并且经过 **not** 审核（合并/变基合并，或丢失的 `(#N)` 后缀）。 这些是盲点 - 检查它们： > - 发布 v1.55.0 \| PR \| 查找 \| 详细信息 \| \| -- \| ------- \| ------ \| \| #5924 \| `changed-after-approval` \| 最后一次由 @all-hands-bot 批准是在 fc6ebe323 上，但合并头是 [c3f2a8e96](https://github.com/OpenHands/software-agent-sdk/compare/fc6ebe32334bfe312921dbeb275fa92ab058ea7e...c3f2a8e96b7e3f9522436dab6c940d09e91f1c8c) — 审查后提交落地 \| \| #5986 \| `changed-after-approval` \| 最后由 @hieptl 批准是在 f79cf5050 上，但合并头是 [9aae234e0]( https://github.com
- [讨论； 评论； simonrosenberg](https://github.com/OpenHands/software-agent-sdk/pull/6007#issuecomment-6192778926)：**安全扫描的批准漂移审查。**所有 8 项发现均为良性。 我检查了每个最后批准后落地的内容。 \| PR \| 经批准 \| 判决 \| \|---\|---\|---\| \| #5747, #4960, #5744, #5520, #5621 \| 只有“移除 PR-仅有的残留物”自动提交。 `.pr/` \| 每个更改的文件都是 \| \| #5657 \| 一次合并 `main`。 `git show --remerge-diff` 为空，因此无需手动解析 \| 良性 \| \| #5924 \| `main` 的一次合并； 它的唯一冲突出现在`.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`，通过保留双方更新的子弹\|，文档只保留\| \| #5986 \|。一个编辑`normalize_git_url` 文档字符串的提交，+6/-2 \|，保留文档字符串 \|。唯一一个未经审核的第一个父提交是这个PR的“发布v1.55.0”版本更新。 其他检查 o
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6007#issuecomment-6192793834): # 🧪 集成测试结果 **总体成功率**: 97.9% **总成本**: $2.09 **测试模型**: 5 **时间戳**: 2026-10-15 13:07:00 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38739279281) - **litellm_proxy_deepseek_deepseek_v4.1_flash**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38739279281) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38739279281) - **litellm_proxy_anth
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6007#issuecomment-6193134479): # 🧪 行为测试结果 **总体成功率**: 96.0% **总成本**: $17.42 **测试模型**: 5 **时间戳**: 2026-10-15 13:23:47 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38739279518) - **litellm_proxy_deepseek_deepseek_v4.1_flash**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38739279518) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38739279518) - **litellm_proxy_anthro

<a id="5991-fixagent-server-drop-pips-vendored-pkg_resources"></a>

### ＃5991：fix(agent-server)：放弃pip的供应商pkg_resources

- 提交：`f5f849f5ab51502cdfff97870f29de95307882a4` (2026-10-15T09:15:51-05:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5991).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5991)。 家庭：F01、F12、F16、F31。

陈述意图：

> - `pip-revendored`阶段从pip的`vendor.txt`中删除`setuptools==70.3.0`，并在`vendoring sync`之前删除pip的`pkg_resources.patch`。 重建的 pip 及其 `bom.cdx.json` 不包含 setuptools。
> - 退休守卫还检查上游 pip 是否仍然捆绑 `pkg_resources`。 它要求仅在上游修复了 urllib3 和 msgpack 后才删除该阶段。

更改的路径：

- `openhands-agent-server/openhands/agent_server/docker/Dockerfile`
- `tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5991#issuecomment-6178654295)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5991#pullrequestreview-5525511555)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评估已批准。 更改已正确针对此仓库（该仓库拥有该智能体-服务器Docker镜像）进行（该问题#5988，现已关闭），完全匹配。 **头部的作用** - `pip-revendored`从pip的`_vendor/vendor.txt`中删除`setuptools==70.3.0`，断言`setuptools==`行不存在，并在`vendoring sync`之前删除`tools/vendoring/patches/pkg_resources.patch`。 重建的轮子及其`bom.cdx.json`中没有setuptools，因此CVE-2025-47273和CVE-2026-59890从打包的`-python`/`-python-slim`镜像中消失。 - 退休守卫现在还会探查`pkg_resources`上游，并记录预期的退休条件（上游会删除`pkg_resources`、**和**修复urllib3/msgpack）。 **在c35c32cd上进行的验证** - Pulle

<a id="5753-fixsdk-list-changes-of-a-repository-below-a-non-repository-path"></a>

### ＃5753：fix(sdk)：列出非存储库路径下存储库的更改

- 提交：`d5995133d9425e6a37756b28ae19543b5d85306d` (2026-10-15T21:47:40+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5753).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5753)。 家庭：F15。

陈述意图：

> `get_git_changes` (`openhands-sdk/openhands/sdk/git/git_changes.py`): 当请求的目录不是仓库，而是位于其下方一级的仓库时，从不基础更改开始列出它们（按路径排序，如之前）。 无论目录本身还是其下面的任何目录都不是有效的仓库，那么原始的`GitRepositoryError`仍然被抛出，所以Agent Server仍然回答`200 []`和`LocalWorkspace.git_changes`仍然抛出。 本身就是存储库的路径是不变的。
> - 测试：对布局（前缀路径和状态）和普通目录的 SDK 测试，其仅下面的 `.git` 被破坏（仍然引发）； 使用真实 git 进行全局路由的智能体-服务器路由器测试。
> - 验证-智能体-服务器地图：`F15.changes-repo-below-path` 丢失其 `# bug` 标记和“已知错误”标签； 散文和两个陷阱现在描述了固定的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`
- `openhands-sdk/openhands/sdk/git/git_changes.py`
- `tests/agent_server/test_git_router.py`
- `tests/sdk/git/test_git_changes.py`

链接问题接受上下文：

- [#5641](https://github.com/OpenHands/software-agent-sdk/issues/5641): [Bug]: GET  /api/git/changes 返回 [] 对于一个包含仓库的非仓库目录，而不是其更改 — 当前状态关闭，关闭于2026-10-15T19:47:42Z。

> - [ ] `GET /api/git/changes`（全局和会话范围内的）在非仓库目录中，该目录包含一个仓库列表，该列表的更改按路径排序，以目录名称开头。- [ ]（没有仓库的目录）仍然返回 `200 []`。 a `path` 本身就是一个存储库，没有改变。 - [ ] `tests/sdk/git/test_git_changes.py` 覆盖此布局上的 `get_git_changes`。 - [ ] 地图项目符号 `F15.changes-repo-below-path` 通过，其 `# bug` 标记被删除。 ### 检查 main 的安装方法 uv 同步 ### 版本 main 位于 2804c12 ### 其他上下文根本原因，在 `openhands-sdk/openhands/sdk/git/git_changes.py` 中： - `get_git_changes`（第 218 行）使用 `glob("./*/.git")`（第 219-222 行）查找嵌套存储库，然后首先在请求的目录上调用 `get_changes_in_repo(cwd, ref=ref)`（第 225 行）。 - `get_changes_in_repo` 以 `validate_git_repository` 开头（第 171 行），这会为非存储库目录（`openhands-sdk/openhands/sdk/git/utils.py:518`）引发 `GitRepositoryError`，因此 `get_git_changes` 在嵌套存储库循环之前退出（第 239 行）。 - `_get_git_changes` (`openhands-agent-server/openhands/agent_server/git_router.py:65-69`) 将其映射到 `[]`。 `LocalWorkspace.git_changes` (`openhands-sdk/openhands/sdk/workspace/local.py:185`) 提出了它。 `_resolve_git_repo_root` (`openhands-agent-server/openhands/agent_server/file_router.py:285`) 已经处理了 `GET /api/file/archive` 的这种布局。 建议的修复（导入 `GitRepositoryError`）：如果基础不是存储库但找到了嵌套存储库，则 st

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5753#issuecomment-6154867283)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5753#pullrequestreview-5510053219)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## PR #5753 的评论（头 `758f9ea`）**范围。**该更改属于此存储库：它修复了 SDK (`openhands-sdk/openhands/sdk/git/git_changes.py`) 中支持规范智能体-服务器 REST API `GET /api/git/changes`（全局和会话范围）的后端行为。 根据 `AGENTS.md` 跨存储库边界，它是正确的所有者。 链接问题#5641 是`ready-for-dev`（`bug`、`priority:low`）。 **更改。** `get_git_changes`现在容忍了一个请求的目录，该目录本身不是仓库，当在它下面有一个或多个仓库时：它从一个空的基更改列表开始，按目录名列出每个嵌套仓库的更改，并按路径排序。 当目录或任何董事都没有时，原始`GitRepositoryError`被重新提出
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5753#pullrequestreview-5510069892)_这篇评论是由AI发布的智能体 (OpenHands)._ fix(sdk)列出在非仓库路径下的仓库更改。                                                                                                     SDK/Agent Server git 端点，且更改仅限于  SDK git 列表、测试和验证智能体服务器功能图。 无产品或架构决策是必要的。 已验证头节点 `758f9ea6`- The `{base}/{repo}` 现在，布局将以下方框中的仓库列表在非仓库基线之下 `proj/README.md` (UPDATED) + `proj/notes.txt` (ADDED按照路径排序。 在实际的 git 上复制的工作区，以及一个明确的  `ref=HEAD`. - The `GitRepositoryError` 合同保留用于无仓库情况：一个普通目录引发，而只有一个目录的目录引发 `.git` 以下部分已损坏（a） `.git` 该文件指向无处不在)也会引发，因此路由器

<a id="5696-fixagent-server-resolve-trajectory-download-dir-from-request-config"></a>

### ＃5696：fix(agent-server)：从请求配置中解析轨迹下载目录

- 提交：`cb266703c5c797f10f17eea8fea61a25ad2eac30` (2026-10-15T23:13:23Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5696).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5696)。 家庭：F14。

陈述意图：

> - `download_trajectory` 现在解析来自 `request.app.state.config` 的对话目录，`dependencies.py`、`tool_router.py` 和 `server_details_router.py` 已使用请求时配置模式。
> - 现有的轨迹测试安装请求时配置，而不是修补模块级查找。
> - 回归测试驱动了一个完整的延迟初始化的实现实例：启动时使用 `deferred_init=True`, `POST /api/init` 带有非默认的 `conversations_path`创建一个对话，然后下载其轨迹通过两者 `/api/file/download-trajectory/{id}` 和 `/api/conversations/{id}/file/download-trajectory/{id}` (等效的 zip 文件，两者都以 404 错误返回) `Conversation not found` 当在解析后的配置中找不到目录时，且没有 `.zip` 下载后的残留物。

更改的路径：

- `openhands-agent-server/openhands/agent_server/file_router.py`
- `tests/agent_server/test_file_router.py`

链接问题接受上下文：

- [#5640](https://github.com/OpenHands/software-agent-sdk/issues/5640): [Bug]: download-trajectory 返回 404 POST /api/init 设置 conversations_path (预期 200 zip) — 当前状态已关闭，关闭于 2026-10-15T23:13:25Z。

> - [ ] 在 `POST /api/init` 设置 `conversations_path` 之后，全局和范围轨迹路由返回 200，其中存储了会话的 zip。 - [ ] 回归测试涵盖了使用非默认 `conversations_path` 初始化的 deferred-init 应用程序上的两条路由。 - [ ] `F14.trajectory-init-path` 地图子弹通过并且其已知错误标记 (`# bug`) 被删除。 ### 安装方法 uv 同步在 main 的签出中 ### Version main at 2804c12 ### 附加上下文根本原因：`download_trajectory` 读取启动时默认配置，而不是应用程序的当前配置。 路径位于`openhands-agent-server/openhands/agent_server/`下。 - `file_router.py:922`：`config = get_default_config()`； 从第923行到第930行，`<conversations_path>/<hex>`构建了它，然后返回了404。 - `config.py:540-546`: `get_default_config()`在启动时加载了环境/文件中的模块单例。 - `init_router.py:175-176`将初始化时的`conversations_path`合并到一个新的`Config`中，并仅`init_router.py:264`安装它为`app.state.config`。 单例保持启动时的值（默认 `workspace/conversations`）。 - `runtime_router.py:85` 通过 `file_router` 下载 `/conversations/{runtime_conversation_id}`，因此命名路由运行相同的端点并以相同的方式失败。 - 其他路由器从请求读取活的配置：`dependencies.py:35`，`tool_router.py:53`，`server_details_router.py:152`。 建议的修复：给`download_trajectory`一个`request: Request`参数并读取`request.app.state.config`而不是调用`get_default_config()`。 ---

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; enyst](https://github.com/OpenHands/software-agent-sdk/pull/5696#pullrequestreview-5540778904)：_食品法典委员会对@enyst._进行人工智能辅助审查审查`0b509ab4`：没有实质性发现。 两条轨迹路线现在都使用初始化的应用程序配置，并保留 REST/OpenAPI 形状。 通过 macOS/Python 3.13.11 上独立的 CLI 启动的服务器进行验证，无需模型调用。 在精确的基础上 `1cfba211`，deferred-init 工作流程再现了两次：对话 GET 返回 200，但两条轨迹路线都返回 404。 在这一点上，同样的工作流程被重复两次：两个路由都返回了200状态码，并且包含了匹配的ZIP内容、已持久化状态和事件文件，LLM和已脱敏键被重复使用，重复下载没有留下任何临时ZIP。 丢失的对话仍然返回 404。 所有 123 个文件路由器、初始化路由器和 OpenAPI 测试均已通过。 对此头的上游检查是元数据检查； 上面的运行时比较和重点测试
- [评论； APPROVED; 恩斯特](https://github.com/OpenHands/software-agent-sdk/pull/5696#pullrequestreview-5540981245)：谢谢！
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5696#pullrequestreview-5544090606)：_此评论由 AI 智能体 (OpenHands) 发布。_ 评论了确切的头 `bdda5799`（仍然是 PR 头； 更改与链接问题的建议修复相匹配）。 范围门通过：这是拥有Agent Server文件/轨迹路线的仓库。 **检查的内容**`openhands-agent-server/openhands/agent_server/file_router.py:938`现在显示为`config: Config = request.app.state.config`，这是配置`POST /api/init`安装的(`init_router.py:281`)。 平面路由 `/api/file/download-trajectory/{id}` 和 `runtime_router.py` 中安装的会话范围别名都运行相同的端点，因此两者都是固定的。 这与`dependencies.py`、`tool_router.py`和`server_details_router.py`已经使用的请求时配置模式匹配； REST/OpenAPI 形状不变（`Request` 不是已序列化参数），并且 migrat
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5696#discussion_r4291752534)：此`POST /api/init`不发送`X-Init-API-Key`标头，并且在其上方创建的`Config`没有`secret_key`。 `Config.secret_key` 默认通过 `_default_secret_key()`，从周围环境读取 `SESSION_API_KEY` / `OH_SESSION_API_KEYS_0`。 当导出任一变量时，初始化门 (`check_init_api_key`) 需要匹配的 `X-Init-API-Key`，因此此请求返回 401，并且测试在下一个 `assert response.status_code == 200` 处失败。 在此头重现：设置`OH_SESSION_API_KEYS_0`后，此测试失败（`/api/init`断言处为401）； 与`env -u OH_SESSION_API_KEYS_0`它通过（11通过）。 `tests/agent_server/test_init_router.py` 已经通过其自动使用 `_clean_env` 测试夹具隔离了它，删除了 `SESSION_API_KEY`、`OH_SESSION_API_KEYS_0` 和 `OH_SECRET_KEY`； 该模块没有这样的

<a id="5987-featplugin-add-strict-plugin-fetch-preflight"></a>

### ＃5987：feat(plugin)：添加严格的插件获取预检

- 提交：`db9c54b71c8c9ed46a2454fc65eee804d3c1e8aa` (2026-10-15T21:25:01-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5987).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5987)。 家庭：F09、F21、F26、F30。

陈述意图：

> - 添加了 `preflight_plugin(...)`、`PluginSourceError` 和 `CheckedPlugin` 到 `openhands.sdk.plugin`，并进行了严格机密扩展、结构化错误代码、临时检查点清理和原始元数据（如 manifest、skills 和 commands）。
> - 通过现有的 `/plugins` 路由器添加了 `POST /api/plugins/fetch`，以获取插件并将其固定到不可变的提交-SHA 缓存路径中，而无需安装或启用它。
> - 添加了对 `fetch_plugin_with_resolution(...)` 的 pinned-cache 重用，当严格解析器已经将 SHA 的提交材料化时。并修正插件错误措辞，使得 URL 类似 `extensions-private` 的文本不会被重写。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `1a0fd91ad03d` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -149,0 +150 @@
> +运算POST/api/plugins/fetchoperationId=fetch_plugin_endpoint_api_plugins_fetch_post
> @@ -408,0 +410 @@
> +requestBody POST /api/plugins/fetch 需要 application/json=True 模式=FetchPluginRequest
> @@ -756,0 +759,4 @@
> +响应 POST /api/plugins/fetch 200 应用程序/json 模式=FetchPluginRespon

更改的路径：

- `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`
- `openhands-agent-server/openhands/agent_server/plugins_router.py`
- `openhands-agent-server/openhands/agent_server/plugins_service.py`
- `openhands-sdk/openhands/sdk/plugin/__init__.py`
- `openhands-sdk/openhands/sdk/plugin/fetch.py`
- `openhands-sdk/openhands/sdk/plugin/paths.py`
- `openhands-sdk/openhands/sdk/plugin/strict_fetch.py`
- `openhands-sdk/openhands/sdk/profiles/__init__.py`
- `openhands-sdk/openhands/sdk/profiles/agent_profile.py`
- `tests/agent_server/test_plugins_router.py`
- `tests/sdk/plugin/test_plugin_strict_fetch.py`
- `tests/sdk/profiles/test_agent_profile.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5987#issuecomment-6171132400)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5987#pullrequestreview-5527194299)：_此评论由 AI 智能体 (OpenHands) 发布。_ 已评论头 `10e032d86363a5ced83270dc0a7aa81564e31959`（`main` <- `feat/strict-plugin-fetch`, +882/-1). Focused tests pass locally (`uv run pytest tests/sdk/plugin/test_plugin_strict_fetch.py tests/agent_server/test_plugins_router.py -q` -> 16 通过）。 链接的问题 #5748 已打开，仅带有 `enhancement` 标签； `Validate PR description` 检查失败，因为 #5748 既不包含 `ready-for-dev` 也不包含预发布创建日期。 严格解析器是一个好补充，锁定缓存路径是正确的，但新的`POST /api/plugins/fetch`、端点和`preflight_plugin()`不满足该问题指出的相同输入的错误合同和机密处理要求。 内联附有两个已证实的发现：1。 不可解析的 `source`（在 `${VAR}` 扩展之后）
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5987#pullrequestreview-5527490418)_这篇评论是由AI发布的智能体 (OpenHands_). 重新审查的头部 `97845e0d628a514252fc08765d97f301949fc3a7` (`fix(plugin): sanitize strict fetch failures`），自上次审核以来发生了变化。 该审查的两项发现都在这一点上得到了解决和验证：1。 `parse_extension_source` 现在被包裹并映射 `ExtensionFetchError` to `PluginSourceError("invalid_source", ...)` 与 `from None`. 我重现了之前的失败。 `POST /plugins/fetch` 与 `not-a-real-source`, `github:oops`, 或 `ftp://...` 现在返回 `422` 与 `{"code":"invalid_source","message":"Invalid plugin source."}` instead of `500`, and a `source="${TOKEN}"` with a `StaticSecret` 返回缺少体中扩展值的结构化错误。 `preflight_plugin` likewise raises `PluginSourceError(code="invalid_source")`. 2. `_store_pinned_c
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5987#discussion_r4278290353): `parse_extension_source` 提出了 `ExtensionFetchError` 对于源来说，它无法分类（e.g. `github:oops`, 一个裸露的相对路径，或一个 `ftp://`  URL). 这里没有任何东西将它转换成 `PluginSourceError`因此，出现了两个失败：- 路由器只捕获了 `PluginSourceError`, so `POST /api/plugins/fetch` 返回 `500 Internal Server Error` 对于这些输入，而不是文档中所述的 `422` 带有结构化的 `{code, message}` 问题的关键在于智能体服务器未处理的异常处理器返回 `str(exc)` 在响应中 `exception` field. 当源是未展开到无法解析的 `${VAR}` (e.g. `source="${PLUGIN_TOKEN}"` with a `StaticSecret`), 扩展的机密值被回显到  HTTP body. 请输出简体中文译文。 `status 500`, body `{"detail":"Internal Server Error","exception":"Unable to parse extension source:
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5987#discussion_r4278290359): `_store_pinned_checkout` 复制整个获取的结账，包括 `.git`。 `_run_git(["remote", "add", "origin", url], ...)` 已经将凭据-标记的 URL 写入 `.git/config`，因此在 `~/.openhands/cache/plugins/<repo>-<hash>/resolved-refs/<sha>` 的不可变固定缓存中，保留了 token 的扩展版本，直到缓存存在。 用`fetch_plugin_strict(source="file://x-access-token:SUPERSECRET@<repo>", ...)`对此头进行验证：缓存的`.git/config`包含`url = file://x-access-token:SUPERSECRET@/...`。 预飞行路径避免了这一点，因为临时检查点被删除了，但端点路径（即问题说在自动化启动脚本中运行的路径）会持久化凭据。 获取后擦洗远程 URL (e.g. `git remote set-url origin <redacted>` 或
- [review_comments; 评论； malhotra5](https://github.com/OpenHands/software-agent-sdk/pull/5987#discussion_r4278385138)：已在 97845e0 中修复：严格获取现在在机密扩展后从 parse_extension_source 捕获 ExtensionFetchError，并将其映射到 PluginSourceError（code="invalid_source"），并使用通用消息且没有异常原因，因此 /plugins/fetch 返回结构化 422 正文，而不回显扩展的机密值。 为机密扩展案例添加了 SDK 和端点回归测试。 该回复由 AI 智能体 (OpenHands) 代表用户创建。
- [review_comments; 评论； malhotra5](https://github.com/OpenHands/software-agent-sdk/pull/5987#discussion_r4278385269)已修复 97845e0：已禁用 .git 信息的插件缓存副本，防止凭据-携带原点 URLs 从已持久化在缓存的检查点。 添加了一个回归测试带有 fetch 的凭据-携带文件 URL重用缓存，并断言缓存的 artifact 没有 .git 信息或展开机密 value. 这封回复是由一个AI创建的智能体 (OpenHands代表用户。
- [review_comments; 评论； malhotra5](https://github.com/OpenHands/software-agent-sdk/pull/5987#discussion_r4278795381)：注意：之前尝试使用 Pydantic 内置类型 `JsonValue`，但为 OpenAPI 检查生成了一个空对象模式
- [review_comments; 评论； malhotra5](https://github.com/OpenHands/software-agent-sdk/pull/5987#discussion_r4289656187)：已确认。 我保持插件 JSON 载荷模式显式，而不是切换到 Pydantic 的 JsonValue，因此 OpenAPI 输出避免了此处提到的空对象模式行为。 该回复由 AI 智能体 (OpenHands) 代表用户创建。

<a id="6021-release-v1551"></a>

### #6021：发布 v1.55.1

- 提交：`5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2` (2026-10-15T21:58:41-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/6021).
- 意图：记录。 运行时：**带有功能限制的族扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-6021)。 Families: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34.

陈述意图：

> ## 发布 v1.55.1
> 
> 此 PR 准备版本 **1.55.1** 的发布。
> 
> **开始者：** @malhotra5
> 
> ### 发布清单
> - [x] 版本设置为 1.55.1
> - [ ] 修复任何弃用截止日期（如果存在）
> - [ ] 集成测试通过（标记为 `integration-test`）
> - [ ] 行为测试通过（标记为 `behavior-test`）
> - [ ] 示例测试通过（标记为 `test-examples`）
> - [ ] 安全扫描通行证（标有 `security-scan`）
> - [ ] 确认任何 `release-note-required` PR 在决赛发布说明中被准确叫出
> 
> ### 合并时会发生什么
> 合并此 PR 时，`create-release.yml` 工作流程将自动：
> 1. 使用标签 `v1.55.1` 和自动生成的注释创建 GitHub 版本，以及合并 `release-note-required` PR 的显式序言
> 2. 针对标记 `v1.55.1` 显式调度 PyPI、npm、GitHub 包、智能体服务器映像和二进制发布者
> 3. 成功发布 PyPI 后触发 `version-bump-prs.yml`
> 
> 
> ---
> <details>
> <summary><b>🐳 Agent Server 此 PR</b> — GHCR 包的图像、拉取/运行命令和所有推送的标签（单击展开）</summ

更改的路径：

- `clients/typescript/package-lock.json`
- `clients/typescript/package.json`
- `clients/typescript/src/generated/agent-server-schema.ts`
- `openhands-agent-server/pyproject.toml`
- `openhands-sdk/pyproject.toml`
- `openhands-tools/pyproject.toml`
- `openhands-workspace/pyproject.toml`
- `uv.lock`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/6021#issuecomment-6205928690)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6021#issuecomment-6205922881): ## 🔒 发布安全扫描 ### 🔒 批准漂移（检查时间与使用时间） **❌ 1 finding(s)** 基线：`v1.55.0` — 4 合并 PR(s)范围。 > ⚠️ 范围内的 1 个第一父级 commit(s) 与 `(#N)` 压缩约定不匹配，并且经过 **not** 审核（合并/变基合并，或丢失的 `(#N)` 后缀）。 这些是盲点 - 检查它们： > - 发布 v1.55.1 \| PR \| 查找 \| 详细信息 \| \| -- \| ------- \| ------ \| \| #5987 \| `changed-after-approval` \| 最后一次由 @all-hands-bot 批准是在 97845e0d6，但合并头是 [906430917](https://github.com/OpenHands/software-agent-sdk/compare/97845e0d628a514252fc08765d97f301949fc3a7...906430917242d7f6cb015c6413c6595b61945943) — 审查后提交的 \| 已审计 4 PR(s)：3 个干净，1 个标记，0不可审计。 ### 📦 供应链依赖性差异 **✅ 没有发现** 基线：`v1.55.0` 添加：*
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6021#issuecomment-6206026216): # 🧪 集成测试结果 **总体成功率**: 97.9% **总成本**: $2.17 **测试模型**: 5 **时间戳**: 2026-10-16 01:35:55 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38835162050) - **litellm_proxy_deepseek_deepseek_v4.1_flash**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38835162050) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38835162050) - **litellm_proxy_anth
- [讨论； 评论； GitHub-actions[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6021#issuecomment-6206037294): # 🧪 行为测试结果 **总体成功率**: 96.0% **总成本**: $10.25 **测试模型**: 5 **时间戳**: 2026-10-16 01:36:54 UTC <details> <summary>📁 详细日志和工件</summary> 单击下面的链接可访问详细的代理/LLM 日志，显示每个模型的完整推理过程。 在 GitHub 操作页面上，向下滚动到“工件”部分以下载日志。 - **litellm_proxy_openai_gpt_5.5**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38835162222) - **litellm_proxy_deepseek_deepseek_v4.1_flash**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38835162222) - **litellm_proxy_gemini_3.1_pro_preview**: [📥 查看和下载日志](https://github.com/OpenHands/software-agent-sdk/actions/runs/38835162222) - **litellm_proxy_anthro

<a id="5998-ci-defer-pr-artifact-cleanup-until-after-merge"></a>

### ＃5998：CI：将PR工件清理推迟到合并后

- 提交：`12e967664c2353f4cb85dd27da04ade035ff078c` (2026-10-16T09:13:44+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5998).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-5998)。 系列：无需产品运行时间。

陈述意图：

> - 删除审批清理并在合并后使用现有的清理 PR，从 `main` 中删除相同存储库和分支 PR 的 `.pr/`。
> - 更新工件通知、贡献者说明、PR 模板和设计文档指南，以描述合并到 `main` 后的自动删除。
> - 仅使已提交树包含根 `.pr` 条目的 `rel-` 版本 PR 的现有预提交作业失败。

更改的路径：

- `.agents/skills/pr-design-doc/SKILL.md`
- `.agents/skills/pr-design-doc/references/html-craft.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/workflows/pr-artifacts.yml`
- `.github/workflows/precommit.yml`
- `AGENTS.md`
- `CONTRIBUTING.md`

链接问题接受上下文：

- [#5997](https://github.com/OpenHands/software-agent-sdk/issues/5997)：推迟临时 PR 工件清理，直到合并到主之后 - 当前状态已关闭，已于 2026-10-16T07:13:46Z 关闭。

> - [ ] `pr-artifacts.yml` 不再定义在 `pull_request_review` 上运行的作业，并且批准同一存储库 PR 不会将 `.pr/` 删除提交推送到 PR 头分支，因此批准时的工件清理不会触发 CI 运行。 - [ ] 批准同一存储库 PR 会使 `.pr/` 目录在 PR 分支上保持不变。 - [ ] 在携带 `.pr/` 的同一存储库或分支 PR 合并到 `main` 后，合并后作业将针对 `automation/remove-pr-artifacts` 上的 `main` 打开或更新单个清理 PR，其差异仅删除 `.pr/` 下的文件。 - [ ] 当 `main` 在合并时没有 `.pr/` 目录时，合并后作业不会创建提交并且不会打开清理 PR（现有的保留无操作路径）。 - [ ] 当 `automation/remove-pr-artifacts` 的清理 PR 已存在时，合并后作业会更新相同的 PR，而不是打开第二个。 - [ ] 的`` comment, for both same-repository and fork PRs, states that `.pr/` is removed automatically after the PR merges to `main` through the cleanup PR, and no longer states that it is removed on approval. - [ ] The cleanup PR continues to be subject to the normal review and required-check protections for `main`, and `.github/workflows/pr-description-check.yml` still exempts the `automation/remove-PR-artifacts` branch. - [ ] `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`, and `.agents/skills/pr-design-doc/SKILL.md` describe removal after merge to `main` consistently and no longer say a same-repository `.pr/` directory is removed on approval. - [ ] `actionlint .github/workflows/pr-artifacts.yml` 通过，并且 t

REST 兼容性：没有为此 PR 返回机器人报告。

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5998#pullrequestreview-5528201235)_这篇评论是由AI发布的智能体 (OpenHands_._ ## 评论 `c0be31e4dd1278a90f04e5bb43d0f65b6474547c` 范围检查：此更改应在此处。 `.github/workflows/pr-artifacts.yml` 是该仓库所有者管理的流程 `.pr/` 评审 artifact 规范，以及关联的 issue #5997`priority:low`, `ready-for-dev` 限制了修复范围仅限于该工作流及其描述其时间的指导。 否 SDK/Agent Server API 或所有权边界被跨越。### 我在当前主干上验证了以下内容： **触发器和作业。** 的 `pull_request_review` 触发器和 `cleanup-on-approval` 工作都丢了。 `check-pr-artifacts` 和 `cleanup-after-merge` remain. 没有 dangling references to `cleanup-on-approval` 在树的任何地方 **合并后路径未变。** 的 `cleanup-after-merge` job body 与  byte-identical `origin/main` (comment)

<a id="6009-fixmarketplace-load-skills-from-registered-repositories-without-a-manifest"></a>

### ＃6009：fix(marketplace)：从注册存储库加载技能而无需清单

- 提交：`6530325e9dd0ea1b6b4f1994d7dab52764cfc3f1` (2026-10-16T12:04:36-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/6009).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-6009)。 家庭：F09、F25、F26。

陈述意图：

> - 当注册源没有市场清单时，注册表将其读取为带有新 `Marketplace.from_skills_dir` 的普通技能文件夹。 `skills/` 和 `.skills/` 中的每个 `<name>/SKILL.md` 文件夹都成为独立技能。 如果两个文件夹都不存在，则使用直接位于源路径中的技能文件夹，因此 `repo_path` 可以指向技能文件夹本身。
> - 永远不会读取松散的 Markdown 文件，因此存储库的 README 和文档不会成为技能。 这些技能会像清单中的独立技能一样自动加载，包括按名称选择。
> - 既没有清单也没有技能文件夹的源仍然会失败，现在有一条消息说两者都丢失了。 无效的清单仍然是一个错误。

更改的路径：

- `openhands-sdk/openhands/sdk/marketplace/registry.py`
- `openhands-sdk/openhands/sdk/marketplace/types.py`
- `tests/agent_server/test_skills_service.py`
- `tests/sdk/conversation/test_local_conversation_plugins.py`
- `tests/sdk/marketplace/test_marketplace_registry.py`

链接问题接受上下文：

- [#6008](https://github.com/OpenHands/software-agent-sdk/issues/6008): [Bug]: 注册的技能仓库没有市场表现文件，加载没有技能——当前状态已关闭，关闭于2026-10-16T16:04:39Z。

> - [ ] 没有清单的注册源会加载 `skills/` 和 `.skills/` 中的 `<name>/SKILL.md` 文件夹，`auto_load` 可以按名称选择它们。 - [ ] 指向技能文件夹本身的 `repo_path` 会直接在其中加载技能文件夹。 - [ ] 松散的 Markdown 例如 README 或文档永远不会作为技能加载。 - [ ] 既没有清单也没有技能文件夹的源仍然会失败，无效的清单仍然是错误。 ### 安装方法 Source checkout with uv ### SDK Version main at b187e88 ### 版本确认 - [x] 我已确认此错误存在于 OpenHands SDK 的 LATEST 版本上 ### Python 版本 3.13 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6193905511)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； COMMENTED; hieptl](https://github.com/OpenHands/software-agent-sdk/pull/6009#pullrequestreview-5550218642)：Hello Alona，**总体：非阻塞。**我这边没有阻挡者。 回退方案包含得很好。 只有在manifest缺失时运行，无效的manifest仍然失败，而发现将`find_skill_md_directories`传递给repository root，因此，技能文件夹在repository之外被symlinked的技能被跳过。- **非阻塞（问题）** (`registry.py:84`): 注册为市场的地方的单个插件仓库现在只加载其技能，丢弃其钩子和MCP服务器无声地。 Main在这里大声失败了。 - **非阻塞 (nit)** (`types.py:302`)：文件夹中重复的技能名称将被删除，且不会发出警告。 在`647e863`、`tests/sdk/marketplace`、`tests/sdk/plugin`、`tests/sdk/skills`上，对话插件测试以及Agent Server技能和插件测试通过（922）。 一个包含 430 项技能的普通存储库会在大约 0.1 内自动加载
- [评论； APPROVED; hieptl](https://github.com/OpenHands/software-agent-sdk/pull/6009#pullrequestreview-5550276736)：谢谢！ 🙏
- [review_comments; 评论； hieptl](https://github.com/OpenHands/software-agent-sdk/pull/6009#discussion_r4296534499)你好阿诺娜，输出中文简体译文 **非阻塞（问题）** 一个不是市场而是单个插件的仓库（例如 `.plugin/plugin.json` 与 `skills/`, `hooks/` 和 `.mcp.json`）也没有市场应用的ifest，所以现在就在这里。 其技能作为独立技能加载，其钩子， MCP 服务器和命令无警告就被丢弃。 在主要部分，注册失败并显示“未找到市场清单”，因此该错误至少是可见的。 我检查了这个用scratch仓库：main加载什么也没有，记录失败，而这个分支加载其技能，只记录“没有manifest”信息行。 这是你想要的行为吗？ 如果不是，你认为在源有错误时保留错误怎么样 `plugin.json` 在其中一个 `PLUGIN_MANIFEST_DIRS`, 或至少记录一条警告，说明其钩子和 MCP 服务器被忽略？ H
- [review_comments; 评论； hieptl](https://github.com/OpenHands/software-agent-sdk/pull/6009#discussion_r4296534504)：你好阿罗娜，**非阻塞（nit）**当两个文件夹声明相同的技能名称（例如`skills/a`和`.skills/b`，都带有`name: shared`）时，`setdefault`保留第一个并删除第二个，没有日志行。 `logger.warning` 命名这两个文件夹将使人们更容易发现这一点。 如果您想保持安静，可以跳过。 非常感谢：祈祷：
- [review_comments; 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6009#discussion_r4297131911)谢谢。 继续加载技能，但同意不应该无声：#6031 登记了一个警告，当源有  `plugin.json`说只有其技能被加载，其钩子， MCP 服务器和命令被忽略。
- [review_comments; 评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6009#discussion_r4297132099)：在 #6031 中添加：当两个技能共享名称时命名两个文件夹的警告。 第一个还保留着。
- [讨论评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6193896004): @OpenHands  /codereview-roasted 请审查提交的 commit 647e863a42cbb503b64068507f43184db0e7c260。 如果 PR 头部更改，报告并拒绝另一提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性回归覆盖率，以及是否   PR  验证声明与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 以这些简洁的行结束实质性审查（不要使用代码框），选择一个裁决：   REVIEWED_HEAD647e863a42cbb503b64068507f43184db0e7c260 REVIEW_REQUEST未找到原文内容 VERDICT: APPROVED 使用 VERDICT: CHANGES_REQUESTED 而是当发现需要更改时。 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6194217377)## 代码审查：从注册的仓库中加载技能，无需 manifest **审阅的提交：**  `647e863a42cbb503b64068507f43184db0e7c260` (PR 头不变 **基础：**  `main` @ `fd387b58dc7b707b73c159845c0396a17000be24` 已验证5个文件匹配 PR manifest: `marketplace/registry.py` (+21), `marketplace/types.py` (55+, 新) `Marketplace.from_skills_dir`), and 3 test files. 否 REST/OpenAPI, 已持久化-settings, public-Python-API, 或序列化表面已更改。### 正确性修正为单一的加法回退方案缺少 manifest 时： `_load_marketplace` 读取文件夹为纯文本智能体技能目录。 我追踪了整个数据流的端到端： - 两个消费者都通过相同的路径。 智能体-server `load_registered_marketplace_skills` 和 `LocalConversation._ensure_plugins_loaded` -> `MarketplaceRegistry.get_marketplace
- [讨论评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6194301153): @OpenHands  /codereview-roasted 请审查提交的 commit 647e863a42cbb503b64068507f43184db0e7c260。 如果 PR 头部更改，报告并拒绝另一提交。 仅审核：请勿推送代码、合并、部署或更改属性。 检查正确性回归覆盖率，以及是否   PR  验证声明与证据相符。 保持代码注释简短。 发布实质性评论并将其链接到您的完成消息中。 以这些简洁的行结束实质性审查（不要使用代码框），选择一个裁决：   REVIEWED_HEAD647e863a42cbb503b64068507f43184db0e7c260 REVIEW_REQUEST: a0cb0409946244658ca7ab7f1c7faa44 VERDICT: APPROVED 使用 VERDICT: CHANGES_REQUESTED 而是当发现需要更改时。 如果无法审核，请在没有批准判决的情况下解释拦截者。
- [讨论评论； ak684](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6195083833)## 代码审查：从注册的仓库中加载技能，无需 manifest **审阅的提交：**  `647e863a42cbb503b64068507f43184db0e7c260` (PR 头部未变 - 通过验证 API) **基础：** 合并基点 `b187e88e` 已验证5个文件匹配 PR manifest: `openhands-sdk/openhands/sdk/marketplace/registry.py` (21, new) `_load_marketplace`  回退方案), `openhands-sdk/openhands/sdk/marketplace/types.py` (55+, 新) `Marketplace.from_skills_dir`), and 3 test files. 否 REST/OpenAPI, 已持久化-settings, public-Python-API, 或序列化表面已更改。### 正确性修正为单一的加法回退方案when `Marketplace.load` 提出了 `FileNotFoundError` (无 manifest) `_load_marketplace` calls `from_skills_dir` 并读取文件夹为纯文本智能体技能目录； 无效的 manifest 仍然引发 `ValueError` before the 回退方案; 阿苏
- [讨论； 评论； OpenHands-ai[bot]](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6195124725): 主题审查已发布到 PR，审查的提交点工作树干净。 ## 摘要 **Post:** [PR #6009代码审查](https://github.com/OpenHands/software-agent-sdk/pull/6009#issuecomment-6195083833) **结论：** APPROVED — `REVIEWED_HEAD: 647e863a42cbb503b64068507f43184db0e7c260`, `REVIEW_REQUEST: a0cb0409946244658ca7ab7f1c7faa44` ### 我核实了 1. **审核目标**：通过GitHubAPI确认PR头正好是`647e863a42cbb503b64068507f43184db0e7c260`（不变，仍然打开）。 PR 的 5 个文件清单将实际提交差异与其合并基础 (`b187e88e`) 相匹配； 早期明显的额外文件只是 PR 分叉点之前的仅主要提交。 2. **正确性**：跟踪通过两个消费者（智能体-服务器`load_registered_marketplace_skills`和“LocalConvers”的完整数据流

<a id="5955-fixagent-server-reserve-the-run-slot-before-a-gateway-turn-saves-its-message"></a>

### ＃5955：fix(agent-server)：在网关保存其消息之前保留运行槽

- 提交：`4a5f5a09096aea331b91481a5ff94dbfed22940e` (2026-10-17T00:03:47+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5955).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5955)。 族：F05、F06、F07、F08、F09、F10、F11、F12、F30、F31。

陈述意图：

> - `EventService.reserve_run_slot()` 会提前声称运行容量（或在对话已经持有自己的运行许可或仍有运行任务在处理时，返回 `None`，因此运行中的对话不会被拒绝）。 `send_message` 采用可选的 `run_slot` 并将其传递给 `run()`。
> - `_run_agent`（网关）在`send_message`之前保留并在之后释放其句柄。
> - 表单：`F30.chat-reuse-run-limit-429` 现在 `Requires: F30.chat-reuse-header` （它搜索的是那个子弹的 `QA_F30_SECOND` 转换，所以 `--only` 在缺少必要前提条件时失败了），以及其已知错误标记、注释和警告行都被更新了。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `openhands-agent-server/openhands/agent_server/openai/service.py`
- `tests/agent_server/test_run_admission.py`

链接问题接受上下文：

- [#5934](https://github.com/OpenHands/software-agent-sdk/issues/5934)：[错误]：持续的 OpenAI 网关对话上的 429（运行限制）仍会保存用户消息，因此每个重试都会附加一个重复项 — 当前状态已关闭，已关闭 2026-10-16T22:03:49Z。

> - [  ] 所有运行槽位都被占用 `POST /v1/chat/completions` 在继续对话时，回答 429 并不附加用户消息，附带详细信息 `Conversation run limit reached. Retry the request later.` - [  ] 当会话已经运行（它持有自己的运行许可）时，仍然接受代理开启会话的请求（不是429的误报） [  ] 原生 `POST /api/conversations/{id}/events` 合同（消息保存后，然后返回 429） `/run`  重试提示) 未改变 [  ] A 单元测试覆盖了拒绝门面，但保留了会话事件 [  ] 地图弹珠 `F30.chat-reuse-run-limit-429` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文原因：- `_run_agent` (`openhands-agent-server/openhands/agent_server/openai/service.py:534`) calls `event_service.send_message(..., run=True)` 在继续的路径（第552行） `EventService.send_message` (`openhands-agent-server/openhands/agent_server/event_service.py:842`) 首先保存消息（第853行），然后才调用 `run()`, 该端点获取一个运行槽并触发 `ConversationRunLimitExceeded`; `send_message` 重新包装了“消息已保存...” 重试  POST  /api/conversations/{id}/run" 第908行的细节。 那份合同符合原生事件端点不是门面。 - 新对话会先为任何创建的会话预留一个位置`ConversationService.start_conversation`, `RunSlot.acquire`这是因为只有继续的路径泄露了。 建议修复：在网关路径上，在 s 之前保留运行槽

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5955#issuecomment-6159717650)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5955#pullrequestreview-5512726609)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## #5955 的评论 — 在网关保存其消息之前保留运行槽位 **范围：** In-repo 并正确拥有。 `openhands-agent-server`（canonical Agent Server）中的变更保持不变，并且利用现有的 `RunSlot` 资源机制而不是添加一个并行机制，这符合链接问题所声明的非目标和 `AGENTS.md` / `.agents/skills/custom-codereview-guide.md` 中的归属指导。 不需要产品/架构决策。 **我在头 `5e4a57f` 上验证的内容：** - 差异仅在 OpenAI 网关的持续对话路径上添加预先保留。 `_run_agent`在`send_message`之前调用`reserve_run_slot()`，并在`finally`中释放句柄。 本机 `POST /api/conversations/{id}/events` 路径 (`event_router.py`) 和 `send_me

<a id="5842-fixagent-server-apply-bash-order__gt-filter-before-paging"></a>

### ＃5842：fix(agent-server)：在分页之前应用 bash order__gt 过滤器

- 提交：`304ea67a7993c04c45a4d2caefa5a0ad228e9c61` (2026-10-17T00:04:40+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5842).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5842)。 家庭：F13。

陈述意图：

> - `_search_bash_events_sync` (`bash_service.py`) 现在在填充页面时会删除已过滤的事件，因此 `limit` 仅计算返回的事件。 `next_page_id` 命名通过过滤器的下一个事件，因此页面后面永远不会有空页面。
> - 两个单元测试：`order__gt`分页跨两页，并且当过滤掉每个剩余文件时没有光标。
> - `F13.order-gt-paging` 地图项目符号不再带有其 `# bug` 标记，其散文和分页陷阱现在描述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`
- `openhands-agent-server/openhands/agent_server/bash_service.py`
- `tests/agent_server/test_bash_service.py`

链接问题接受上下文：

- [#4388](https://github.com/OpenHands/software-agent-sdk/issues/4388)：智能体-服务器：order__gt 过滤器处于活动状态时，search_bash_events 分页错误 — 页面尺寸过小，客户端在空的下一页上循环 — 当前状态已关闭，已关闭 2026-10-16T22:04:42Z。

> - [ ] 在当前 `main` 上，设置 `order__gt` 和 `limit=N` 的 `GET /api/bash/bash_events/search` 返回最多包含 `N` 个事件的页面，其中 `order` 大于 `order__gt`，而不是受读取文件数限制的页面。 - [ ] 当页面的项目全部被 `order__gt` 删除时，响应返回 `items: []` 和 `next_page_id` null（或以其他方式保证前进进度），因此跟随光标的客户端无法在空页面上循环。 - [ ] `next_page_id` 仍然会在下一个请求时解析为有效的页面开始，并且过滤结果集的最终页面报告 `next_page_id` null，因此使用 `order__gt` active 对结果集进行分页会终止，并仅产生每个匹配事件一次。 - [ ] `RemoteWorkspace.execute_command`（及其异步镜像）重新组装超过 100 个块的输出：生成超过 100 个 `BashOutput` 块的命令返回完整的输出和真正的退出代码，而不是 `exit_code` -1 和 `timeout_occurred` True。 - [ ] 没有 `order__gt` 的现有 `search_bash_events` 行为不变：`kind__eq`、`command_id__eq`、`timestamp__gte`/`timestamp__lt` 和 `sort_order` 仍然像以前一样过滤、排序和分页，`tests/agent_server/test_bash_service.py` 继续通过。 - `tests/agent_server/test_bash_service.py` 中的 [ ] 回归覆盖范围断言可观察的页面内容：大小为 `limit` 的 `order__gt` 页面返回 `limit` 个过滤事件，并且全过滤请求不返回任何项目，也没有光标。 添加的测试在 `main` 上失败，但修复后通过。 - [ ] `.agents/skills/verify-智能体-ser 中的 `F13.order-gt-paging` 项目符号

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5842#issuecomment-6157898237)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5842#pullrequestreview-5511870390)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论：PR #5842 — 在分页 **范围之前应用 bash `order__gt` 过滤器。**这属于 `OpenHands/software-agent-sdk`：更改修复了 Agent Server 中的 `BashEventService._search_bash_events_sync`，它拥有 `/api/bash/bash_events/search` REST 合约。 无需跨存储库移动。 **我在头 `929319f`** 上验证的内容 - 修复是正确且最小的。 旧代码在 `matched[start_index : start_index + limit]` 中切片，然后在 `matched[start_index + limit]` 位置设置光标位置，然后在切片内部应用 `order__gt` 过滤器。因此，当 `next_page_id` 仍然设置时，一页可以没有项目。 新循环迭代 `matched[start_index:]`，跳过不可读的文件和失败的事件 `order__gt`，并且仅在 `len(page_events) >= limi 时设置 `next_page_id = name`
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5842#pullrequestreview-5524169112)：针对同一问题（#4388）在 #4396 上批准了这一点。 两者都采用正确的分页前过滤方法（此PR归功于#4396），但这个在三个方面更强：（1）当前头CI完全绿色（51/56检查通过，REST跳过/中立）与#4396从9月25日开始的陈旧的3检查头相比； (2) 它有针对真实 Agent Server 的实时前/后证据（`F13.order-gt-paging`：主屏幕上的 xfail x2，带有空页 + 光标，此处 xpass x2，标记删除后通过），其中 #4396 仅具有单元测试； (3) 光标指向通过过滤器的下一个事件，因此整页后面永远不会有空页 — #4396 明确留下额外的空页往返。 生产变化很小（约 15 条生产线，没有新机器），并且两项新测试在主要测试中失败。 结束#4396 支持此PR。 _这篇评论是cre

<a id="5780-fixagent-server-log-failed-runs-without-rendering-a-rich-traceback-on-the-loop"></a>

### ＃5780：fix(agent-server)：记录失败的运行而不在循环上呈现丰富的回溯

- 提交：`60c6f62133e0f649e2e71ec8c8aa51a06a1fb0f0` (2026-10-17T00:05:19+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5780).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5780)。 族：F05、F06、F07、F08、F09、F10、F11、F12、F31。

陈述意图：

> - `event_service.py`：使用消息中的纯文本回溯记录 ERROR 处的运行失败，而不是通过 `exc_info`，因此没有处理程序在循环上呈现丰富的回溯。
> - 测试：新的单元测试检查记录是否为ERROR，没有`exc_info`并携带整个链； 更新了现有的日志记录测试。
> - 地图：`F05.run-error-responsive` 失去了已知错误标记； 子弹散文和陷阱行现在描述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `tests/agent_server/test_event_service.py`

链接问题接受上下文：

- [#5373](https://github.com/OpenHands/software-agent-sdk/issues/5373)：智能体服务器：一次日志调用可能阻塞事件循环，并放大内存占用（rich 回溯渲染）；当前状态为已关闭，关闭时间为 2026-10-21T13:51:40Z。

> - [  ] 使用默认的服务器日志配置 (`LOG_RICH_TRACEBACKS` unset or True)，用循环记录异常 `__context__`/`__cause__` 链在有界时间内和有界内存中返回：一个确定性测试构造了这样的异常，调用了日志路径，并且调用完成而不是挂起，没有无界 RSS 增长 [  ] 对于病理性的深异常链和重复/重复的原因链 — 不仅是循环形状 [  ] 事件-WebSocket 错误路径 (`openhands/agent_server/sockets.py`, `events_socket`) 从未执行过无界操作同步 traceback/stack render; 失败 `websocket.send_json` 或者客户端断开连接仍然被处理为良性 `Event websocket disconnected`) 无丰富渲染 `stack_info=True` - [  ] 错误路径仍然发送了  `ServerErrorEvent` 当套接字打开时，发送给客户端。 必须确保渲染的加固不会导致客户端可见错误报告的丢失 [  ] 在病理化日志路径被执行时，服务器继续提供服务： `/alive`, `/server_info`, and the conversation REST  端点响应其正常延迟，并且没有楔形发生（在现有服务器/压力结构的仓库中的自动化测试） [  ] 在病理路径被反复执行后，该过程终止于 SIGTERM 在配置的停止点内超时 instead of requiring SIGKILL. - [  ] 现有的日志行为保持不变：普通（非病理）异常仍然会生成丰富的调用栈 `LOG_RICH_TRACEBACKS=true`; `LOG_RICH_TRACEBACKS=false` 和 JSONCI console 

- [#5633](https://github.com/OpenHands/software-agent-sdk/issues/5633): [Bug]: 运行失败导致事件循环无法记录详细的堆栈跟踪：/alive 需要大约5秒，而不是100毫秒——当前状态已关闭，关闭时间戳为2026-10-16T22:05:21Z。

> - [  ] 使用默认控制台日志，没有 `/alive` 探针运行失败时会花费1.5秒，而套接字错误帧不会延迟 [  ] 运行失败仍然详细记录，足以诊断它 [  ] A 回归测试在生产服务器上失败，并限制了的延迟并发请求 [  ] 地图弹珠 `F05.run-error-responsive` passes; 其已知错误标记已被移除 uv  同步在主版本 2804c12 的 checkout 中， 上下文 - `openhands-agent-server/openhands/agent_server/event_service.py:1546`: `logger.exception("Error during conversation run")` 在 `_run_and_publish`在服务器循环中的一项任务。 这里异常是  `ConversationRunError` 串联起来 LiteLLM, OpenAI, httpx 和 httpcore 错误 `openhands-sdk/openhands/sdk/logger/logger.py:45` defaults `LOG_RICH_TRACEBACKS` to True; 134-137 安装了 `RichHandler(rich_tracebacks=...)` 除非作为根控制台处理器，否则 `LOG_JSON` 或 CI 已经设置。 `RichHandler.emit` 渲染整个链，包括源上下文在调用者同步地，在这里是一个循环 `LocalConversation.arun` 已经存储了 `ConversationErrorEvent` and set `ERROR` 在执行之前 `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2582-2608`因此，只有循环中的日志行及其余内容都会被延迟。 建议的修复：保持控制台渲染不在循环中，可以使用  `QueueHandler`/`QueueListener` 在控制台处理器周围 `setup_logging` （涵盖所有） `logger.exception` 在循环中) 或者，这里，一条一言错误 (事件已经存在 `code` 一个

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5780#issuecomment-6156831024)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5780#pullrequestreview-5524170122)批准#5709，针对同一问题#5633。 两者都停止了富指针渲染的阻塞事件循环。 我更喜欢这个 PR'日志交易：完整的调用堆栈仍然存在' ERROR 将级别以文本形式包含在消息中，因此生产日志（INFO / LOG_JSON) 保留诊断细节，而 #5709 将堆栈跟踪降级为 DEBUG 生产部署将失去它。 证据也是这对证据中最强的一个：活的 `/alive` 在主分支上，4540/4791 ms的探针与142/93 ms的探针相比，新测试在主分支上失败了。 该变化使用了 ~13 条生产线，仅使用了 stdlib，没有新设备，且是当前头 CI #5709 有失败 PR描述检查。 赞成此票，关闭#5709 PR_此评论由人工智能创建智能体 (OpenHands代表格雷姆 Neubig._

<a id="5779-fixsdk-install-the-posted-llm-when-switch_llm-targets-a-registered-usage_id"></a>

### ＃5779：fix(sdk)：当switch_llm针对已注册的usage_id时安装发布的LLM

- 提交：`a6c7bf5591f64ca62c653565d7498d72e155e789` (2026-10-17T00:08:24+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5779).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5779)。 家庭：F05、F08、F09、F10。

陈述意图：

> - `LocalConversation.switch_llm` 仅当其配置（`model_dump(mode="json")` 和机密暴露）等于发布的配置时才重用已注册的 LLM； 否则，它会用上一个LLM替换注册表条目，并将已记录在该`usage_id`下的`stats.usage_to_metrics[usage_id]`的指标对象交给它。 相同的重新切换（`switch_profile`、`classify_and_switch_llm`的`profile:<name>`）仍然重用缓存的对象。
> - 路线、其 `200 {"success": true}` 合同和 `clients/typescript` 保持不变，与分类范围相同。
> - 回归测试：`tests/sdk/conversation/test_switch_model.py`（初始化会话切换，省略 `usage_id`，指标结转； 重复使用相同的配置）和`tests/agent_server/test_switch_llm_survives_reload.py`（真实`ConversationService`：`default`注册，从实时对话中读回的切换模型，`base_state.json`和`get_conversation`）。 `F09.switch-llm-registered-usage-id` 已知错误标记已被删除，其配方现在需要安装。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`
- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`
- `tests/agent_server/test_switch_llm_survives_reload.py`
- `tests/sdk/conversation/test_switch_model.py`

链接问题接受上下文：

- [#5636](https://github.com/OpenHands/software-agent-sdk/issues/5636): [Bug]: switch_llm 返回200，但保留旧值 LLM 当提交的 usage_id 已经注册过 — 当前状态关闭，关闭于2026-10-16T22:08:25Z。

> - [  ] 在初始化对话时， `switch_llm` 带有注册的 `usage_id` 并且安装了帖子中的不同配置 LLM 或返回4xx状态码，而不是200状态码 LLM - [  ] 重新切换到已注册的相同配置 `usage_id` (e.g. `classify_and_switch_llm`'s `profile:<name>`它仍然有效，使用情况保持不变 `stats.usage_to_metrics`. - [  ] A 回归测试覆盖了一个初始化对话的切换 `usage_id: "default"`. - [  ] 的 `F09.switch-llm-registered-usage-id` 地图子弹通过和已知错误标记被移除。### 安装方法 uv  同步在主版本 2804c12 的 checkout 中， 上下文 - `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1658-1662`: `switch_llm` calls `self.llm_registry.get(llm.usage_id)` 并注册了提交的 LLM 只有在 `KeyError`; 点击后发布的配置将被丢弃文档字符串 1650-1653: “first-write-wins”) `local_conversation.py:1586-1596`: 智能体初始化注册了智能体's LLMs, so `default` 在第一个消息之后 `openhands-sdk/openhands/sdk/llm/llm.py:626-627`: `usage_id` 默认值为 `"default"`. - `openhands-agent-server/openhands/agent_server/conversation_router.py:616-650`: 路由调用 `conversation.switch_llm(llm)` and returns `Success()` 无条件地其的文档字符串提供转发配置。 Suggested fix: in `switch_llm`, 重用注册的 LLM 只有当其配置等于发布的配置时 `_condenser_for_switched_llm` 比较 `model_dump(mode="json", context={"expose_secrets": True})`); 否则更换 ent

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5779#issuecomment-6156816074)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5779#pullrequestreview-5511218922)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## #5779 范围检查的评论（每个根 `AGENTS.md` 和 `.agents/skills/custom-codereview-guide.md`）：更改完全在该存储库的所有权范围内 - SDK 中的 `LocalConversation.switch_llm` 行为加上其测试和 verify-智能体-server 功能图。 `8a36139` - **无需交叉产品决策。** - `switch_llm` 根因修复是正确的。LLM 现在比较注册和发布的 `model_dump(mode="json", context={"expose_secrets": True})`，只有在它们匹配时才重用缓存对象，否则替换注册表。 我确认 `expose_secrets` 上下文实际上传播到机密字段序列化器，因此相同模型/不同密钥配置被正确地视为不同的（`equal exposed: False`
- [reviews APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5779#pullrequestreview-5524169569)批准#5699，针对同一问题#5636。 两者都正确地重用了注册的 LLM 只有在配置匹配时才替换它，否则保留累积的指标。 这个在验证和集成方面胜出：(1) 当前头 CI 绿色完全 (51/56) 对应 #5699 的失败 PR-描述检查和5检查头；(2) 实时地图证据`F09.switch-llm-registered-usage-id` 在主分支上失败， 在这里通过， 在移除标记后通过]，加上一个专门的实[]`ConversationService` 重载测试（`test_switch_llm_survives_reload.py`(3) 该指标从注册的系统中继承 LLM 对象本身，每个对象都保持一个单一的指标对象 usage_id. 赞成此票，关闭#5699 PR （其活的curl重现工作很好，证实了修复）。_此评论由AI创建智能体 (OpenHands) on

<a id="5772-fixagent-server-mark-a-goal-loop-left-active-at-restart-as-interrupted"></a>

### ＃5772：fix(agent-server)：将重新启动时保持活动状态的目标循环标记为中断

- 提交：`8ba8ccbeb1a5306835f44f5f0f8ab20516373ee9` (2026-10-17T00:14:07+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5772).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5772)。 族：F05、F06、F07、F08、F09、F10、F11、F12、F31。

陈述意图：

> - `EventService.start()` 现在会处理现有的过期状态，旁边是新的过期状态`RUNNING` 执行状态重排序：如果已持久化  `goal` 状态仍然 `active`, 它追加了一个 `active: false, status: "interrupted"` 与之相同的状态 `objective`, `iteration` 和 `max_iterations` （宣判已结案，就像其他所有案件一样） `interrupted` status). 它由加载状态驱动，因此它可以涵盖优雅重启和硬杀，目标是可恢复的 `/goal/resume`. 终端或已经不活动的状态将被保留。 检查是尽力而为（未读取的日志会记录警告，不会阻止加载）并且在运行事件循环。
> - `_last_goal_loop_status()` 按索引向后遍历日志并在第一个目标状态处停止，而不是具体化整个事件列表。
> - verify-智能体-server 特征图中的 `F11.goal-restart-active` 删除了其已知错误标记，并且描述该错误的散文和陷阱现在描述了该行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F11-goals.md`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `tests/agent_server/test_goal_loop.py`

链接问题接受上下文：

- [#5627](https://github.com/OpenHands/software-agent-sdk/issues/5627): [Bug]: /goal 优雅重启时保持活动状态 `running` 之后而不是 `interrupted` — 当前状态已关闭，关闭时间：2026-10-16T22:14:09Z。

> - [  ] 在优雅重启并保持循环的情况下，最后一个目标状态是 `active: false, status: "interrupted"` 目标和计数保持不变 `/goal/resume` 继续它 [  ] 对话最后目标状态为 [加载] `active: true` (e.g. 在一次硬杀之后，[where] `close()` 也不报告（该端点已弃用） `interrupted`, covered by a 回归 test. - [  ] 的 `F11.goal-restart-active`  uv  同步在主版本 2804c12 的 checkout 中， 上下文根本原因，在 `openhands-agent-server/openhands/agent_server/event_service.py`: - `EventService.close()` (2061) 设置了 `self._closing = True` (2064) 并且取消了 `_goal_loop_task` (2076-2079). - [缺少内容] `except asyncio.CancelledError` handler in `_run_goal_loop` (1835-1842) 发射 `interrupted` 仅 `if not self._closing` (1839)，因此关闭取消记录了什么 `EventService.start()` 重置一个已过期的 `RUNNING` 加载时状态为执行 (:1328-1333)，但没有任何东西能解决一个滞后的状态 `running` 目标状态 `stop_goal_loop()` (1858-1871) 返回 `False` 当没有任务且记录了什么时， `/goal/stop` route (`conversation_router.py:477-494`无论返回什么，都会返回200。 `resume_goal_loop()` (1905) 接受了此状态，因为它既不是也不是  `complete` nor `capped`这就是唯一的出路。 Suggested fix: in `start()`，旁边是陈旧的-`RUNNING` reconcile, read `_last_goal_loop_status()` (1873) 并且，如果 `active: true`, append a `goal`  `ConversationStateUpdateEvent` 与相同的pa

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5772#issuecomment-6156386934)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5772#pullrequestreview-5511025928)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 摘要此更改在此存储库的范围内：智能体服务器拥有对话生命周期和 `ConversationStateUpdateEvent` 流，并且修复程序与现有的过时的 `RUNNING` 执行状态协调一起存在于 `EventService.start()` 中。 该错误是真实存在的，修复程序已解决该错误。 在加载时，`EventService.start()` 现在调用 `_reconcile_stale_goal_status()`，它读取了最后一个已持久化 `goal` 状态，并，如果它仍然 `active`，则追加一个 `active: false, status: "interrupted"` 状态，携带相同的 `objective`、`iteration` 和 `max_iterations`，并且 `verdict` 已清除——与目标循环发出的每个其他 `interrupted` 状态的形状相同。 因为它是从加载状态驱动的，所以它涵盖了优雅的重启和硬终止，并且它离开了终端/alr
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5772#pullrequestreview-5524169343)：针对同一问题（#5627）在 #5719 上批准这一点。 核心 reconcile-in-`start()` 方法是相同的，但这个 PR 是更完整的包：（1）当前头 CI 完全绿色（51/56，REST 跳过/中性）与 #5719 失败的 PR 描述检查和薄 4 检查头； (2) 实时地图证据（`F11.goal-restart-active`：在 main 上 xfail x2，此处 xpass x2，标记删除后通过）加上在 main 上失败的优雅重启、硬终止和恢复回归测试； (3) 它通过 `GoalStatus` 验证已持久化状态，像其他所有中断状态一样清除 `verdict`，尽力使不可读的日志无法阻止对话加载，将 `_last_goal_loop_status` 改进为惰性向后扫描，并从特征图中删除现已修复的已知错误标记。 结束#5719 支持此PR。 _此评论由 AI 创建
- [review_comments; 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5772#discussion_r4299828915)：好智能体。 我曾经用显微镜手动寻找这些😅

<a id="5769-fixtypescript-use-the-global-websocket-in-the-callback-socket-clients"></a>

### #5769: fix(typescript): 在回调套接字客户端中使用全局 WebSocket

- 提交：`c87fddb623f0b7a43f697fa6bb3006e10203cd4c` (2026-10-17T00:21:57+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5769).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5769)。 家庭：F13、F34。

陈述意图：

> - 新的内部助手 `src/events/global-websocket.ts`：调用时返回 `globalThis.WebSocket` 并保存共享错误消息。 现在，两个客户端在连接时都会调用它。 所有模块加载检测和 `require('ws')` 代码都消失了，并且构建的 `dist/` 没有 `require` 或 `ws` 导入。
> - 测试：回调-客户端测试存根 `globalThis.WebSocket` 而不是假 `window`。 新测试涵盖导入后安装的构造函数以及全局构造函数上的 bash 客户端。 缺失实现测试现在删除了全局。
> - verify-智能体-server 映射：`F34.ws-callback-client` 和 `F34.bash-websocket` 丢失其 `# bug` 标记和“已知错误”标签。 他们的散文、WebSockets 概述和 Node 陷阱现在描述了固定行为。 README 指出了 Node 22 的要求。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `clients/typescript/README.md`
- `clients/typescript/src/__tests__/package-import.test.ts`
- `clients/typescript/src/__tests__/websocket-callback-client.test.ts`
- `clients/typescript/src/events/bash-websocket-client.ts`
- `clients/typescript/src/events/global-websocket.ts`
- `clients/typescript/src/events/websocket-client.ts`

链接问题接受上下文：

- [#4731](https://github.com/OpenHands/software-agent-sdk/issues/4731)：修复 WebSocket 客户端 require('ws') 破坏捆绑器 — 当前状态已关闭，已于 2026-10-16T22:22:00Z 关闭。

> ## 问题 `src/events/websocket-client.ts` 在库代码中使用 `require('ws')`：```typescript if (typeof window !== 'undefined' && window.WebSocket) { WebSocketImpl = window.WebSocket; } else { const ws = require('ws'); WebSocketImpl = ws; } ``` 问题：1。 `require()` 破坏了 ES 模块捆绑器（Webpack、Rollup、Vite）——它们静态分析导入 2. 检测在 ** 模块加载时 ** 运行，因此 `require('ws')` 会立即在 Node.js 中执行，即使 WebSocket 客户端从未使用过 3。 与浏览器兼容性要求相矛盾

- [#4846](https://github.com/OpenHands/software-agent-sdk/issues/4846): [Bug]:WebSocket 客户端在 ESM 版本中忽略 Node 的全局 WebSocket — 当前状态已关闭，已于 2026-10-16T22:21:59Z 关闭。

> - [ ] TypeScript WebSocket 回调客户端在节点 ESM 中使用 globalThis.WebSocket（如果可用）。 - [ ] 回退方案路径仍然支持注入的 WebSocket 实现和浏览器 window.WebSocket。 - [ ] TypeScript 客户端测试覆盖 Node 的全局 WebSocket 构造函数路径。 ###安装方法uv同步--dev; npm CI in clients/typescript ### 如果您选择“其他”，请指定_无响应_ ### SDK 版本当前主分支 ### 版本确认 - [x] 我已确认此错误存在于 OpenHands SDK 的 LATEST 版本上 ### Python 版本_无响应_ ### 型号名称（如果适用）_无响应_ ### 操作系统 Linux ### 日志和错误消息 WebSocket实现不可用 ### 最小代码示例 ```bash node --input-type=module -e "const {WebSocketCallbackClient}=await import('./dist/events/websocket-client.js'); const client=new WebSocketCallbackClient({host:'http://127.0.0.1:9',conversationId:'test',callback:()=>{},onError:console.error}); client.start(); client.stop()" ``` ### 屏幕截图和附加上下文这是支持  https://github.com/OpenHands/software-agent-sdk/pull/4799  的问题

- [#5651](https://github.com/OpenHands/software-agent-sdk/issues/5651): [Bug]: ConversationEventStream 节点 22 WebSocket 在拒绝重新连接后停止而不是后退 — 当前状态打开、关闭 —。

> - [ ] 在节点 22 的全局 `WebSocket` 上，流在尝试被拒绝后不断后退，并在服务器返回后重新连接，甚至当服务器在 `start()` 处关闭时也是如此。 - [ ] 从未解决的握手在 10 秒后算作失败的尝试，当实现也触发时不会进行双重调度 `close`。 - [ ] 带有假 `WebSocket` 的单元测试会发射 `error`，但从不 `close` 覆盖两条路径。 - [ ] `F34.event-stream-reconnect-native` 地图项目符号通过，其已知错误标记已被删除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main at 2804c12 ### 附加上下文在 `clients/typescript/src/client/conversation-event-stream.ts` 中： - `scheduleReconnect()` (176-195) 仅从 `onclose` 调用（145-165，在 164 处调用）并且从同步的 `catch` 中抛出 `connect()` (166-173)。 - `onerror` (140-144) 从不重新安排。 - 10 秒握手中止 (126-128) 仅调用 `socket.close()`。 在十一日关闭一个已经失败的套接字时，会触发第二个`error`，将`readyState`设置为2，并且仍然触发没有`close`，因此断开连接无法恢复。 建议的修复方案：将尝试的每个终端结果通过一个返回的[idempotent handler]发送，除非`this.socket === socket`，清除握手计时器，设置`this.socket = null`并调用`scheduleReconnect()`。 当尝试尚未打开时，从 `onclose`、`onerror` 以及握手计时器中调用它； 来自兼容实现的后续`close`然后找到`this.socket !== socket`并且不安排任何内容。 在此之前，Node 消费者可以传递 `ws` 构造函数

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5769#issuecomment-6155874165)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5769#pullrequestreview-5510851704)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围这属于此存储库：它修复了 `clients/typescript/`，此存储库拥有的浏览器兼容的 TypeScript 客户端，并且不需要跨存储库移动。 ## 我在头 `891df04d` 上验证的内容 - 修复是正确的。 `WebSocketCallbackClient` 和 `BashWebSocketClient` 现在都通过新的 `src/events/global-websocket.ts` 在连接时解析 `globalThis.WebSocket`，并且所有模块加载 `require('ws')` / `window.WebSocket` 检测都消失了。 构建的 `dist/events/` 不包含 `require` 或 `ws` 引用，因此解决了 #4731 和 #4846 中的捆绑器和 ESM-`require` 问题。 - 真实的前后证据（针对真实 `ws` 服务器的节点 24 ESM，构建 `dist/`）： - 基础 `dfd8fe8`：问题 #4846 重现 -> `ONERROR：WebSocket 实现不可用。 安装 ws 包
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5769#pullrequestreview-5524170717)：针对相同的问题（#4846、#4731）在#4799 上批准了这一点。 他们都读取全局的WebSocket而不是`require('ws')`，但PR在连接时通过一个共享的`global-websocket.ts`助手解析`globalThis.WebSocket`，因此安装在导入之后的构造函数(e.g。 `ws` 该端点在较旧的Node上被分配，然后在客户端中重复检测块被删除；#4799 在每个客户端在模块加载时捕获全局一次。 此 PR 还使 `ws` 保持依赖关系，因此 #5651 的文档 `createWebSocket` 解决方法仍然有效。 验证更强大且当前：对客户端进行的实时地图证明（xfail x2 on main -> xpass x2 here -> pass），该问题的Node 22重现重新运行在`dist/`，385 TypeScript测试通过，当前主干CI完全绿色（52/58）。 结束#4799 支持此PR。 （不关闭#

<a id="5768-fixagent-server-bound-profile-pre-flight-and-reject-exhausted-quotas"></a>

### ＃5768：fix(agent-server)：绑定配置文件预检并拒绝用尽的配额

- 提交：`76055f697a5e9295252e0d54ab4ea822946e5c54` (2026-10-17T00:23:32+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5768).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5768)。 家庭：F20。

陈述意图：

> - ping 使用 LLM 的副本，其中包含 `num_retries: 0`，不包含 `fallback_strategy`，并且 `timeout` = min(15 s, posted timeout)。 发布的配置本身没有改变。
> - SDK 的现有 `is_quota_exhaustion_error` 归类为用完预算/配额的速率限制错误，并通过已脱敏提供商消息回答 `valid: false`； 普通的 429 仍然是 `valid: true`。
> - 验证-智能体-服务器地图：`F20.validate-unreachable-bounded`和`F20.validate-hang-bounded`丢失其`# bug`标记和“已知错误”标签； 散文描述了有限的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md`
- `openhands-agent-server/openhands/agent_server/profiles_router.py`
- `tests/agent_server/test_profiles_router.py`

链接问题接受上下文：

- [#5100](https://github.com/OpenHands/software-agent-sdk/issues/5100): [Bug]请输出简体中文译文验证将预算超支的报告标记为有效，并暂停 ~2 分钟重试 — 当前状态关闭，关闭于2026-10-16T22:23:35Z。

> - [  ] 一个表示耗尽预算/配额的429e.g. `budget_exceeded`, `insufficient_quota`) makes `validate_profile` return `valid=false` with a 已脱敏错误信息 [  ] 仍然非阻塞的普通可恢复限流`valid=true`). - [  ] 预飞行调用不使用该配置的运行时重试 policy 上述重现只需几秒钟，最多耗时 2 LLM - [  ]  单元测试在 `tests/agent_server/` 覆盖预算超支429、可恢复429和无长期计划重试安装方法 pip / uv (`openhands-agent-server` 由 uvx 启动的 Agent Canvas) ### SDK 版本 1.48.0（也已验证） `main`请输出简体中文译文 [x] 我已经确认该 bug 存在于  LATEST 版本 OpenHands  SDK ### Python 版本 3.13 ### 如果适用，请输出模型名称 openhands/gpt-5.5 via LiteLLM 代理 ### 操作系统 macOS

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5768#issuecomment-6155830844)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5768#pullrequestreview-5510676729)：_此评论由 AI 智能体 (OpenHands) 发布。_ 评论了当前标题 `87799be1a4ff1dc2b24b6a88000ea72a452dbd64`（标题/正文/标签、评论线程、检查运行和链接问题 #5100/#5653/#5155 现在全部重新阅读）。 该帐户事先没有对此进行审查； 之后就没有评论了。 **范围。**该更改存在于该存储库自己的 Agent Server 路线 (`openhands-agent-server/.../profiles_router.py`) 及其测试和 `verify-agent-server` 特征映射散文中。 它属于这里； 没有必要进行跨回购移动。 问题 #5100 已由 `ready-for-dev` 开放。 **调查结果。**不存在重大正确性、安全性、兼容性或验收标准缺陷。 - **飞行前有限制。** `_preflight_llm()` copies the posted LLM with `num_retries=0`, `timeout=min(llm.timeout, 15)`, and `fallback_strategy=None`. 与`num_retries=0`tenacity的
- [reviews APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5768#pullrequestreview-5524170404)批准#5155，针对同一问题#5100。#5155仍然处于草稿状态 HUMAN 模板占位符未填充，添加了内容 `.pr/` 工作文件，因此它不在可审查状态。 this PR 已经完整。 在实质上，预飞行和拒绝消耗的配额都通过现有的方式绑定 `is_quota_exhaustion_error`但这个 PR 此外还包括：(1) 当前头节点 CI 完全绿色（51/56）且预提交干净；（2）对不可到达的证据进行实时地图取证端点请输出简体中文译文。False 在 0.3 秒后) 和悬挂提供者案例 (在 stub 中恰好有一个请求，被限制在 15.1 秒) 中，每个 xfail x2 在 main -> xpass x2 这里 -> pass; (3) 一个更干净的差异 (+217/-42, 3 个文件) 从共享中提取出来 `_invalid()` 代替重复错误处理，它会丢弃回退方案在飞行前检查期间，以确保工作正常回退方案无法掩盖一个损坏的主，且不

<a id="5778-fixagent-server-return-the-whole-output-from-execute_bash_command"></a>

### ＃5778：fix(agent-server)：返回execute_bash_command的整个输出

- 提交：`c73ec79e3fd1dfc1e5d6326fca4e0c14fa10029f` (2026-10-17T00:25:28+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5778).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5778)。 家庭：F13、F14、F15、F16、F34。

陈述意图：

> - `bash_router.py`: 路由读取命令的 `BashOutput` 事件的每一页（按照 `next_page_id`），按 `order` 排序，分别将标准输出和标准错误输出合并，最后返回合并后的文本及其退出代码。 响应仍然是一`BashOutput`； 小输出不变。
> - `clients/typescript`: `RemoteWorkspace.executeCommand` 将缺失的退出代码映射到 `-1` 而不是 `0`。
> - 验证-智能体-服务器地图：`F13.execute-large-output` 删除其已知错误标记； F13 和 F34 的散文和陷阱现在描述了连接的输出。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`
- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `clients/typescript/src/__tests__/remote-workspace-execute.test.ts`
- `clients/typescript/src/workspace/remote-workspace.ts`
- `openhands-agent-server/openhands/agent_server/bash_router.py`
- `tests/agent_server/test_bash_router.py`

链接问题接受上下文：

- [#5638](https://github.com/OpenHands/software-agent-sdk/issues/5638): [Bug]: execute_bash_command 仅返回超过 1 MiB 的最后一个输出块； null exit_code 过去 100 个块 — 当前状态已关闭，已于 2026-10-16T22:25:30Z 关闭。

> - [ ] `execute_bash_command` 返回多块命令的完整 stdout 和 stderr，并加入 `order`，以及最终块的退出代码。 - [ ] 对于超过 100 个块，响应携带真正的退出代码（`exit 7` 为 7）。 TS `RemoteWorkspace.executeCommand` 不再将丢失的退出代码映射到 0。 - [ ] 回归测试涵盖通过路由的多块输出。 - [ ] verify-智能体-server 特征图中的 `F13.execute-large-output` 项目符号通过，并删除了其已知错误标记。 ### 安装方法 uv 同步在 main 的签出中 ### 主版本位于 2804c12 ### 附加上下文 - `openhands-agent-server/openhands/agent_server/bash_router.py:122-123` 从 `search_bash_events(command_id__eq=command.id)` 返回 `cast(BashOutput, page.items[-1])`。 该搜索使用默认的 `limit=100` (`bash_service.py:150`)，并且路由忽略 `next_page_id`。 - `bash_service.py:25` 套 `MAX_CONTENT_CHAR_LENGTH = 1024 * 1024`。 `read_stream` (`bash_service.py:336-351`) 将每个完整的 1 MiB 切片存储为自己的 `BashOutput`，没有退出代码。 只有最后一个事件 (`bash_service.py:407-414`) 带有 `exit_code`。 小输出之所以有效，是因为它们唯一的事件是最后一场。 - `clients/typescript/src/workspace/remote-workspace.ts:133` 套 `exit_code: bashOutput.exit_code ?? 0`。 - Python SDK 的 `RemoteWorkspace.execute_command` 不使用此路由。 它轮询搜索并连接每个块。 建议的修复：在 `execute_bash_command` 中，按照 `next_page_id` 翻阅命令的 `BashOutput` 事件。 按 `order` 对它们进行排序，连接 `stdout` 和 `std

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5778#issuecomment-6156787589)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5778#pullrequestreview-5511327800)_这篇评论是由AI发布的智能体 (OpenHands)._ fix(agent-server)返回整个输出 execute_bash_command 经过验证 `e58ea59dee1afb53847c887bf1e5a520765d326d`. **我检查了什么** - 范围：修复内容位于智能体-server REST 路由和镜像到 `clients/typescript/`与所有权流程匹配的 `AGENTS.md` (Agent Server -> OpenAPI -> TS client). 它属于这个存储库； 无需跨仓库移动 `bash_router.py`: `_collect_bash_output` 现在是   `next_page_id` 在每一页上，按命令排序 `BashOutput` events by `order`, joins `stdout`/`stderr` 分别返回  `exit_code`. 分页不是非重叠的 (`next_page_id` 这是下一页的第一个项目，因此没有丢弃或重复分块。 响应仍然是一个单一的 `BashOutput`, and small/e
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5778#pullrequestreview-5524169829)：针对同一问题（#5638）在 #5697 上批准这一点。 两者都对所有块进行分页，按顺序连接，并将缺失的 TypeScript 退出代码映射到 -1 而不是 0。 这个 PR 总体上更强：(1) 当前头 CI 全绿色 (51/56) 对比 #5697 失败的 PR 描述检查和 5 检查头； (2) 实时地图证据（`F13.execute-large-output`：主线上的 xfail x2，此处的 xpass x2，标记删除后通过）除了通过覆盖 >100 个块和退出代码 7 的真实 `BashEventService` 进行的路由测试； (3) 空结果返回 `BashOutput` 和 exit_code -1，而不是提高 500，与 Python SDK 现有的 -1 约定相匹配。 结束#5697 支持此PR。 _此评论由 AI 智能体 (OpenHands) 代表 Graham Neubig._ 创建

<a id="6036-test-guard-linux-only-canvas-backend-cases-on-macos"></a>

### #6036：测试：保护 macOS 上仅限 Linux 的 Canvas 后端案例

- 提交：`bf9b6057b00e1b2b532ecff508c0d92d818adced`（2026-10-16T18:35:29-04:00）。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/6036).
- 意图：记录。 运行时：**不需要产品运行时**； [特征证据和限制](intent-runtime-overlay.md#pr-6036)。 系列：无需产品运行时间。

陈述意图：

> - 仅跳过需要受支持的 Linux 后端工件的测试。
> - 添加涵盖 `unsupported` 状态、准备和启动的非 Linux 回归测试，无需提取工件。

更改的路径：

- `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/6036#issuecomment-6223595991)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/6036#pullrequestreview-5553750739)_这篇评论是由AI发布的智能体 (OpenHands## 仅限范围测试的更改 `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`该仓库拥有（智能体-server 测试套件). 它属于这里； 无需进行跨仓库移动或产品决策。## 变更内容：添加了  `requires_linux_backend` skipif 标记键值对 `CanvasExtensionBackendManager.current_platform() is None`, 并应用于十项测试中测试夹具建造 `backend-linux-amd64`/`arm64` 将它们作为 Linux 脚本的 shebang 执行 `/proc`基于存活检查。 一个新 `test_backend_is_unsupported_on_non_linux_platform` asserts the `unsupported` status `prepare`, and `start` 非Linux主机上的路径，以及没有提取任何 artifact。 我在模块中检查了每一个测试测试夹具所有需要重新测试的测试

<a id="5951-fixagent-server-let-oh__is_none1-clear-a-config-file-value"></a>

### #5951: fix(agent-server): 让 OH_*_IS_NONE=1 清除配置文件值

- 提交：`6235a41b5b847296e9f8bece1479c060e9a14a5f` (2026-10-17T01:56:40+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5951).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5951)。 家庭：F01、F02、F03、F29、F31、F32。

陈述意图：

> - `env_parser.merge` 获得仅关键字 `none_overrides` 标志（默认 `False`，因此环境解析器内的合并不变）； 设置后，后面的值中的显式 `None` 会替换前面的值，而 `MISSING` 仍然保留它。
> - `load_config` 将文件上的环境与 `none_overrides=True` 合并。 环境数据中不存在没有 `OH_*` 变量的字段，因此文件值保持不变。
> - 地图项目符号 `F31.config-null-override`：`# bug` 标记和“已知错误”标签被删除，散文和空闲 - TTL 陷阱/配置行重写为固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`
- `openhands-agent-server/openhands/agent_server/config.py`
- `openhands-agent-server/openhands/agent_server/env_parser.py`
- `tests/agent_server/test_config.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5935](https://github.com/OpenHands/software-agent-sdk/issues/5935): [Bug]: OH_{FIELD}_IS_NONE1 不能 null 在中设置了一个值智能体- 服务器配置文件 - 当前状态关闭，关闭于2026-10-16T23:56:42Z。

> - [ ] `OH_<FIELD>_IS_NONE=1` 将可空字段设置为 `None`，即使配置文件设置了该字段（环境 null 会覆盖文件值，就像任何其他 `OH_*` 值一样）。 - [ ] 字段没有任何 `OH_*` 变量，则保留文件值； 非 null `OH_<FIELD>` 仍然取代它。 - [ ] 在环境解析器内部合并（e.g. `str \| None` 解析器的联合）没有改变。 - [ ] `tests/agent_server/test_config.py` 中的单元测试涵盖了文件值加 `_IS_NONE` 的情况。 - [ ] 地图项目符号 `F31.config-null-override` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因： - `load_config` (`openhands-agent-server/openhands/agent_server/config.py:564-585`) 将两个源与 `merge(file_data, env_data)`（第 581 行）结合起来。 - `env_parser.merge` (`openhands-agent-server/openhands/agent_server/env_parser.py:360-383`) 每当后一个值是 `None` 时返回前一个值（“优先考虑当前值而不是缺失值”，第 380-381 行）。 该规则适合合并多个环境解析器的输出，但在 `load_config` 中，它删除了 `NoneEnvParser.from_env`（第 81 行）为 `_IS_NONE=1` 返回的显式 `None`。 `env_data` (`MISSING`) 中不存在没有环境变量的字段，因此它们不受影响。 F31 陷阱还注意到 `OH_CONVERSATION_IDLE_TTL_SECONDS_IS_NONE=1` 的结果，仅当文件未设置 TTL 时才禁用空闲逐出。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5951#issuecomment-6159557508)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5951#pullrequestreview-5512677813)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 结论：已批准范围检查：更改位于此存储库拥有的 `openhands-agent-server`（配置加载 + env 解析器）中，并且修复了链接的错误 #5935（`ready-for-dev`、`priority:low`）。 不需要跨存储库或产品方向的决策。 ## 我验证的内容 - **头部匹配** `5353a33b858a08edeff53cfdbca5afe02ad43d84`； PR 已开放，非草稿，无标签，`all-hands-bot` 已请求。 - **CI因为这个头是完全绿色的**：`agent-server-tests`、`cross-tests`、`pre-commit`、`REST API (OpenAPI)`、`Persisted settings`、`windows-tests`、`integration-test`、`smoke-test`和REST全部通过。 - **重点测试通过**：`uv运行pytesttests/agent_server/test_config.pytests/agent_server/test_env_parser.pytests/agent_server/test_cors.pytests/agent_server/test_init_rout

<a id="5840-fixagent-server-answer-422-for-a-malformed-id-on-scoped-bash-routes"></a>

### ＃5840：fix(agent-server)：针对作用域 bash 路由上格式错误的 id 回答 422

- 提交：`8869bcd914af1ef3fb588eeeab7c4b502b83a93e` (2026-10-17T02:06:05+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5840).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5840)。 家庭：F02、F03、F06、F13、F16、F30。

陈述意图：

> `get_bash_event_service` 当在受控请求中缺少运行时状态时，验证引发路径参数自身的错误 (`RequestValidationError`, loc `["path", "runtime_conversation_id"]`)，以便响应与其他受控路由返回的 422 响应体 FastAPI 相同。 有效id不变； 全球`/api/bash/...`路线不变。
> - 单元测试用 `not-a-uuid` 覆盖所有 7 个范围内的 bash 路由。
> - 地图项目符号 `F13.scoped-bad-id`：`# bug` 标记和“已知错误”被删除，散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`
- `openhands-agent-server/openhands/agent_server/dependencies.py`
- `tests/agent_server/test_runtime_router.py`

链接问题接受上下文：

- [#5833](https://github.com/OpenHands/software-agent-sdk/issues/5833)：[Bug]：对话范围内的 bash 路由对于非 UUID 对话 ID（预期为 422）返回 500“‘State’对象没有属性‘runtime_event_service’” — 当前状态已关闭，已关闭 2026-10-17T00:06:06Z。

> - [ ] 所有 7 个会话范围的 bash 路由对于非 UUID `runtime_conversation_id` 都回答 `422`，验证错误位于 `["path", "runtime_conversation_id"]`，并且不记录回溯。 - [ ] 具有有效会话 ID 的作用域 bash 路由以及全局 `/api/bash/...` 路由保持不变。 - [ ] `tests/agent_server/test_runtime_router.py` 中的单元测试涵盖了每个作用域 bash 路由上格式错误的 id。 - [ ] 地图项目符号 `F13.scoped-bad-id` 通过，其 `# bug` 标记被删除。 ### 检查 main 的安装方法 uv 同步 ### 版本 main 位于 6e7a853 ### 附加上下文根本原因： - 作用域路由器是使用路由器依赖项 `bind_local_conversation_runtime` (`openhands-agent-server/openhands/agent_server/runtime_router.py:81`) 构建的，它在 `runtime_conversation_id: UUID` 参数验证后设置 `request.state.runtime_event_service`（第 40 行）。 - 当那个时候参数失败验证，FastAPI 记录错误并跳过该依赖，但继续解析剩余依赖(`fastapi/dependencies/utils.py` `solve_dependencies` `errors.extend(...); continue`)。- bash 端点的依赖 `get_bash_event_service` (`openhands-agent-server/openhands/agent_server/dependencies.py:74-76`) 读取 `request.state.runtime_event_service`，该值从未设置，因此在 FastAPI 返回收集到的 422 之前就引发了 `AttributeError`。- 文件、git 和 vscode 范围的路由没有读取该状态的依赖，因此它们已经回答了 422。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 --

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5840#issuecomment-6157881748)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5840#pullrequestreview-5512682694)：_此评论由 AI 智能体 (OpenHands) 发布。_ 此存储库的范围是正确的：修复位于此存储库拥有的智能体-服务器 REST 表面 (`openhands-agent-server/.../dependencies.py`) 中，并且它是有界的格式错误输入边缘情况，而不是产品/架构决策。 **我目前的主干上验证了**（`bf333281`和CI都为绿色，没有失败的检查）：- 根因是真实的，并且与关联的缺陷匹配：路由器依赖`bind_local_conversation_runtime`（`runtime_router.py:81`）验证`runtime_conversation_id: UUID`，只有在设置`request.state.runtime_event_service`（`runtime_router.py:40`）之后才会设置。 当那个路径参数失败时，FastAPI 记录错误并`continue`，但继续解决端点的剩余依赖项(`fastapi/dependencies/utils.py` `solve_dependencies`)，因此旧的无条件 `require` 语句仍然有效

<a id="5901-fixsdk-reject-skill-installs-with-unparsable-frontmatter-as-invalid"></a>

### ＃5901：fix(sdk)：拒绝技能安装，不可解析的前置元数据无效

- 提交：`cab7bb4b29476cf4a70150f5f94ba97f22766b9a` (2026-10-17T02:07:48+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5901).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5901)。 家庭：F25。

陈述意图：

> - `_load_skill_from_dir` (`openhands-sdk/openhands/sdk/skills/installed.py`)，技能安装路径使用的加载程序，将 `yaml.YAMLError` 转换为 `SkillValidationError`，匹配 `skill.py` 中的目录加载已经处理 YAML 错误的方式。 路由器不需要更改：它已经将 `SkillValidationError` 映射到 422。
> - `tests/sdk/skills/test_installed_skills.py` 中的单元测试：`install_skill` 引发 `SkillValidationError` 且不安装任何内容。
> - 地图项目符号 `F25.install-bad-frontmatter`：`# bug` 标记和“已知错误”标签被删除，散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md`
- `openhands-sdk/openhands/sdk/skills/installed.py`
- `tests/sdk/skills/test_installed_skills.py`

链接问题接受上下文：

- [#5894](https://github.com/OpenHands/software-agent-sdk/issues/5894): [Bug]: SKILL.md 的 POST /api/skills/install 与不可解析的 YAML 前置元数据返回 500 而不是 422 — 当前状态已关闭，已关闭 2026-10-17T00:07:49Z。

> - 具有不可解析的 YAML 前置元数据的 SKILL.md 的 [ ] `POST /api/skills/install` 返回具有现有无效技能详细信息的 `422`，并且未安装任何内容。 - [ ] SDK `install_skill(...)` 为该输入引发 `SkillValidationError`（由 `tests/sdk/skills/test_installed_skills.py` 中的单元测试覆盖）。 - [ ] 地图项目符号 `F25.install-bad-frontmatter` 通过，其 `# bug` 标记被删除。 ### 检查主版本中的安装方法 uv 同步 ### 版本 main 在 6e7a853 ### 附加上下文根本原因： - `install_skill_endpoint` (`openhands-agent-server/openhands/agent_server/skills_router.py:343-382`) 将 `SkillFetchError`/`ExtensionFetchError` 映射到 400，仅将 `SkillValidationError` 映射到 422。 - 安装路径通过 `SkillInstallationInterface.load_from_dir` -> `_load_skill_from_dir` (`openhands-sdk/openhands/sdk/skills/installed.py:46-51`) -> `Skill.load` -> 加载获取的技能`_load_agentskills_skill`，其`frontmatter.load(...)`（`openhands-sdk/openhands/sdk/skills/skill.py:408`）让`yaml.YAMLError`逃脱。 - 项目/目录加载已将 YAML 错误视为不良技能（`skill.py:1128`、`:1143` catch `yaml.YAMLError`），因此安装路径不一致。 建议修复：在`_load_skill_from_dir`中，将`yaml.YAMLError`转换为`SkillValidationError`（安装，然后将其映射到422，无需更改路由器）。 相关：如果一个技能的来源变得不可获取，那么刷新该技能也会返回500，这是同一个伞下的另一个项目（刷新端点没有任何错误映射）。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于 #

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5901#issuecomment-6158726769)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5901#pullrequestreview-5518630810)_这篇评论是由AI发布的智能体 (OpenHands## 范围这个更改应该在这里。 仓库拥有  Python  SDK 和 Agent Server包括技能行为和标准 REST  API (`AGENTS.md` -> 跨仓库边界）。 它修复了一个 bug 在  `openhands-sdk/openhands/sdk/skills/installed.py` and its 回归测试，关联的 issue #5894 正在打开 `bug`, `priority:low`, and `ready-for-dev`. 无需维护者/产品决策。## 我在 HEAD 上验证了什么 `8ba2cd2` - **根本原因和解决方案是正确的。**  `frontmatter.load` 提出了 `yaml.parser.ParserError` 对于报告的输入，它是一个子类的 `yaml.YAMLError` 已被确认为 [confirmed in the] 工作区 venv). `_load_skill_from_dir` 现在将其转换为 `SkillValidationError`该端点已弃用。 确保源包含有效的

<a id="5885-fixsdk-drop-bedrock-only-ids-from-the-supported-model-list"></a>

### ＃5885：fix(sdk)：从支持的模型列表中删除仅限基岩的ID

- 提交：`acf55bcd26729d3f9212d5d5334047b6cd595d2a` (2026-10-17T02:09:09+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5885).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5885)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - `get_supported_llm_models` 现在会丢弃 LiteLLM 的模型成本映射文件（`litellm_provider` `bedrock` `bedrock_converse` `bedrock_mantle`），除了 `bedrock` 前缀的 id，而不是添加更多的字符串启发式。 配置凭据时 (`bedrock/<modelId>`)，AWS 中列出的基岩模型保持不变。 这也适用于SDK的`UNVERIFIED_MODELS_EXCLUDING_BEDROCK`。
> - Two 单元测试 in `tests/sdk/llm/test_model_list.py`.
> - `F23.models-no-bedrock` 地图项目符号失去了已知错误标记； 它的散文和一句提到区域前缀基岩 ID 的陷阱行现在描述了固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F23-llm-catalog-and-connections.md`
- `openhands-sdk/openhands/sdk/llm/utils/unverified_models.py`
- `tests/sdk/llm/test_model_list.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5882](https://github.com/OpenHands/software-agent-sdk/issues/5882): [Bug]: GET /api/llm/models?provider=deepseek|anthropic 列出 AWS 仅基岩 id (deepseek.r1-v1:0, anthropic.claude-...-v1:0) — 当前状态已关闭，已关闭 2026-10-17T00:09:11Z。

> - [ ] `get_supported_llm_models()` 不带 AWS 凭据，除了现有的 `bedrock` 前缀过滤器之外，不返回其 LiteLLM 元数据 (`litellm.model_cost[id]["litellm_provider"]`) 命名基岩提供商的 id。 - [ ] `GET /api/llm/models?provider=deepseek` 和 `?provider=anthropic` 未列出 `deepseek.*` / `anthropic.*` 基岩 ID，但仍列出提供商自己的 ID。 - [ ] 配置凭据时 AWS 中列出的基岩模型 (`bedrock/<modelId>`) 不变。 - [ ] `tests/sdk/llm/test_model_list.py` 中的聚焦单元测试涵盖了这一点。 - [ ] 地图项目符号 `F23.models-no-bedrock` 通过，其 `# bug` 标记被删除。 ### 检查 main 中的安装方法 uv 同步 ### 版本 main 位于 6e7a853 ### 附加上下文根本原因： - `openhands-sdk/openhands/sdk/llm/utils/unverified_models.py:71-73`：`get_supported_llm_models` 仅删除以 `bedrock` 开头的 id。 LiteLLM 的模型成本地图列出了大多数没有该前缀（`deepseek.r1-v1:0`、`us.anthropic.claude-...`）、带有 `litellm_provider: "bedrock"` 或 `"bedrock_converse"` 的基岩模型。 - `openhands-sdk/openhands/sdk/llm/utils/unverified_models.py:147`：当没有 `/` 时，`_extract_model_and_provider` 将第一个 `.` 之前的文本视为提供者，因此 `deepseek.r1-v1:0` 归档在 `deepseek` 下，`anthropic.claude-...` 归档在 `anthropic` 下。 - `openhands-agent-server/openhands/agent_server/llm_router.py:135-143`: `list_models` 按提取的提供商过滤该列表。 建议的修复：使用LiteLLM自己的提供者元数据（`litellm.model_cost[id]["litellm_provider"]`）来删除基岩 

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5885#issuecomment-6158551626)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5885#pullrequestreview-5517050648)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评估更改在此存储库的范围内（它修复了 `openhands-sdk` 中的 `get_supported_llm_models`，支持 `GET /api/llm/models`），并且链接的问题 #5882 是标记为 `ready-for-dev` 的错误。 未发现材料正确性、安全性、兼容性或接受性缺陷。## 验证已完成 - 检出精确的头 `5bc90fb7186e349643789aafa754dfbd8c2c9821` 并确认它与 PR 头匹配。- 对于这个头的所有 GitHub 检查动作都是绿色的。- `uv run pytest tests/sdk/llm/test_model_list.py` - 14 项通过。 当修复被回滚到基线 `6e7a8532` 时，这两个新测试失败了，但在分支 `uv run pytest tests/agent_server/test_llm_router.py tests/sdk/llm` 上却通过了，因此它们是真正的回归保护。 只有两个失败（tests/sdk/llm/auth/t）

<a id="5884-fixsdk-expand--in-oh_persistence_dir-for-the-meta-profile-store"></a>

### ＃5884：fix(sdk)：在OH_PERSISTENCE_DIR中展开〜以获取元配置文件存储

- 提交：`3adf42f6377b570dfea53cc02bc669e1515f18f8` (2026-10-17T02:10:21+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5884).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5884)。 族：F04、F06、F07、F09、F20、F22、F23、F30、F33、F34。

陈述意图：

> - `default_meta_profile_dir()` (`openhands-sdk/openhands/sdk/llm/meta_profile_store.py`) 现在返回 `get_user_persistence_dir() / "meta-profiles"`，因此 `~` 被扩展，并且相对值与每个其他商店完全相同地锚定。 它仍然在调用时进行评估，因此路由器 `launch.py` 和裸 `MetaProfileStore()` 会按原样拾取它。
> - `OH_PERSISTENCE_DIR='~/state'` 新增单元测试。
> - `F22.persistence-dir` 地图项目符号删除了其 `# bug` 标记和“已知错误”标签； 散文和陷阱现在描述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F22-meta-profiles.md`
- `openhands-sdk/openhands/sdk/llm/meta_profile_store.py`
- `tests/sdk/llm/test_meta_profile_store.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5878](https://github.com/OpenHands/software-agent-sdk/issues/5878): [Bug]: 以 OH_PERSISTENCE_DIR='~/x'' 时，meta-profiles 写入 '<server cwd>/~/x/meta-profiles'' 而不是展开的目录 — 当前状态已关闭，关闭于 2026-10-17T00:10:23Z。

> - [  ]  `default_meta_profile_dir()` resolves `OH_PERSISTENCE_DIR` 同其他商店一样（重用） `get_user_persistence_dir()`, 所以 `~` 路径被扩展，相对路径被锚定 [  ] A 单元测试覆盖 `OH_PERSISTENCE_DIR` 带有前缀的 `~`. - [  ] 的 `F22.persistence-dir` 子弹通过它的 `# bug` marker removed. ### 安装方法请输出简体中文译文 `uv sync` 在主版本 6e7a8532ef4426da08b5c06dd57cf4795303be01 的 checkout 中上下文根本原因： `openhands-sdk/openhands/sdk/llm/meta_profile_store.py:41-43`, `default_meta_profile_dir()` 返回 `Path(os.environ["OH_PERSISTENCE_DIR"]) / "meta-profiles"` without `expanduser()` 或锚定，不同于 `get_user_persistence_dir()` 在 `openhands-sdk/openhands/sdk/utils/path.py:32`，其中设置和 LLM  callers `openhands-agent-server/openhands/agent_server/meta_profiles_router.py:47`, `openhands-agent-server/openhands/agent_server/launch.py:71`, and bare `MetaProfileStore()`. 相关：  https://github.com/OpenHands/software-agent-sdk/issues/3835  /  https://github.com/OpenHands/software-agent-sdk/pull/3836  (添加了 ) `OH_PERSISTENCE_DIR` 支持元元档  https://github.com/OpenHands/software-agent-sdk/issues/3815.  由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5884#issuecomment-6158518958)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5884#pullrequestreview-5516489839)_这篇评论是由AI发布的智能体 (OpenHands)._ ## Review — PR #5884 **范围：** 在范围内。 `default_meta_profile_dir()` 居住在 SDK，及其唯一的消费者（ 智能体-服务器元配置路由器 `launch.py`, and bare `MetaProfileStore()`这些都在这个仓库里。 没有交叉回购所有权问题。 **请输出简体中文译文。**  `default_meta_profile_dir()` 现在返回 `get_user_persistence_dir() / "meta-profiles"` 而不是携带自己的 `Path(os.environ["OH_PERSISTENCE_DIR"])` 复制。 Call-time evaluation被保留，因此路由器， `launch.py`, and bare `MetaProfileStore()` 所有都选择了相同的解决方法 `settings.json`, LLM profiles 智能体个人资料和技能缓存。 **我进行了验证，结果是 b1f62cde。** - 生活，真实地进行智能体-server 入口 (`python -m openhands.agent_server` 与 `HOME=<tmp>/home`, `OH_PERSISTENCE_DIR=~/qa

<a id="5867-fixagent-server-reject-mcp-oauth-callback-urls-with-a-bad-port-as-400"></a>

### #5867: fix(agent-server) 拒绝 MCP OAuth 回调 URLs 以 400 作为不正确的端口

- 提交：`e5a1602e3bbc8b55571b7777bd6b6142101f11ad` (2026-10-17T02:12:02+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5867).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5867)。 家庭：F19。

陈述意图：

> - `_validate_callback_url` 将 `ValueError` 从 `.port` 转变为 `400 Unexpected OAuth callback URL`，并将 `ValueError` 从 `urlparse` 本身转变为 e.g。 `http://[::1/callback`，未闭合的 IPv6 括号）进入 `400 Invalid OAuth callback URL`。 有效的 URLs 和现有的检查保持不变。 工作一直在等待。
> - `tests/agent_server/test_mcp_router.py`（端口 99999、端口 `abc`、格式错误的 IPv6）中的新参数化测试断言 400、详细信息，并且作业保持 `authorizing`。
> - 地图项目符号 `F19.oauth-callback-bad-port`：`# bug` 标记和“已知错误”已删除，这两个帖子现在检查 400 个细节，将散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F19-mcp.md`
- `openhands-agent-server/openhands/agent_server/mcp_router.py`
- `tests/agent_server/test_mcp_router.py`

链接问题接受上下文：

- [#5863](https://github.com/OpenHands/software-agent-sdk/issues/5863): [Bug]: MCP OAuth 回调 URL 端口 99999 或非数字端口回答 500 而不是 400 — 当前状态已关闭，已关闭 2026-10-17T00:12:04Z。

> - [ ] 具有超出范围或非数字端口的回调 URL 用 `detail: "Unexpected OAuth callback URL"` 回答 `400`，并且作业将继续等待同意。 - [ ] 范围内端口和匹配的回调 URL 的行为与今天一样。 - [ ] `tests/agent_server/test_mcp_router.py` 覆盖两个端口。 - [ ] 地图项目符号 `F19.oauth-callback-bad-port` 通过，其 `# bug` 标记被删除。 ### 检查 main 中的安装方法 uv 同步 ### 6e7a853 处的 main 版本 ### 附加上下文根本原因，在 `openhands-agent-server/openhands/agent_server/mcp_router.py` 中：`_validate_callback_url`（第 746 行）与 `parsed.port != expected_parsed.port`（第 760 行）进行比较。 `urllib.parse.SplitResult.port` 对于 0-65535 之外的端口或非数字端口引发 `ValueError`，没有任何东西捕获它，通用处理程序将其转换为 500。 对于格式错误的 IPv6 主机，这同样适用于 `urlparse` 本身，例如 `http://[::1/callback`（`ValueError: Invalid IPv6 URL`，第 747 行），它适合 `400 Invalid OAuth callback URL`。 相关：同一路由中的同级项`F19.oauth-callback-replay`（转发回调时出现传输层错误）被单独跟踪。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5867#issuecomment-6158327530)

<a id="5916-fixagent-server-drop-upstream-date-and-server-from-proxied-responses"></a>

### ＃5916：fix(agent-server)：从代理响应中删除上游日期和服务器

- 提交：`7abcd3bab78f988b2f2ca2485f4626a5484ce313` (2026-10-17T02:13:25+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5916).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5916)。 家庭：F12、F29。

陈述意图：

> - `proxy_http` (`docker_runtime/proxy.py`) 从它返回的响应中删除上游 `date` 和 `server` 标头，因此 uvicorn 的一对是唯一的。 更改仅在响应端：`_filter_headers` 和请求标头转发未受影响。
> - `proxy_http` 与 Docker 运行时会话代理共享，其内部 Agent Server 也发送 `date`/`server`，因此相同的重复在那里消失。
> - `tests/agent_server/docker_runtime/test_proxy.py` 中新增单元测试； `F29.proxy-response-headers` 地图项目符号失去了已知错误标记。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md`
- `openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py`
- `tests/agent_server/docker_runtime/test_proxy.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5914](https://github.com/OpenHands/software-agent-sdk/issues/5914): [Bug]: 代理画布前端后端响应携带两个 Date 和两个 Server 头 — 当前状态关闭，关闭于 2026-10-17T00:13:27Z。

> - [ ] 通过 Canvas 应用程序后端桥代理的响应携带一个 `Date` 和一个 `Server` 标头（Agent Server 自己的）。 - [ ] 转发到上游的请求标头未更改。 - [ ] `tests/agent_server/docker_runtime/test_proxy.py` 中的单元测试涵盖了响应标头 `proxy_http` 返回。 - [ ] 地图项目符号 `F29.proxy-response-headers` 通过，其 `# bug` 标记被删除。 ### 检查 main 中的安装方法 uv 同步 ### 版本 main 位于 6e7a853 ### 附加上下文根本原因：`openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py` 中的 `proxy_http` 使用 `headers=_filter_headers(upstream.headers)`（第 175 行）构建响应。 `_filter_headers`（第 58-59 行）仅丢弃逐跳/凭证集 `_HOP_BY_HOP_HEADERS`（第 32-50 行），因此上游 `date` 和 `server` 通过。 然后 uvicorn 在前面添加自己的 `date` 和 `server` 默认标头，而不进行重复删除（`uvicorn/protocols/http/h11_impl.py:471`，`httptools_impl.py:479`：`self.default_headers + list(message["headers"])`）。 `_filter_headers` 由请求和响应方向共享，`proxy_http` 由 Canvas 桥 (`canvas_extensions/bridge.py:467`) 和 Docker 运行时会话代理 (`docker_runtime/routers.py:102`) 共享，其内部 Agent Server 也发送 `date`/`server`，因此那里发生相同的重复。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5916#issuecomment-6159040303)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5916#pullrequestreview-5512474921)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 结论在头部 `1cb0168` 上未发现重大正确性、安全性或兼容性缺陷。 ## 范围此更改属于此存储库：它修复了 `openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py` 中的 `proxy_http`、Agent Server 自己的代理，以及链接的问题 #5914（标签 `bug`、`priority:low`、`ready-for-dev`、打开）针对同一文件。 ## 我在当前主干上验证了什么 - **修复及其影响范围。** `_RESPONSE_DROP_HEADERS = {"date", "server"}`仅应用于响应路径 (`headers={...}` 在第179-183行），而 `_filter_headers`（第120行，请求方向）未改变，因此请求转发未受影响，因为问题的接受标准要求。 `proxy_http` 由 Canvas 应用程序后端 b 共享

<a id="5826-fixagent-server-read-agent_final_response-from-the-active-branch"></a>

### ＃5826：fix(agent-server)：从活动分支读取agent_final_response

- 提交：`079d410db4fe17ccfe28b80f58b12676cf854c7c` (2026-10-17T02:25:16+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5826).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5826)。 族：F05、F06、F07、F08、F09、F10、F11、F12、F31。

陈述意图：

> - `EventService._get_agent_final_response_sync` 现在将 `state.active_branch()` 传递到 `get_agent_final_response`。 这涵盖了 REST 路由和 OpenAI 兼容网关 (`openai/service.py`)，它们都经过 `EventService.get_agent_final_response`。 SDK 自己的调用者（任务管理器、委托、智能体挂钩）读取从未导航的新子对话，因此它们没有改变； TypeScript客户端只是调用路由。
> - 真实 `LocalConversation` 上的新单元测试：返回答案，向后导航给出 `""`，向前导航到答案再次返回。 现有的模拟的测试现在存根 `active_branch()`。
> - 特征图：`F10.navigate-final-response` 失去其 `known bug` 标签和 `# bug` 标记； 散文现在陈述了预期的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `tests/agent_server/test_conversation_response.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5822](https://github.com/OpenHands/software-agent-sdk/issues/5822): [Bug]: agent_final_response 仍然返回废弃分支的答案 HEAD 后端 — 当前状态关闭，关闭于2026-10-17T00:25:17Z。

> - [  ]  `agent_final_response` (and the) OpenAI兼容网关，使用相同的 `EventService.get_agent_final_response`只考虑活动分支上的事件 [  ] 聚焦的单元测试覆盖了在导航之前覆盖的智能体答案（返回 ） `""`) 和正常线性情况 (未改变) [  ] 地图弹珠 `F10.navigate-final-response` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 `uv sync` 在主版本 6a298a48fcdb06c3bf5835d648a7d8b4d3d31cf5 ### 其他上下文根本原因： `EventService._get_agent_final_response_sync` (openhands-agent-server/openhands/agent_server/event_service.py呼叫：2203 `get_agent_final_response(self._conversation._state.events)`, i.e. 整个的 `EventLog`, instead of `self._conversation._state.active_branch()` as `LocalConversation` 用于标题生成、滞留检测和待办事项（openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py). 对话树/导航 API 带着#3922和#3923来。 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5826#issuecomment-6157712499)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5826#pullrequestreview-5512658173): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围属于此存储库：智能体服务器拥有此 REST 合约，引用的问题 #5822 (`bug`, `priority:low`, `ready-for-dev`) 是此存储库的跟踪错误。 不需要产品/架构决策。 ## 验证（head `e35e8e8c`） - Head 仍然是 `e35e8e8c916f7b9fd37b48b17898f006ec9c9f02`； PR打开，不是草稿，没有标签。 - 该头上的所有检查运行都是绿色的，包括`agent-server-tests`、`cross-tests`、`sdk-tests`、`pre-commit`、`REST API (OpenAPI)`、`agent-server-api`和`security`。 - `uv run pytest tests/agent_server/test_conversation_response.py` -> 8 通过（包括新的真实 `LocalConversation` 测试）。 - `uv run pytest tests/agent_server -k openai` -> 17 已通过。 - 重读链接问题：#5822 用 `bug`、`priority:low`、`ready-for-dev` 打开

<a id="5812-docstypescript-describe-the-pre-run-200-and-defer-switchacpmodel-behaviour"></a>

### #5812: docs(typescript): 描述预运行 200-and-defer switchAcpModel 行为

- 提交：`9ad70fedddc4e7e68df476a30f9c464b4ca1081c` (2026-10-17T02:34:06+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5812).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5812)。 家庭：F34。

陈述意图：

> - 重写 `switchAcpModel` 文档字符串：通过 `session/set_model` 进行实时会话切换； 在第一次运行之前，服务器回答 200 并存储第一个会话的模型； 非 ACP 对话得到 400。
> - 从 `F09.ts-client-acp-docs` 地图项目符号中删除 `# bug` 标记，为新措辞添加肯定检查，并更新 F09 陷阱行。
> - 无需更改代码； Python 文档字符串 (`conversation_router.py`, `LocalConversation.switch_acp_model`) 已经描述了延迟的行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`
- `clients/typescript/src/client/conversation-client.ts`
- `clients/typescript/src/conversation/remote-conversation.ts`

链接问题接受上下文：

- [#3763](https://github.com/OpenHands/software-agent-sdk/issues/3763): ACP: 持久化在预会话模型切换之前丢失模型（switch_acp_model 在第一次run() 之前失去模型）——当前状态关闭，关闭于2026-06-17T09:15:28Z。

> 概述：预会前 ACP 模型切换（更改模型） ACP 谈话 **在第一个 `run()`**）被默默丢失了： `LocalConversation.switch_acp_model` 在模型第一次运行时，它会先提升新值，所以第一次运行时使用的模型实际上是在构建时创建的 `acp_model`. 下游表现为误导性的“成功”状态 OpenHands 和智能体-canvas (芯片显示新模型) 运行使用旧的）或硬 409 错误，具体取决于部署。 这个问题提出要修复它 **在根目录下 SDK** — 持久化

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5808](https://github.com/OpenHands/software-agent-sdk/issues/5808): [Bug]: TS客户端switchAcpModel 文档字符串说服务器在发送第一个消息之前返回409，但实际上返回200并推迟切换——当前状态已关闭，关闭时间2026-10-17T00:34:08Z。

> - [ ] `ConversationClient.switchAcpModel` 和 `RemoteConversation.switchAcpModel` 文档字符串描述了第一次运行之前的 200-and defer 行为，不再提及 409。 - [ ] `F09.ts-client-acp-docs` 地图项目符号通过，其 `# bug` 标记被删除，并且关于陈旧文档字符串的 F09 陷阱行被更新。 ###安装方法`uv sync`在main的checkout中。 ### 版本主要位于 6a298a48fcdb06c3bf5835d648a7d8b4d3d31cf5 ### 附加上下文根本原因：当 #3763 进行会话前切换持久化而不是引发时，为原始 409 行为 (#3390) 编写的文档字符串未更新。 地点：`clients/typescript/src/client/conversation-client.ts:413-419` 和 `clients/typescript/src/conversation/remote-conversation.ts:326-331`。 服务器行为：`openhands-agent-server/openhands/agent_server/conversation_router.py:697-710`、`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1723-1748`。 Python文档字符串已经是正确的。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5812#issuecomment-6157501660)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5812#pullrequestreview-5511606327)_这篇评论是由AI发布的智能体 (OpenHands)._ **范围。** 文档内仅有的更改 `clients/typescript/`这个仓库拥有。 没有代码端点，或更改类型。 此处范围正确； 没有什么可移动的。 **我在头部验证了什么 `f0956f6c`** - 两篇重写文档字符串现在匹配服务器。 `conversation_router.py` (`switch_conversation_acp_model`) 宣布了 400/404/504，[并] 详细描述了 [预启动] 情况已持久化当第一个会话开始时应用，返回 200。 `LocalConversation.switch_acp_model` 和 `EventService.switch_acp_model` 确认相同。 `RemoteConversation.switchAcpModel`'linked' `{@link switchLlm}` 和 `ConversationClient`'linked' `{@link switchLLM}` 都有效，所以文档链接有效。- 没有过时的措辞：`grep -c 'returns 409 before the first mess`

<a id="5802-fixagent-server-reject-a-whitespace-only-conversation-title-on-patch"></a>

### ＃5802：fix(agent-server)：拒绝PATCH上仅包含空格的对话标题

- 提交：`f676088d7a46f7bf6ab15f4b2d6551f8106cc30e` (2026-10-17T02:37:16+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5802).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5802)。 家庭：F04、F08、F10、F11、F12、F13。

陈述意图：

> - `UpdateConversationRequest` 获取 `title` 字段验证器，该字段在修剪后拒绝一个空标题，因此路由在服务运行之前就返回了 `422`，并且存储的标题保持不变。 非空白标题未更改（服务仍会删除它们； `max_length=200`仍然适用）。
> - 新的路由器测试 `test_update_conversation_whitespace_only_title_rejected`（空格和制表符/换行符）断言 `422` 并且该服务永远不会被调用。
> - `F04.patch-whitespace-title` 地图项目符号失去了 `# bug` 标记和“已知错误”标签； 它的散文现在陈述了预期的行为。
> 
> PythonSDK`RemoteConversation`和`clients/typescript`只将标题转发给这个端点，所以服务器端验证器覆盖了它们。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`
- `openhands-agent-server/openhands/agent_server/models.py`
- `tests/agent_server/test_conversation_router.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5799](https://github.com/OpenHands/software-agent-sdk/issues/5799): [Bug]: PATCH  /api/conversations/{id} 返回200，并清除存储的标题 — 当前状态关闭，关闭于2026-10-17T00:37:18Z。

> - 带有仅空白标题的 [ ] `PATCH /api/conversations/{id}` 返回 `422` 并保持存储的标题不变。 - [ ] 正常标题仍然有效，并且在存储之前仍然会删除周围的空白。 - [ ] 聚焦的单元测试覆盖了纯空白标题。 - [ ] 地图项目符号 `F04.patch-whitespace-title` 通过，其 `# bug` 标记被移除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 6a298a4 ### 附加上下文根本原因： - `UpdateConversationRequest.title` (`openhands-agent-server/openhands/agent_server/models.py:514-519`) 有 `min_length=1`，它接受 `" "`。 - `ConversationService.update_conversation` (`openhands-agent-server/openhands/agent_server/conversation_service.py:1807`) 存储 `request.title.strip()`，即 `""`。 - `AutoTitleSubscriber` (`conversation_service.py:2494`) 跳过 `stored.title is not None` 的任何对话，因此清空的标题也会禁用自动标题。 相关：PATCH 未知 ID 状态 (`F04.patch-unknown-id`) 是一个单独的错误。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5802#issuecomment-6157371915)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5802#pullrequestreview-5511512208)_这篇评论是由AI发布的智能体 (OpenHands[_] ## 范围在范围内。 更改仍在 `openhands-agent-server` (这个仓库拥有) Agent Server 及其标准形式 REST  API），并且链接的问题#5799带有 `bug` / `priority:low` / `ready-for-dev`因此，没有产品/架构决策处于开放状态。 这是一个专注于后端的系统验证 fix 的 OpenAPI 表面用于 PATCH title 模式因此，没有改变，所以 `clients/typescript` 镜像无需协调更新。## 评论报告的错误是  `PATCH /api/conversations/{id}` 与 `{"title": " "}` returned `200 {"success": true}` 和已持久化标题为 `""`, whereas `{"title": ""}` 正确拒绝了 `422`. 所提出的修复方案添加了  `field_validator("title")` to `UpdateConversationRequest` 拒绝任何非-`None` 在标题后留空 `.strip()`. 我验证

<a id="5864-fixagent-server-skip-the-workspaces-save-when-a-write-changes-nothing"></a>

### ＃5864：fix(agent-server)：当写入没有改变时跳过工作区保存

- 提交：`478a6f9caebc42e3e2625f741ea73336a2551b90` (2026-10-17T02:41:31+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5864).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5864)。 家庭：F03、F17、F18、F31。

陈述意图：

> - 当 `update_fn` 返回给定的文档时，`FileWorkspacesStore.update` 跳过 `save`； 每个路由的 `apply` 已经返回其输入不变，以进行无操作，因此不需要更改路由器。 实际添加和删除仍然写入（并且仍然在只读存储上回答 500）。
> - `tests/agent_server/test_workspaces_router.py` 中的两个单元测试：拒绝删除新目录不会留下任何文件； `save` 失败，重新添加保持 200，未知删除 404，真正添加 500，并且文件保留其 inode 和 mtime。
> - 删除 `F17.noop-delete-no-file`、`F17.noop-write-untouched` 和 `F17.noop-write-readonly` 的 `# bug` 标记，并将其散文和陷阱行重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F17-workspaces-registry.md`
- `openhands-agent-server/openhands/agent_server/persistence/store.py`
- `tests/agent_server/test_workspaces_router.py`

链接问题接受上下文：

- [#5849](https://github.com/OpenHands/software-agent-sdk/issues/5849): [Bug]: 工作区写入路由，当没有任何变化时重写 workspaces.json； 404 DELETE 创建文件，并在只读存储上无操作写入答案 500 — 当前状态已关闭，已关闭 2026-10-17T00:41:33Z。

> - [  ] A `DELETE` (工作区如果路径未保存，则返回 404 错误，并创建或重写无内容 `workspaces.json`. - [  ] 仅重发已保存的路径工作区或其父母) 返回 200，并不重写文件 [  ] 在存储过程中，服务器无法写入，这些无用的请求仍然保持404/200的响应，而真实的添加请求仍然返回500 `Failed to save workspaces`. - [  ] 实增实减仍然存在持久化包括盖章 `schema_version` 1 用手写文档 [  ]  `tests/agent_server/test_workspaces_router.py` 涵盖了新鲜目录删除和无操作写入 [  ] 地图弹珠 `F17.noop-delete-no-file`, `F17.noop-write-untouched` 和 `F17.noop-write-readonly` 通过他们的 `# bug` 标记已移除 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因： `FileWorkspacesStore.update` (`openhands-agent-server/openhands/agent_server/persistence/store.py:772-788`总是调用 `self.save(updated)` (787) after `update_fn`, 即使每个路由的 `apply` 当没有任何匹配项时，它会将输入保持不变`openhands-agent-server/openhands/agent_server/workspaces_router.py:110, 145, 189, 226`). 删除路由只在之后出现 `store.update` 返回了第162行和第243行，因此失败的保存将404状态码转换为500状态码。 建议的修复：跳过 `save` 当 `update_fn` 返回了它所给的同一个对象。 的 `.workspaces.lock` 由文件创建的锁不是这个问题的一部分。 由第一完整发现的智能体式验证-智能体-server; 追踪到 

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5864#issuecomment-6158210060)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5864#pullrequestreview-5511929674): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 摘要该更改通过在 `update_fn` 返回相同文档 (`updated is not workspaces`) 时跳过 `save` 来修复 `FileWorkspacesStore.update` (`openhands-agent-server/openhands/agent_server/persistence/store.py`) 中报告的 no-op-write 错误。 我验证了`workspaces_router.py`中的所有四个路由`apply`闭包都返回了同一个对象，在`WorkspacesStore.update`的所有调用者中，身份检查是正确的。 树中不存在其他调用者。 ## 验证 - Head `35d3349a5788fc9e3f7a8f8fc08a0f382e2b9d04` 与请求匹配； PR 是开放的，不是草稿，没有标签。 - `uv run pytest tests/agent_server/test_workspaces_router.py` -> 14 已通过。 这两个新测试练习了新鲜目录 404 删除和失败的无操作路径 `save`（重新添加 2

<a id="5851-fixagent-server-document-422-for-an-invalid-secret-name"></a>

### #5851: fix(agent-server): 文档 422 的机密名称无效

- 提交：`07e6e059afd836817d8263d3edb67cb95d5c203e` (2026-10-17T02:44:59+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5851).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5851)。 家庭：F18、F19、F32。

陈述意图：

> - `get_secret_value` 和 `delete_secret` 中的文档字符串现在说 `422 if name format is invalid`。 状态码不变。 （`PUT /api/settings/secrets` 自  https://github.com/OpenHands/software-agent-sdk/pull/5682.  以来已经说过 422）
> - 对于 GET、DELETE 和 PUT，新的参数化测试检查无效名称是否为 422，并且路线的 `/openapi.json` 描述名称为 422 而不是 400。
> - 删除 verify-智能体-server 映射中的 `F18.secret-name-contract` 已知错误标记，并将其散文和陷阱行重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md`
- `openhands-agent-server/openhands/agent_server/settings_router.py`
- `tests/agent_server/test_settings_router.py`

链接问题接受上下文：

- [#5846](https://github.com/OpenHands/software-agent-sdk/issues/5846): [Bug]: GET/DELETE /api/settings/secrets/{name} 文档 400 名称无效，但答案 422 — 当前状态已关闭，已于 2026-10-17T00:45:01Z 关闭。

> - [ ] `get_secret_value` 和 `delete_secret` 的文档字符串（以及 OpenAPI 描述）表示 422 表示无效名称； 状态码本身没有改变。 - [ ] A 单元测试检查每个机密路由的已发布 OpenAPI 描述是否命名了无效名称实际获得的状态。 - [ ] 地图项目符号 `F18.secret-name-contract` 通过，其 `# bug` 标记被移除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因，在 `openhands-agent-server/openhands/agent_server/settings_router.py` 中： - `_validate_secret_name`（第 92 行）引发 `HTTP_422_UNPROCESSABLE_ENTITY`（第 104-105 行），其自身的文档字符串（第 101 行）表示 422。 - `get_secret_value` 文档字符串，第 501 行：`400 if name format is invalid, 404 if secret not found.` - `delete_secret` 文档字符串，第 580 行：`400 if name format is invalid, 404 if secret not found, 500 if file is corrupted.` 没有签入重复声明的 OpenAPI 文档或 TypeScript 客户端文本。 相关：#5682（修复了`PUT`文档字符串），#5623。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5851#issuecomment-6158029851)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5851#pullrequestreview-5511894462)_这篇评论是由AI发布的智能体 (OpenHands._ PR 第5851号，最新版本 `a90f6d132ef803329654bae6a2f52c065384a465` ("fix(agent-server)422 错误，用于无效的文档机密 (name), +36/-14 across 3 files。 该变化对进行了调整 `GET`/`DELETE  /api/settings/secrets/{name}`  文档字符串 — 因此，发布的 OpenAPI 描述 —— 422 伴随的 `_validate_secret_name` 实际上提高了，添加了回归测试，并更新 verify-智能体-server F18 ## 验证 - 范围/所有权：在此处。 路由在  `openhands-agent-server/openhands/agent_server/settings_router.py`这个仓库拥有。 无需跨仓库/客户端重生成：未检入的 OpenAPI 文档重复了这一说法 TypeScript 客户端 (`clients/typescript/src/client/settings-client.ts`) neither asserts nor docume

<a id="5874-fixagent-server-describe-the-real-materialize-report-in-the-seed-docstring"></a>

### ＃5874：fix(agent-server)：描述种子文档字符串中真实的物化报告

- 提交：`fd96074269cee08e8d8da917512b26b8d49c98f6` (2026-10-17T02:50:59+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5874).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5874)。 家庭：F21、F30。

陈述意图：

> - 仅文档字符串：描述实际报告的内容。 没有行为改变。
> - `test_seed_skips_ghost_llm_profile_for_bare_defaults` 现在还固定 `errors` 条目并且在物化主体中缺少 `dangling_llm_profile_ref`。
> - verify-智能体-server 映射：将已知错误标记放在 `F21.dangling-llm-report` 上，并将其散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md`
- `openhands-agent-server/openhands/agent_server/agent_profiles_router.py`
- `tests/agent_server/test_agent_profiles_router.py`

链接问题接受上下文：

- [#5871](https://github.com/OpenHands/software-agent-sdk/issues/5871): [Bug]: _seed_default_llm_profile 文档字符串说材料化报告了dangling_llm_profile_ref，但材料化响应中没有这样的字段——当前状态已关闭，关闭于2026-10-17T00:51:00Z。

> - [ ] `_seed_default_llm_profile` 文档字符串将具体化报告描述为 `valid` False、`llm_profile_resolved` False 和 `errors` 条目，并且不再承诺来自具体化的 `dangling_llm_profile_ref`。 - [ ] 运行时行为没有变化（实现和启动响应相同）。 - [ ] `test_seed_skips_ghost_llm_profile_for_bare_defaults` 固定记录的实现报告（`errors` 条目，无 `dangling_llm_profile_ref` 键）。 - [ ] 地图项目符号 `F21.dangling-llm-report` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因： - `openhands-agent-server/openhands/agent_server/agent_profiles_router.py:181-183`：文档字符串说“实现/试运行将其报告为 `dangling_llm_profile_ref` 而不是提升”。 - `openhands-sdk/openhands/sdk/profiles/resolver.py:109`（`llm_profile_resolved`）和`:496`（`"LLM profile ... not found"`错误）是具体化实际报告的内容； 诊断模型有`dangling_mcp_server_refs`和`dangling_meta_profile_ref`，但没有`dangling_llm_profile_ref`。 - `openhands-sdk/openhands/sdk/launch/errors.py:53`：`dangling_llm_profile_ref`仅存在于发射的422细节中。 另一个方向（向具体化诊断添加 `dangling_llm_profile_ref` 字段）将是 API 添加； 这个问题建议只修正文档字符串。 相关：#4031（引入文档字符串的 Ghost-profile 修复）、#3933。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5874#issuecomment-6158452510)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5874#pullrequestreview-5515574008): _This review was posted by an AI 智能体 (OpenHands)._ ## Review: 文档字符串-only correction, verified against the code **Scope gate.**此更改属于此存储库。 它修正了文档字符串在 `_seed_default_llm_profile` 包中的 Agent Server 错误，以及回归的测试，以及 `verify-agent-server` 的功能图 —— 全部都在根 `AGENTS.md` 跨库边界内拥有。 不需要产品/架构决策； 链接的问题 (#5871, `bug`/`priority:low`/`ready-for-dev`) 明确界定了替代方案 API 添加的范围。 **根据工作区代码进行验证（头`f1feebd6`）。** - `openhands-sdk/openhands/sdk/profiles/resolver.py:105-142` — `AgentProfileDiagnostics` 有 `llm_profile_ref`、`llm_profile_resolved`、`errors`，加上 `dangling_mcp_server_refs` 和 `dangling_meta_profile_ref`，并且 ** 没有 ** `dangling_l

<a id="5966-fixsdk-keep-streamed-deltas-out-of-remoteconversationstateevents"></a>

### ＃5966：fix(sdk)：将流式增量保留在RemoteConversation.state.events之外

- 提交：`8d2c996de5bf4bc558c03451618124c49df24397` (2026-10-17T03:01:34+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5966).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5966)。 家庭：F33。

陈述意图：

> - `RemoteEventsList.create_default_callback()` 跳过 `StreamingDeltaEvent`； 用户回调和可视化工具仍然会收到每个增量。
> - 单元测试：默认值回调将增量保留在缓存事件之外。
> - 地图：从 `F33.conversation-streaming-state` 中删除 `# bug` 标记，并将其散文和陷阱行重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`
- `openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`
- `tests/sdk/conversation/remote/test_remote_events_list.py`

链接问题接受上下文：

- [#4671](https://github.com/OpenHands/software-agent-sdk/issues/4671): [Epic] 流式传输：将线路格式与持久事件记录分开——当前状态打开、关闭——。

> - [ ] 第 0 步基线落地 (#4679) — 字节预算是从测量的帧大小分布得出的，而不是猜测。 - [ ] 第 1 步独立修复：#4674 · #4675 · #4676 · #4677 · #4678 · #4077。 - [ ] 步骤 1b 落地 (#4696) - `StreamingDeltaEvent` 不是 `Event`，增量有自己的扇出，线上的框架不变，并且 `receives_streaming_deltas` 消失了。 - [x] 运行时空闲计时器在不产生持久事件的长流期间重置（#4695），并在步骤 1b 之后保持不变。 - [x] 步骤 2 落地 (#4680) - `append_event` 返回其序列号并在持久化之后发布。 - [x] 步骤 3+4 落地 (#4681) — `/sockets/session/{id}` 持久耐用非`Event`信封中的事件，具有光标、分页重播和字节预算准入。 - [x] 第 5 步落地 (#4682) - `StreamContext` 铸造身份； 每个 `ItemStarted` 恰好被一个 `Durable` 或 `ItemAborted` 退休。 - [ ] 第 6 步落地 (OpenHands/OpenHands#16965) — 按事件 ID 排列的画布键槽，`handle-event-for-ui.ts` 不包含文本比较。 - [ ] 第 7 步落地 (#4683) - `StreamingDeltaEvent` 被彻底删除，旧的端点被记录为已弃用。 - [ ] `Event` 在磁盘上始终保持不变：相同的类、相同的 `extra="forbid"`、相同的字节。

- [#4683](https://github.com/OpenHands/software-agent-sdk/issues/4683)：流式传输第 7 步：停止发出 StreamingDeltaEvent 并冻结遗留事件端点 — 当前状态打开、关闭 —。

> - [ ] `StreamingDeltaEvent` 没有建筑工地。 - [ ] A Webhook 接收流式和非流式对话的相同事件计数，路径中没有过滤器。 - [ ] 遗留端点被记录为已弃用并具有删除目标。

- [#5963](https://github.com/OpenHands/software-agent-sdk/issues/5963): [Bug]:RemoteConversation.state.events 保持每个 StreamingDeltaEvent 帧带有流式传输 LLM — 当前状态已关闭，已关闭 2026-10-17T01:01:36Z。

> - [  ] With a 流式传输  LLM, `RemoteConversation.state.events` 包含无 `StreamingDeltaEvent`; 其存储的事件与服务器匹配 [  ] 用户回调 (并且可视化器)仍然接收每一份 `StreamingDeltaEvent`. - [  ] A 单元测试在 `tests/sdk/conversation/remote/` 涵盖默认的回调 with a `StreamingDeltaEvent`. - [  ] 地图弹珠 `F33.conversation-streaming-state` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因： `RemoteConversation._initialize_connection` (`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py:1091`) 注册 `self._state.events.create_default_callback()` 作为套接字回调，and that 回调 (`remote_conversation.py:495-499`) calls `RemoteEventsList.add_event` 对于每一件事，包括瞬时事件 `StreamingDeltaEvent` 框架直接发布给服务器 PubSub (`openhands-agent-server/openhands/agent_server/event_service.py:1218-1226`) 不保存它们。 结算过 REST 它们从不返回这些，因此它们只能通过套接字路径进入缓存。 相关更广泛传输层工作（不是同一份报告）：  https://github.com/OpenHands/software-agent-sdk/issues/4671  和  https://github.com/OpenHands/software-agent-sdk/issues/4683;    https://github.com/OpenHands/software-agent-sdk/pull/4700  给差分以各自的扇出，这也会移除这个。 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5966#issuecomment-6159953472)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5966#pullrequestreview-5512811912)：_此评论由 AI 智能体 (OpenHands) 发布。_ 已评论头部 `55c3ee3`（基础 `main`）。 该更改会 `RemoteEventsList.create_default_callback()` 在缓存之前丢弃 `StreamingDeltaEvent`，这是 #5963 的正确最小修复：服务器直接发布差分到 pub/sub，从不持久化它们 (`event_service._publish_stream_delta`。 请参阅`StreamingDeltaEvent` 文档字符串），因此客户端缓存应该与存储的事件日志匹配。 增量仍然到达用户回调和可视化工具，因为 `compose_callbacks` 使用原始事件调用每个回调，并且只有默认的回调提前返回。 `reconcile()`/`_add_event_unsafe()` 从服务器获取，服务器从不存储增量，因此它们也保持干净。 在工作区中执行的验证： - `uv run pytest tests/sdk/conversation/remote/test_remote_events_list.py` -> 1

<a id="5917-fixagent-server-refuse-a-non-gzip-canvas-backend-artifact-with-409"></a>

### ＃5917：fix(agent-server)：拒绝带有 409 的非 gzip 画布后端工件

- 提交：`57c71706e83c83b8f58a6b4efc959f5132cec94b` (2026-10-17T03:03:50+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5917).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5917)。 家庭：F28。

陈述意图：

> - `CanvasExtensionBackendManager.prepare` 将提取中的存档格式错误 (`tarfile.TarError`、`gzip.BadGzipFile`、`EOFError`、`zlib.error`) 转换为 `ValueError("backend artifact is not a valid gzip tar archive")`，因此路由会回答 409。 临时提取目录仍然被删除，并且没有写入批准。
> - 单元测试表示纯字节、gzip-but-not-tar 和截断的 gzip 工件（管理员级别），加上路由的 409。
> - 地图：`F28.prepare-corrupt-archive` 失去其 `# bug` 标记和“已知错误”标签； 该配方现在还检查 409 详细信息。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md`
- `openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py`
- `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py`

链接问题接受上下文：

- [#5910](https://github.com/OpenHands/software-agent-sdk/issues/5910): [Bug]: Canvas 后端准备返回 500 '不是 gzip 文件' 而不是 409 — 当前状态已关闭，关闭于 2026-10-17T01:03:52Z。

> - [ ] 使用不是 gzip tar 存档的 sha256 匹配工件进行准备会返回 `409`，并有原因，而不是 `500`。 - [ ] 没有为该应用程序编写批准文件和提取的工件目录。 - [ ] `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` 中的单元测试涵盖了非 gzip 工件。 - [ ] 地图项目符号 `F28.prepare-corrupt-archive` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### Version main at 6e7a853 ### 附加上下文根本原因： - `CanvasExtensionBackendManager._extract_archive` (`openhands-agent-server/openhands/agent_server/canvas_extensions/backend.py:302`) 使用 `tarfile.open(archive, mode="r:gz")` 打开工件，这会针对非 gzip 字节引发 `tarfile.ReadError`（“不是 gzip 文件”）。 它自己的所有拒绝都是`ValueError`。 - `prepare_canvas_extension_backend_endpoint` (`openhands-agent-server/openhands/agent_server/canvas_extensions_router.py:359-362`) 仅将 `ValueError` 映射到 `409`，因此 `tarfile.ReadError` 作为 `500` 到达通用处理程序。 建议的修复：在 `_extract_archive` 中，将存档格式错误（`tarfile.TarError`，加上截断流在读取过程中引发的 gzip/zlib 错误）转换为 `ValueError("backend artifact is not a valid gzip tar archive")`。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5917#issuecomment-6159100199)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5917#pullrequestreview-5512511330)_这篇评论是由AI发布的智能体 (OpenHands)._ ## Scope Agent Server  Python 在拥有者的仓库中修复 `openhands-agent-server/openhands/agent_server/canvas_extensions/`).  无需跨仓库或产品/架构决策，因此该事项按正常技术审查进行。## 我在 HEAD 上验证了什么 `8fe2c264` - 报告的症状是真实的：准备路线（`canvas_extensions_router.py`) 只映射 `ValueError` 到409，而 `_extract_archive` uses `tarfile.open(..., mode="r:gz")`这引发了  `tarfile.ReadError` / `gzip.BadGzipFile` / `EOFError` / `zlib.error` — None 其中的 `ValueError`. 修复了将提取调用包裹起来的代码 `prepare` 并将其翻译成 `ValueError("backend artifact is not a valid gzip tar archive")`- 该端点已弃用

<a id="5898-fixagent-server-map-profile-store-errors-in-scoped-secrets-list"></a>

### ＃5898：fix(agent-server)：在范围机密列表中映射配置文件存储错误

- 提交：`1396fa7ff6510a28fe9587b1708376f23507cd5b` (2026-10-17T03:04:29+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5898).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5898)。 家庭：F18、F19、F32。

陈述意图：

> - `list_secrets` 现在读取 `store_errors()` 内的范围配置文件，因此路由像智能体-配置文件路由一样回答 400 / 503； 未知的 ID 仍会回答 404，有效的 ID 仍会在列表范围内。
> - `tests/agent_server/test_settings_router.py` 中的两个单元测试（可卸载配置文件 -> 400，锁超时 -> 503）。
> - 功能图 `F18.secret-scope-profile-errors`：`# bug` 标记被删除，散文和陷阱行重写为预期行为，第一个项目符号现在声明 `Requires: F18.secret-put-list-get`（它读取项目符号创建的 `QA_F18_TOKEN` 机密，因此 `--only` 排列失败而不是到达标记）。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md`
- `openhands-agent-server/openhands/agent_server/settings_router.py`
- `tests/agent_server/test_settings_router.py`

链接问题接受上下文：

- [#5632](https://github.com/OpenHands/software-agent-sdk/issues/5632)：[错误]：等待锁定的配置文件或连接存储会冻结整个服务器； /alive 失速长达 30 秒 — 当前状态打开、关闭 —。

> - [ ] 当四个存储中任何一个上的请求等待其锁、`GET /alive` 和不相关路由在 2 秒内应答时。 - [ ] 等待请求在锁超时之后仍然返回 503，并且不写入任何内容。 - [ ] 回归测试保存存储锁并在等待期间断言 `/alive` 答案。 - [ ] 地图项目符号 `F20.store-busy-responsive`、`F21.busy-blocks-server`、`F22.store-busy-responsive`、`F23.store-busy-responsive` 通过并删除了已知错误标记。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 2804c12 ### 附加上下文根本原因：FastAPI 在事件循环上运行 `async def` 端点，并且 `FileLock.acquire(timeout=30)` 使用阻塞睡眠进行轮询，在整个等待过程中保持循环。 - 存储锁（30 秒），在 `openhands-sdk/openhands/sdk/` 下：`llm/llm_profile_store.py:130-146`、`profiles/agent_profile_store.py:71-84`、`llm/meta_profile_store.py:123-140`、`llm/provider_connection_store.py:166-176`。 超时变成 `store_errors()` 中的 503 (`_secrets_exposure.py:127-137`; `meta_profiles_router.py:77` 元配置文件）。 - `async def` 处理程序调用内联存储 (`openhands-agent-server/openhands/agent_server/`): `profiles_router.py:148,170,212,378,400,452`; `agent_profiles_router.py:289,318,367,406,461,496`和`store.load`在`materialize_agent_profile`中的568； `meta_profiles_router.py:124,141,161,190,212`; `provider_connections_router.py:146,159,191,248`。 - 对比：`materialize_agent_profile` 已经通过 `asyncio.to_thread` (`agent_profiles_router.py:578`) 运行 `preview_launch`，并且对话启动执行相同的操作

- [#5883](https://github.com/OpenHands/software-agent-sdk/issues/5883): [Bug]: GET /api/settings/secrets?agent_profile_id= 对于可卸载的智能体配置文件或繁忙的配置文件存储回答 500（智能体-配置文件路由回答 400/503） — 当前状态已关闭，已关闭 2026-10-17T01:04:31Z。

> - [ ] `?agent_profile_id=` 中的可卸载智能体配置文件会回答 400 并出现加载错误，而不是 500。 - [ ] 智能体配置文件存储上的锁超时会回答 503 `Profile store is busy. Please retry.`，而不是 500。 - [ ] 未知 ID 仍会回答 404 `Agent profile not found`； 有效的ID仍然涵盖列表。 - [ ] A 单元测试覆盖了两种错误路径。 - [ ] The `F18.secret-scope-profile-errors` map bullets 通过它们 `# bug` 标记去除。 ### 安装方法 `uv sync` 在主库的检查点中。 ### 版本 main 为 6e7a8532ef4426da08b5c06dd57cf4795303be01 ### 其他上下文根因： `list_secrets` 在 `openhands-agent-server/openhands/agent_server/settings_router.py:466-472` 调用 `AgentProfileStore.name_for_id` 和 `AgentProfileStore.load` 在 `store_errors()` (`openhands-agent-server/openhands/agent_server/_secrets_exposure.py:127`) 之外， 上下文管理器该智能体-profile 路由使用来映射 `ValueError` 到 400 和 `TimeoutError` 到 503。 相关：#5632（持有的存储锁使整个服务器停顿 30 秒； 单独关注，此处未解决）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5898#issuecomment-6158682432)

<a id="5875-fixagent-server-honor-utc-offsets-in-bash-event-timestamp-filters"></a>

### ＃5875：fix(agent-server)：尊重 bash 事件时间戳过滤器中的 UTC 偏移量

- 提交：`75dec1d3ef1cf1630502b31e83527e8e3301fb18` (2026-10-17T03:04:38+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5875).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5875)。 家庭：F13。

陈述意图：

> - `BashEventService._timestamp_to_str` 现在在格式化之前将感知日期时间转换为 UTC，匹配 UTC 文件名前缀（事件时间戳来自 `utc_now()`）。 朴素边界仍然被解读为UTC。
> - 聚焦单元测试：`+02:00` 边界在 `timestamp__gte` 和 `timestamp__lt` 上，加上简单的情况。
> - 特征图：`F13.timestamp-offset` 项目符号失去了其 `known bug` 标签和 `# bug` 标记，其散文和匹配的陷阱行现在描述了固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md`
- `openhands-agent-server/openhands/agent_server/bash_service.py`
- `tests/agent_server/test_bash_service.py`

链接问题接受上下文：

- [#5870](https://github.com/OpenHands/software-agent-sdk/issues/5870): [Bug]: Bash事件时间戳过滤器忽略时区偏移（+02:00的边界导致2小时晚）——当前状态已关闭，关闭时间2026-10-17T01:04:40Z。

> - [ ] `timestamp__gte` / `timestamp__lt` 带有非 UTC 偏移​​量，在全局和会话范围的 bash 搜索路径上选择与用 `Z` 写入的同一时刻相同的事件。 - [ ] 朴素（无偏移）边界仍被视为 UTC。 - [ ] `tests/agent_server/` 中的焦点单元测试覆盖了偏移边界。 - [ ] 地图项目符号 `F13.timestamp-offset` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因：`BashEventService._timestamp_to_str` (`openhands-agent-server/openhands/agent_server/bash_service.py:71-75`) 使用 `strftime("%Y%m%d%H%M%S%f")` 格式化日期时间，而不将其转换为 UTC。 事件文件名由 `event.timestamp` (`utc_now()`, UTC) 构建而成，搜索比较绑定字符串与这些文件名前缀（行 192-193），因此在另一个偏移量处的可识别绑定被视作本地时间。 修复：在格式化之前将感知日期时间转换为 `_timestamp_to_str` 中的 UTC。 相关： https://github.com/OpenHands/software-agent-sdk/pull/5842 更改`order__gt`同一文件中的分页（独立）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5875#issuecomment-6158488952)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5875#pullrequestreview-5515603414)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围此更改属于此存储库：它修复了此存储库拥有的 `openhands-agent-server` bash 事件过滤行为，并更新了存储库拥有的 `verify-agent-server` 功能图。 ## 我在当前主干分支 `ac37f64d` - ** 中验证了什么 - **修复了正确性.`BashEventService._timestamp_to_str` 现在会调用 `timestamp.astimezone(UTC)` 来处理 aware datetimes 在格式化之前。 事件文件名是根据 `utc_now()` 时间戳生成的，因此 UTC 标准化边界现在可以与 UTC `YYYYMMDDHHMMSSffffff` 前缀正确比较。 我直接确认了基线 vs 固定行为：对于事件在 `10:00Z` 和 `+02:00` 约束为 `11:00+02:00`（09:00Z），基线实现将约束格式化为 `...110000` 并排除事件，而固定实现则不会这样做

<a id="5957-fixtypescript-client-type-gitchangestatus-with-the-servers-wire-values"></a>

### ＃5957：fix(typescript-client)：输入GitChange.status与服务器的连线值

- 提交：`5f2185ed63334dca95a54839848d2518f9d7f513` (2026-10-17T03:07:44+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5957).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5957)。 家庭：F34。

陈述意图：

> - `GitChange.status` (`clients/typescript/src/models/workspace.ts`) 现在是生成合约的 `GitChangeStatus`，因此它不会再次从服务器漂移； `GitChangeStatus`也是从主入口导出的。
> - 测试：`agent-server-contract-types.test.ts` 中的类型级别检查（状态与生成的值相等，也通过 `RemoteWorkspace.gitChanges`），以及 `remote-workspace-git.test.ts` 中的运行时测试（`gitChanges` 返回原始状态）。
> - 地图：`F34.workspace-git-types` 失去其 `# bug` 标记和“已知错误”标签； 散文和陷阱行现在描述的是固定类型。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `clients/typescript/src/__tests__/agent-server-contract-types.test.ts`
- `clients/typescript/src/__tests__/remote-workspace-git.test.ts`
- `clients/typescript/src/index.ts`
- `clients/typescript/src/models/workspace.ts`

链接问题接受上下文：

- [#5947](https://github.com/OpenHands/software-agent-sdk/issues/5947): [Bug]: TypeScript  GitChange.status 已经被添加|修改过|删除|重命名了，但服务器发送了 'ADDED|UPDATED|DELETED|MOVED— 当前状态已关闭，关闭时间：2026-10-17T01:07:46Z。

> - [ ] 导出的 `GitChange['status']` 是 `'MOVED' \| 'ADDED' \| 'DELETED' \| 'UPDATED'`，取自生成的 `GitChangeStatus`。 - [ ] `clients/typescript` 中的单元测试根据生成的合约检查导出的类型，并且 `gitChanges` 返回未更改的线路状态。 - [ ] 地图项目符号 `F34.workspace-git-types` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 其他上下文根本原因：`clients/typescript/src/models/workspace.ts:31` 手动声明从未与服务器匹配的小写状态。 服务器的枚举是`openhands-sdk/openhands/sdk/git/models.py`中的`GitChangeStatus`，生成的合约在`clients/typescript/src/generated/agent-server-schema.ts:5431`中。 `GitChange`从`clients/typescript/src/index.ts:192`重新导出并由`RemoteWorkspace.gitChanges`（`src/workspace/remote-workspace.ts:214`）返回。 这会更改已发布的类型，因此与小写值进行比较的使用者现在将收到编译错误； 这些比较在运行时从未匹配。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5957#issuecomment-6159691140)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5957#pullrequestreview-5512715807)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 正确、最小的修复 — 已批准重新获取头 `1935c7f` 并根据回购指南（`AGENTS.md`、`clients/typescript/AGENTS.md`、`.agents/skills/custom-codereview-guide.md`）审查差异和链接问题 #5947（开放； `bug`, `priority:low`, `ready-for-dev`). **对此进行验证** - `clients/typescript/src/models/workspace.ts`类型`GitChange['status']`作为生成的`GitChangeStatus`（`'MOVED' \| 'ADDED' \| 'DELETED' \| 'UPDATED'`），匹配SDK枚举（`openhands-sdk/openhands/sdk/git/models.py:9`）和生成的合约（`agent-server-schema.ts:5431`）。 This is the issue's primary acceptance criterion. - `GitChangeStatus`从根入口（`src/index.ts:193`）重新导出； 不存在该名称的其他导出，因此不会发生冲突。 - 问题重现者：`co

<a id="6038-fix-use-short-tmux-sockets-for-overlong-paths"></a>

### ＃6038：修复：对超长路径使用短 tmux 套接字

- 提交：`47c50f7e5c6862822990065b6eee23718f5e650e` (2026-10-16T21:11:35-04:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/6038).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-6038)。 家庭：F13、F27、F31、F33。

陈述意图：

> - 使用Agent Server的可唯一字节长度方法来选择一个明确的短`/tmp` tmux套接字路径，当原始路径会超过平台的Unix-套接字限制时，而不修改全局`TMUX_TMPDIR`。
> - 保持套接字创建与选定的套接字路径一起锁定。
> - 在超长的目录下运行真正的独立和池化终端会话； 给共享套接字 Agent Server 测试短暂的临时命名空间，以便他们继续涵盖锁定和清理。

更改的路径：

- `openhands-tools/openhands/tools/terminal/terminal/tmux_terminal.py`
- `tests/agent_server/test_api.py`
- `tests/tools/terminal/test_tmux_pane_pool.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/6038#issuecomment-6224775724)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/6038#pullrequestreview-5554885018)：_此评论由 AI 智能体 (OpenHands) 发布。_ **范围。**这属于这个存储库。 它在`openhands-tools`（这个仓库拥有的终端工具）中更改了tmux套接字路径选择，并且是Agent Server逻辑的直接终端对应物（已经在`main`（`_ensure_server_tmux_tmpdir`在`openhands-agent-server/openhands/agent_server/api.py`）中）。 不涉及跨存储库或产品决策。 **头部验证`0870a753`（Linux，tmux 3.5a，真实tmux，无模拟对象）。** - 实际入口之前/之后：将 `TMUX_TMPDIR` 设置为 100 字节目录，`origin/main` 为 `TmuxTerminal.initialize()` 和 `TmuxPanePool.initialize()` 提高 `libtmux.exc.LibTmuxException: ['error connecting to .../openhands-<32 hex> (File name too long)']`。 在这个头上，相同的脚本成功了：两个终端都创建了一个真实的会话，

<a id="5973-fixagent-server-answer-409-and-keep-state-when-a-write-loses-ownership"></a>

### ＃5973：fix(agent-server)：回答409并在写入失去所有权时保持状态

- 提交：`f621dab57be854aaee3a982c83b6bf34b8ce5705` (2026-10-17T03:13:03+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5973).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5973)。 族：F01、F03、F04、F05、F06、F07、F08、F09、F10、F11、F12、F30、F31、F32。

陈述意图：

> - `EventService.save_meta(stored=None)` 现在使用新的 `StoredConversation`，写入后在租约保护下，只在写入成功后 `self.stored`。持久化首先，正如问题所建议的。 `update_conversation`、`AutoTitleSubscriber`、`update_secrets`构建`model_copy`并传入； `update_conversation` 仅在保存后应用 `ConversationState.tags` 更新。
> - `ConversationOwnershipLostError` 映射到 **409 Conflict**，其中 `detail`“对话由另一个 Agent Server 实例拥有； 写入被拒绝”（位于凭据绑定激活的现有 409 旁边）。 这也将过时所有者的拒绝 `POST .../events` 从 500 变为 409。
> - `F31.fenced-write-no-trace` 地图项目符号删除了其 `known bug` 标记，现在断言状态为 409，并且关于陈旧所有者回答 500 的 F31 陷阱已更新。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md`
- `openhands-agent-server/openhands/agent_server/api.py`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `tests/agent_server/test_auto_title_span_metadata.py`
- `tests/agent_server/test_conversation_service.py`
- `tests/agent_server/test_unhandled_exception_error_id.py`

链接问题接受上下文：

- [#4800](https://github.com/OpenHands/software-agent-sdk/issues/4800): [Bug]: ConversationService在内存中被存储字段被修改过 save_meta() 无失败时回滚 — 当前状态已关闭，关闭于 2026-10-17T01:13:06Z。

> - 当 `save_meta()` 引发时，[ ] `set_conversation_tag` 使 `stored.tags` 保持不变 - 当 `save_meta()` 引发时，[ ] `delete_conversation_tag` 使 `stored.tags` 保持不变 - 当 `save_meta()` 引发时，[ ] `update_conversation` 使 `stored.title` / `stored.tags` 保持不变 - 当 `save_meta()` 引发时，[ ] `AutoTitleSubscriber` 使 `stored.title` 保持不变 - [ ] 由于会话所有权丢失而拒绝写入返回适当的 4xx 而不是未处理的 500。 - [ ] 在拒绝写入之后，GET 仍然报告先前的标题/标签，并且已持久化元数据保持不变。 最干净的解决方法是颠倒顺序——首先写入磁盘，然后更新内存中的状态——而不是事后添加回滚逻辑。 不是拦截器，但值得在所有受影响的站点上一致解决，而不是零敲碎打。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5973#issuecomment-6160438950)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5973#pullrequestreview-5522877638): _该评论由一个AI发布智能体 (OpenHands)._ ## 摘要该修复程序正确地反转了 mutate-then-持久化的顺序，该顺序允许拒绝的写入泄漏到内存元数据中。 `EventService.save_meta(stored=None)` 现在在租约保护下序列化提供的 `StoredConversation`，并仅在写入成功后将其采用为 `self.stored`； `update_conversation`、`AutoTitleSubscriber`和`apply_resume_secrets`构建一个`model_copy`并将其传入。 `update_conversation` 还在保存后移动了 `ConversationState.tags` 突变，因此丢失租约 `PATCH` 使 `meta.json` 和状态都保持不变。 `ConversationOwnershipLostError` 现在映射到 409，而不是落入通用 500 处理程序。 针对当前头进行验证： - 范围：这是一个智能体-服务器错误修复（对话元数据持久化 + REST 错误 m

<a id="5956-fixtypescript-resolve-updateconversation-with-the-updated-conversation"></a>

### ＃5956：fix(typescript)：使用更新的对话解决updateConversation

- 提交：`8cfff960ff3b9de94d9346eac9802405d6af0bed` (2026-10-17T03:21:58+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5956).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5956)。 家庭：F34。

陈述意图：

> - `ConversationManager.updateConversation` 和 `ConversationClient.updateConversation` 将 PATCH 输入为 `Success`，并通过 `getConversation` 读回对话来解决。
> - 两种方法的新单元测试； 现有的 `ConversationClient` 包装测试占了额外的 `GET`。
> - 地图：`F34.manager-update-result` 失去其 `# bug` 标记和“已知错误”标签； 散文和陷阱行现在描述了重读。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `clients/typescript/src/__tests__/api-clients.test.ts`
- `clients/typescript/src/client/conversation-client.ts`
- `clients/typescript/src/conversation/conversation-manager.ts`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5946](https://github.com/OpenHands/software-agent-sdk/issues/5946): [Bug]: TypeScript updateConversation 输入返回 ConversationInfo，但解析为 {success: True} — 当前状态已关闭，已关闭 2026-10-17T01:22:00Z。

> - [ ] `ConversationManager.updateConversation` 和 `ConversationClient.updateConversation` 解析为与其声明的返回类型相匹配的值。 - []标题仍然通过`PATCH /api/conversations/{id}`存储； 服务器的响应契约不变。 - [ ] `clients/typescript/src/__tests__` 中的单元测试涵盖解析值。 - [ ] 地图项目符号 `F34.manager-update-result` 通过，其 `# bug` 标记被删除。 ### 检查 main 中的安装方法 uv 同步 ### 版本 main 位于 6e7a853 ### 附加上下文根本原因： - `clients/typescript/src/conversation/conversation-manager.ts:384-393`：`updateConversation(...): Promise<ConversationInfo>` 调用 `this.client.patch<ConversationInfo>(...)` 并返回 `response.data`。 - `clients/typescript/src/client/conversation-client.ts:430-439`: `updateConversation<TConversation = ConversationInfo>(...)` 做同样的事情。 - 服务器回答`Success`（`openhands-agent-server/openhands/agent_server/conversation_router.py`，`PATCH /api/conversations/{conversation_id}`），`Success`是`clients/typescript/src/generated/agent-server-schema.ts`中的响应类型。 有两种方法可以使它一致：1. 保持声明的类型，并在PATCH后读回对话（增加一个额外的GET，不改变签名）；2. 将声明的类型更改为`Success`（不增加额外的请求，但对调用者来说，如果传递类型参数或将结果读作对话，会引发类型级别的断开）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5956#issuecomment-6159731776)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5956#pullrequestreview-5512668118)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围这是更改的正确存储库。 `clients/typescript/` 与 Agent Server API (根 `AGENTS.md`, `clients/typescript/AGENTS.md`) 相同，修复措施留在客户端库中：它将 `PATCH /api/conversations/{id}` 响应类型为 `Success` 生成的合同实际上声明和解决的，通过 `getConversation` 读取的对话。 无需服务器合同变更、无需仓库移动、无需产品/架构决策。## 发现缺陷未发现材料正确性、安全性、兼容性或接受标准缺陷。 - `ConversationManager.updateConversation` 和 `ConversationClient.updateConversation` 现在发送 `PATCH` 类型的 `Success` 并解决 `getConversation(id)` (`conversation-manager.ts:390-391`)

<a id="5968-fixagent-server-answer-409-when-a-continued-gateway-run-waits-for-confirmation"></a>

### ＃5968：fix(agent-server)：当继续网关运行等待确认时回答 409

- 提交：`804498a61126a90917efebb5c2c25defb53f2cf0` (2026-10-17T03:23:48+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5968).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5968)。 家庭：F30。

陈述意图：

> - `_wait_for_reused_conversation_completion` 现在也返回 `paused` 和 `waiting_for_confirmation`。 它保持相同的守卫（上次的运行被看到 `running`，或者新的事件到达），因此，之前的状态不会提前结束等待。 `_raise_for_terminal_error` 然后回答 409 `Agent run ended with status: <status>`，与新对话得到的答案相同。
> - 新的单元测试 `tests/agent_server/test_openai_gateway_reused_wait.py` 涵盖了立即回答 409 的两种状态以及陈旧状态防护。
> - 地图项目符号 `F30.chat-reuse-confirmation`：删除了 `# bug` 标记和“已知错误”标签，将 `--expect 409,504` 收紧到 `409`，并将散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md`
- `openhands-agent-server/openhands/agent_server/openai/service.py`
- `tests/agent_server/test_openai_gateway_reused_wait.py`

链接问题接受上下文：

- [#5962](https://github.com/OpenHands/software-agent-sdk/issues/5962)：[Bug]：在 waiting_for_confirmation 中停止（或暂停）的持续 OpenAI 网关对话在 120 秒后回答 504，而不是 409 — 当前状态已关闭，已关闭 2026-10-17T01:23:50Z。

> - [ ] 一个持续的网关对话，其运行在 `waiting_for_confirmation` 中停止，并在几秒钟内回答 409 并详细说明 `Agent run ended with status: waiting_for_confirmation`； 与`paused`相同。 - [ ] 在新回合开始运行之前已经是 `waiting_for_confirmation` 或 `paused` 的对话不会提前结束等待（防止上一回合过时状态的防范措施仍然适用）。 - [ ] 完成、错误和卡住的运行保留其当前答案 (200, 500, 500)，并且运行时间超过 120 秒仍答案 504。 - [ ] A 单元测试涵盖 `waiting_for_confirmation` 和 `paused` 上返回的继续对话等待。 - [ ] 地图项目符号 `F30.chat-reuse-confirmation` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因：在连续路径 `_run_agent` 中等待 `_wait_for_reused_conversation_completion` (`openhands-agent-server/openhands/agent_server/openai/service.py:343`)，仅当 `last_status.is_terminal()`（第 359 行）时返回：完成、错误、卡住。 `paused` 和 `waiting_for_confirmation` 不是终端，因此循环轮询直到 120 秒截止日期并引发 504（第 363 行）。 因此，`_raise_for_terminal_error` 的 409 分支（第 379 行）在此路径上无法到达。 新对话等待运行任务（`EventService.wait_for_run_completion`），当运行停止进行确认时该任务结束，因此它们到达 409。 相关：地图项目符号 `F30.chat-reuse-concurrent` ( https://github.com/OpenHands/software-agent-sdk/pull/5948 ) 和 `F30。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5968#issuecomment-6159965900)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5968#pullrequestreview-5512793603)：_此评论由 AI 智能体 (OpenHands) 发布。_范围：此更改属于此存储库。 它修改了智能体-服务器网关行为(`openhands-agent-server/openhands/agent_server/openai/service.py`),其功能映射，以及`tests/agent_server/`下的一个测试，都在根和`openhands-agent-server` `AGENTS.md`描述的Agent Server所有权下。## 评估根因匹配了关联问题：`_wait_for_reused_conversation_completion`仅在`is_terminal()`返回，所以`paused`和`waiting_for_confirmation`在继续路径上从未观察到，分支`409`的`_raise_for_terminal_error`不可达，请求通过固定120秒的截止时间，作为`504`。 此更改添加了 `_STOPPED_RUN_STATUSES`（`PAUSED`、`WAITING_FOR_CONFIRMATION`）并返回现有状态下的这些状态

<a id="5965-fixsdk-deliver-streamed-deltas-to-remoteconversation-token_callbacks"></a>

### ＃5965：fix(sdk)：将流式增量传送到RemoteConversation token_callbacks

- 提交：`b301ee008178ec4a357d3c2bc6370495c6ce1e3f` (2026-10-17T03:27:19+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5965).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5965)。 家庭：F33。

陈述意图：

> - `RemoteConversation.__init__` 接受 `token_callbacks`（作为最后一个命名参数添加，因此位置调用者不受影响）并将其传递给 `_initialize_connection`。
> - 当 token 和回调给出时，一个小型事件回调将每个 `StreamingDeltaEvent` 从套接字转换为 `LLMStreamChunk` (`choices[0].delta.content` / `reasoning_content`)，这种类型是本地对话的 token 回调接收。 当没有token回调通过时，什么都不会改变； 事件回调和 `state.events` 未受影响。
> - 地图：从 `F33.conversation-token-callbacks` 中删除 `# bug` 标记并重写其散文和匹配的陷阱行。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`
- `openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`
- `tests/sdk/conversation/remote/test_remote_conversation.py`

链接问题接受上下文：

- [#4671](https://github.com/OpenHands/software-agent-sdk/issues/4671): [Epic] 流式传输：将线路格式与持久事件记录分开——当前状态打开、关闭——。

> - [ ] 第 0 步基线落地 (#4679) — 字节预算是从测量的帧大小分布得出的，而不是猜测。 - [ ] 第 1 步独立修复：#4674 · #4675 · #4676 · #4677 · #4678 · #4077。 - [ ] 步骤 1b 落地 (#4696) - `StreamingDeltaEvent` 不是 `Event`，增量有自己的扇出，线上的框架不变，并且 `receives_streaming_deltas` 消失了。 - [x] 运行时空闲计时器在不产生持久事件的长流期间重置（#4695），并在步骤 1b 之后保持不变。 - [x] 步骤 2 落地 (#4680) - `append_event` 返回其序列号并在持久化之后发布。 - [x] 步骤 3+4 落地 (#4681) — `/sockets/session/{id}` 持久耐用非`Event`信封中的事件，具有光标、分页重播和字节预算准入。 - [x] 第 5 步落地 (#4682) - `StreamContext` 铸造身份； 每个 `ItemStarted` 恰好被一个 `Durable` 或 `ItemAborted` 退休。 - [ ] 第 6 步落地 (OpenHands/OpenHands#16965) — 按事件 ID 排列的画布键槽，`handle-event-for-ui.ts` 不包含文本比较。 - [ ] 第 7 步落地 (#4683) - `StreamingDeltaEvent` 被彻底删除，旧的端点被记录为已弃用。 - [ ] `Event` 在磁盘上始终保持不变：相同的类、相同的 `extra="forbid"`、相同的字节。

- [#4683](https://github.com/OpenHands/software-agent-sdk/issues/4683)：流式传输第 7 步：停止发出 StreamingDeltaEvent 并冻结遗留事件端点 — 当前状态打开、关闭 —。

> - [ ] `StreamingDeltaEvent` 没有建筑工地。 - [ ] A Webhook 接收流式和非流式对话的相同事件计数，路径中没有过滤器。 - [ ] 遗留端点被记录为已弃用并具有删除目标。

- [#5959](https://github.com/OpenHands/software-agent-sdk/issues/5959): [Bug]: Conversation(token_callbacks=[...]) 与 RemoteWorkspace 默默地忽略回调 — 当前状态已关闭，已关闭 2026-10-17T01:27:21Z。

> - [  ]  `RemoteConversation` 接受 `token_callbacks` 并调用它们一次 `StreamingDeltaEvent` 在事件套接字上收到的，带有 `LLMStreamChunk` 携带德尔塔的 `content` 和 `reasoning_content`. - [  ] 没有 `token_callbacks`行为没有改变。 event 回调仍然收到 `StreamingDeltaEvent` - [  ] A 单元测试下 `tests/sdk/conversation/remote/` 覆盖转发 [  ] 地图弹珠 `F33.conversation-token-callbacks` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文原因：- `openhands-sdk/openhands/sdk/conversation/conversation.py:200` passes `token_callbacks=token_callbacks` to `RemoteConversation`. - `RemoteConversation.__init__` (`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py:724`) 没有 `token_callbacks` 参数； 它落到了 `**_: object` (第749行) 该行永远不会被读取。 `_initialize_connection` (第1053行) 只处理事件回调到的 `WebSocketCallbackClient`. - 服务器发布自身的差异 token  回调 (`openhands-agent-server/openhands/agent_server/event_service.py:1244`, `_token_streaming_callback`因此，数据已经在套接字上。 客户端只需要传递每个 `StreamingDeltaEvent` 到的 token  回调。 相关： 流式传输 epic  https://github.com/OpenHands/software-agent-sdk/issues/4671  和步骤 7  https://github.com/OpenHands/software-agent-sdk/issues/4683  (将退役) `StreamingDeltaEvent` 在旧的套接字上。 然后客户端转发应该

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5965#issuecomment-6159914119)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5965#pullrequestreview-5512798385)：_此评论由 AI 智能体 (OpenHands) 发布。_ 在标题 `bc379ab41c0254ad70e9a3582e2e7cf52bedd937` 处进行了审核（与审核请求相同）。 ** 范围。** 这应该在这个仓库中：它修复了 SDK 的 `RemoteConversation`（`Conversation(agent=..., workspace=RemoteWorkspace(...))` 使用的工厂路径），在 Python SDK 的对话层中。 不需要跨存储库移动或产品决策。 **我目前的主干上验证了什么。** - 该bug和修复方案与代码一致：`Conversation(...)` 已经向前行`token_callbacks` (工厂行 ~200)，并且`RemoteConversation.__init__` 在`**_` 中被吞没了。 头部现在通过 `_initialize_connection` 接受 `token_callbacks`、线程，并附加一个适配器事件回调，将事件套接字中的每个 `StreamingDeltaEvent` 转换为 `

<a id="5877-fixts-client-match-agent-profile-payload-types-to-the-server-models"></a>

### #5877: fix(ts-client): 将智能体-配置文件载荷类型与服务器型号匹配

- 提交：`4fedb7e2b524b5f6d2d5d0efa9be3c03e072da40` (2026-10-17T02:01:50Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5877).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5877)。 家庭：F34。

陈述意图：

> - `clients/typescript/src/models/agent-profile.ts`：声明服务器的Pydantic模型发送的字段（`openhands-sdk/openhands/sdk/profiles/agent_profile.py`，`resolver.py`），并删除`skills`和`resolved_mcp_servers`。 `AgentProfileSaveInput`因此不再提供`skills`。
> - `agent-server-contract-types.test.ts` 断言 `keyof` 四种导出类型与其生成的合约对应项之间相等。 `derive-switch-plan.test.ts` 和 `api-clients.test.ts` 中的测试夹具已更新，现在删除的 `skills: unknown[]` 条目已从 `config/public-type-budget.json` 中删除。
> - 地图项目符号 `F21.ts-payload-types`：删除 `# bug` 标记，并按预期行为重写散文。 子弹还获得了它所缺少的 `Requires: F21.save-create, F21.acp-kind` 行：单独使用 `--only` 运行，它为这些子弹创建的配置文件获得了 404。 生成合同正控制不变。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md`
- `clients/typescript/config/public-type-budget.json`
- `clients/typescript/src/__tests__/agent-server-contract-types.test.ts`
- `clients/typescript/src/__tests__/api-clients.test.ts`
- `clients/typescript/src/__tests__/derive-switch-plan.test.ts`
- `clients/typescript/src/models/agent-profile.ts`

链接问题接受上下文：

- [#5872](https://github.com/OpenHands/software-agent-sdk/issues/5872): [Bug]: TypeScript 客户端的智能体-profile 载荷类型不匹配服务器发送的内容——当前状态已关闭，关闭于2026-10-17T02:01:53Z。

> - [ ] `AgentProfileDiagnostics` 声明服务器 `AgentProfileDiagnostics` 模型的每个字段，不再声明 `resolved_mcp_servers`。 - [ ] `OpenHandsAgentProfile` 声明 `disabled_skills`、`meta_profile_ref` 和 `enable_classify_and_switch_llm_tool`，并且不再需要（或通过 `AgentProfileSaveInput` 提供）`skills`。 - [ ] `ACPAgentProfile` 声明 `acp_startup_timeout`。 - [ ] `clients/typescript` 中的 A 单元测试固定字段列表； 静态检查，型式检查和测试通过。 - [ ] 地图项目符号 `F21.ts-payload-types` 通过，其 `# bug` 标记被删除。 ###安装方法uv同步在main检查中###版本main在6e7a853 ###附加上下文根本原因：服务器型号改变时，手写镜像没有更新。 - `clients/typescript/src/models/agent-profile.ts:68`（`skills: unknown[]`）、`:80-89`（`ACPAgentProfile`，无 `acp_startup_timeout`）、`:133-160`（`AgentProfileDiagnostics`，`:148`处有 `resolved_mcp_servers`）。 - 服务器模型：`openhands-sdk/openhands/sdk/profiles/agent_profile.py:150`（`OpenHandsAgentProfile`、`disabled_skills`、`enable_classify_and_switch_llm_tool`、`meta_profile_ref`）、`:270`（`ACPAgentProfile`、`acp_startup_timeout`）、`:96`（`extra="forbid"`，因此`skills`上的422）； `openhands-sdk/openhands/sdk/profiles/resolver.py:86`（`AgentProfileDiagnostics`）。 - 相关：#4018（将 `skill_refs`/`skills` 替换为 `disabled_skills`）、#3722/#3723（原始 TS 类型）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5877#issuecomment-6158490190)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5877#pullrequestreview-5516546531)：_此审查由 AI智能体（OpenHands）发布。_ **范围。** 属于本仓库：`clients/typescript/` 对应 Agent Server API，且 `verify-agent-server` 功能映射由本仓库维护。 链接问题 #5872 已开放，当前包含 `bug`、`priority:low`、`ready-for-dev`，因此工作已在范围内并准备就绪。 **在头`221c82541ffd7c72ccb884b530d181b4b1e59cad`上验证：** - 四种手写类型的密钥集现在等于它们生成的对应项（`OpenHandsAgentProfile`、`ACPAgentProfile`、`AgentProfileDiagnostics`、`AgentProfileSummary` 与 `OpenHandsAgentProfile`/`AcpAgentProfile`/`AgentProfileDiagnostics`/`AgentProfileInfo`) - 以编程方式进行比较，没有额外或丢失的密钥。 - 新的断言使它们匹配：在 `origin/main` 的 `agent-profile.ts` 上，相同的测试文件因三个 `TS2344` 错误而失败

<a id="5868-fixagent-server-guard-llm-profile-delete-through-the-json-alias"></a>

### ＃5868：fix(agent-server)：通过 .JSON 别名保护 LLM 配置文件删除

- 提交：`8ee5cba234d14f7841b52c3c8259a884a9179fdb` (2026-10-17T04:12:49+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5868).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5868)。 族：F04、F06、F07、F09、F20、F21、F22、F23、F30、F33、F34。

陈述意图：

> - 在`llm_profile_store.py`中添加`canonical_profile_name()`（由`_get_profile_path`使用）。 `profile_refs.py`中的`_scan_referrers`/`_rewrite_refs`比较并写入规范密钥。
> - `profiles_router.py`: `_set_active_profile_if_matches` 比较规范密钥并存储规范新名称，激活记录规范名称。
> - 功能图：删除 `F20.json-alias-guard` 已知错误标记，直接断言 409 和生存，并更新散文和陷阱行。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md`
- `openhands-agent-server/openhands/agent_server/profiles_router.py`
- `openhands-sdk/openhands/sdk/llm/llm_profile_store.py`
- `openhands-sdk/openhands/sdk/profiles/profile_refs.py`
- `tests/agent_server/test_profiles_router.py`
- `tests/sdk/profiles/test_profile_refs.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5861](https://github.com/OpenHands/software-agent-sdk/issues/5861): [Bug]: DELETE /api/profiles/{name}.json删除了一个 LLM引用了的智能体用户（纯名回答 409）——当前状态已关闭，关闭于 2026-10-17T02:12:51Z。

> - [  ]  `DELETE /api/profiles/<name>.json` 答案 `409` 每当命名指针时 `DELETE /api/profiles/<name>` 将会，而该配置也会存活 [  ] 通过别名删除会清空 `active_profile` 当它提及该档案时。 通过别名重命名 `active_profile` and cascades `llm_profile_ref` 与普通名称相同。- [  ] A 单元测试覆盖 FK 锁中的别名 ([])`openhands-sdk/openhands/sdk/profiles/profile_refs.py`和路由器 [  ] 地图弹珠 `F20.json-alias-guard` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文原因：- `LLMProfileStore._get_profile_path` 去掉尾部 `.json` (`openhands-sdk/openhands/sdk/llm/llm_profile_store.py:166`, 所以 `qa-alias.json` 处理文件 `qa-alias.json` profile `qa-alias`. - `_scan_referrers` 比较 `llm_profile_ref` 带有原始名称的（`openhands-sdk/openhands/sdk/profiles/profile_refs.py:66`); 它被用来  `delete_llm_profile` 并遵循重命名递归（`_rewrite_refs`). - `_set_active_profile_if_matches` 比较 `active_profile` 带有原始名称的（`openhands-agent-server/openhands/agent_server/profiles_router.py:136`)，从删除和重命名操作中调用。 相关： 智能体-profile store 本身的身份（map ID）也有相同的后缀不匹配问题 `F21.json-suffix-identity`这是一个独立的修复。 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5868#issuecomment-6158368393)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5868#pullrequestreview-5514387998)_这篇评论是由AI发布的智能体 (OpenHands)._ ## 范围该更改位于存储库内并正确拥有：它修复了 Agent Server  REST profile routes (`openhands-agent-server/openhands/agent_server/profiles_router.py`) and the SDK profile stores/FK helpers (`openhands-sdk/openhands/sdk/llm/llm_profile_store.py`, `openhands-sdk/openhands/sdk/profiles/profile_refs.py`），这正是 `AGENTS.md` 分配给这个仓库。 没有交叉仓库移动或维护者架构决策是必要的 `1d9fd297`) - 再读一遍 PR仍然开放，不是草稿，头不变，没有标签，没有先前的审查或审查线程在这一点上，没有非机器人问题评论。 问题 #5861 正在打开 `bug`/`priority:low`/`ready-for-dev`, 以及其预期行为（alias delete 转换为 409，alias rename/delete 移动 `active_prof

<a id="5953-fixagent-server-post-webhook-events-that-fill-the-buffer-during-an-in-flight-batch"></a>

### ＃5953：fix(agent-server)：在进行中的批处理期间发布填充缓冲区的Webhook事件

- 提交：`e785defbf652f9c819d53d5ab8ea8eeb8332a942` (2026-10-17T04:43:42+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5953).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5953)。 家庭：F04、F05、F10、F12、F31、F32。

陈述意图：

> - `WebhookSubscriber._post_events` 在排空启动时排队的内容后重新检查缓冲区，并在缓冲区再次满时继续发布（计数或 `max_batch_bytes`）。 还有一个请求正在处理中； 失败的 POST 仍然重新排队并将 REST 留给刷新计时器。 一旦队列耗尽，在 POST 期间启动的刷新计时器将被取消（而不是当 `_post_events` 在该计时器内运行时）。 除了共享新的 `_buffer_full()` 检查之外，`__call__` 保持不变。
> - 新的单元测试 `test_events_published_during_post_are_sent_once_buffer_is_full`（阻止第一个 POST，发布两个事件，断言两个批次，并且没有 `close()` 则不运行计时器）。
> - 地图：`F32.buffer-stranded` 子弹失去了 `# bug` 标记和“已知错误”标签； 它的散文、`F32.flush-on-close`散文和陷阱条目现在描述了固定行为。 子弹的行 `sink read ... --expect-min 1 --expect-max 1`（到目前为止正好是一批）断言了 buggy 状态，因此它被丢弃； `F32.buffer-size`已经检查第一批。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `tests/agent_server/test_webhook_subscriber.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5952](https://github.com/OpenHands/software-agent-sdk/issues/5952): [Bug]: Webhook 飞行中的批次发布的事件 POST 等待 flush_delay 尽管缓冲区已满——当前状态已关闭，关闭时间2026-10-17T02:43:44Z。

> - [  ] 填充缓冲区的事件（按数量或大小） `max_batch_bytes`) while a batch POST 正在飞行的帖子将立即发布 POST 返回，无需等待 `flush_delay` 或 `close()`. - [  ] 最多一个 Webhook 每个订阅者正在发送的请求。 失败 POST 仍然保留了队列中的事件，以便在刷新定时器后执行 [  ] A 单元测试在 `tests/agent_server/test_webhook_subscriber.py` 涵盖在阻塞期间发生的事件 POST, 无需调用 `close()` 在计数之前 [  ] 地图弹珠 `F32.buffer-stranded` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因，在 `openhands-agent-server/openhands/agent_server/conversation_service.py` (`WebhookSubscriber`): - `__call__` 当缓冲区满但 `_post_lock` 在第2595行被持有（该行），只会启动刷新计时器并返回 `_post_events` (2613行) 只有排水 `events_remaining = len(self.queue)` 当它开始时（行 2618），因此在其中排队的事件 POST 被遗弃。 现有的测试 `test_concurrent_event_delivery_has_one_request_in_flight` calls `close()` 在计数之前，它隐藏了它。 相关：同一家族中的慢接收项`F32.slow-receiver`), 关于内联的 POST 抓住未来的发布。 由第一完整发现的智能体式验证-智能体-server; 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5953#issuecomment-6159631841)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5953#pullrequestreview-5512854204): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 摘要此 PR 修复了智能体服务器中的一个真实的、范围广泛的 Webhook 批处理错误：在批次 POST 运行时发布的事件已排队，但在 POST 返回时未发布，即使它们重新填充了缓冲区，因此它们等待 `flush_delay`（默认 30 秒）、下一次突发或谈话结束了。 ## 已执行验证 - **范围**：更改位于此存储库拥有的 `openhands-agent-server/openhands/agent_server/conversation_service.py` (WebhookSubscriber) 中。 它仍然停留在报告的错误中，不触及 REST/WebSocket 合同、已持久化设置或其他公共表面。- ** 正确性 **: `_post_events` 现在重新检查 `_buffer_full()` 在清空后，仍然已序列化落后于 `_post_lock` （一次请求）
- [讨论； 评论； enyst](https://github.com/OpenHands/software-agent-sdk/pull/5953#issuecomment-6228640677)：这里还存在一个问题，虽然有点边缘情况，但似乎是可能的。 来自 Astra 对话： > [P2] 失败的后续批次可以在没有重试计时器的情况下留下 > > 顺序为： > > 1。 事件在第一个 POST 期间到达，填充缓冲区并启动刷新计时器。 > 2. PR 立即在第二个 POST 中发送它们，暂时清空队列。 > 3. 计时器在此期间到期 POST，看到空队列，然后退出。 > 4. POST 耗尽了重试。 其事件被重新排队，但没有定时器来交付它们。 > > 它们可以无限期地静置，直到另一个事件触发交付或对话关闭。 > > 我用实际订阅者和本地HTTP接收器重现了这种情况，返回了一个延迟的503： > > * 基础：自动重试失败的批次，并清空队列。 > * PR：留下两个事件静置

<a id="5848-fixsdk-list-git-changes-of-a-repository-subdirectory-relative-to-it"></a>

### #5848: fix(sdk): 列出相对于它的存储库子目录的 git 更改

- 提交：`14f821bb2af5439bdcdb84193b470739e68d971f` (2026-10-17T05:10:16+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5848).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5848)。 家庭：F15。

陈述意图：

> - `get_changes_in_repo` (`openhands-sdk/openhands/sdk/git/git_changes.py`) 将 `--relative` 传递到 `git diff --name-status`，因此跟踪的更改的范围仅限于请求的目录并与其相关，例如 `git ls-files --others`。 存储库根不受影响（顶层的 `--relative` 是无操作）。
> - 测试：`get_changes_in_repo` 对存储库的 `src/` 进行内部和外部更改（修改、删除、未跟踪）。
> - 验证-智能体-服务器地图：`F15.changes-subdir-paths` 丢失其 `# bug` 标记和“已知错误”标签； 现在检查断言 `["app.py", "new.py"]` 仅针对 `src/` 进行解析，并且散文描述了固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F15-git.md`
- `openhands-sdk/openhands/sdk/git/git_changes.py`
- `tests/sdk/git/test_git_changes.py`

链接问题接受上下文：

- [#5843](https://github.com/OpenHands/software-agent-sdk/issues/5843): [Bug]: GET  /api/git/changes 对于一个仓库子目录，混合了仓库相对路径和子目录相对路径 — 当前状态已关闭，关闭于2026-10-17T03:10:18Z。

> - [ ] `GET /api/git/changes`（全局和对话范围）存储库的子目录仅返回该目录下的更改，以及与其相关的每个路径（跟踪、删除和未跟踪等）。 - [ ] 存储库根目录及其目录名称下列出的嵌套存储库保持不变。 - [ ] `tests/sdk/git/test_git_changes.py` 覆盖子目录上的 `get_changes_in_repo`。 - [ ] 地图项目符号 `F15.changes-subdir-paths` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 其他上下文根本原因，在 `openhands-sdk/openhands/sdk/git/git_changes.py`、`get_changes_in_repo` 中： - 跟踪的更改来自 `git diff --name-status <ref>`（第 184 行），它始终打印整个存储库的相对路径无论工作目录如何，存储库； - 未跟踪的文件来自 `git ls-files --others --exclude-standard`（第 197 行），其范围为工作目录并与之相关。 建议的修复：将 `--relative` 添加到 `git diff --name-status` 调用中，这将差异限制为工作目录并打印相对于它的路径，与 `ls-files` 相同。 这保留了 `get_git_changes` 已用于嵌套存储库 (`Path(git_dir) / change.path`) 和 `GET /api/git/diff` 用于其路径的请求目录基数。 相关：#5641（请求目录下的存储库，`F15.changes-repo-below-path`），它更改`get_git_changes`，而不是`get_changes_in_repo`。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5848#issuecomment-6157982385)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5848#pullrequestreview-5511816320)_这篇评论是由AI发布的智能体 (OpenHands_._ ## 评论 `fix(sdk): list git changes of a repository subdirectory relative to it` 范围： `get_changes_in_repo` 现在通过 `--relative` to `git diff --name-status`, plus a 回归测试和验证智能体服务器地图更新。 更改应在这个仓库中提交SDK git行为) 并且符合关联的 issue #5843 的验收标准`bug`, `priority:low`, `ready-for-dev`[已验证] `89557e0` - **根行为未改变。** 从仓库根目录， `git diff --name-status --relative HEAD` 这是一个无操作（我确认在有和无的情况下输出相同） `--relative`, 所以 `path=<repo>` 始终返回整个仓库的仓库相对路径 **子目录行为已修复。** 从 `src/` 带有修改后的 `src/app.py`已被删除 `src/old.py`, untrack

<a id="5967-fixagent-server-report-real-usage-buckets-in-telemetry-outcome-events"></a>

### ＃5967：fix(agent-server)：报告遥测结果事件中的实际使用情况存储桶

- 提交：`9af99982a1250b1b5d5095a5a49df4107fc18e14` (2026-10-17T05:11:24+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5967).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5967)。 家庭：F32。

陈述意图：

> - `TelemetrySubscriber` 现在记录带有统计数据的每个状态更新的使用情况：`key="stats"` 更新 `EventService` 在每次 LLM 调用后发布，以及 `full_state` 快照。 每个终端排放（`finished`、故障状态和`close()`中的`interrupted`回退方案）都存储最新的总数； 原始数据仍然不会发送，订阅者保持完整且无阻塞。
> - 新单元测试：`test_outcome_reports_usage_from_the_live_event_order`（基线快照，`running`，`stats`，裸`finished`； 在 `unknown`) 和 `test_interrupted_fallback_reports_usage_seen_before_close`（分类的 `close()` 标准）上失败。
> - 地图：`F32.telemetry-usage-buckets` 失去其 `# bug` 标记和“已知错误”标签，散文和陷阱描述了固定行为。 `F32.telemetry-lifecycle` 和 `F32.telemetry-conversation` 现在在创建 `qa-f32-telemetry` 接收器并授予同意的早期遥测配方中声明 `Requires:`，因此 `--only F32.telemetry-usage-buckets` 是独立的（没有它，先决条件就会失败，并显示“没有名为 qa-f32-telem 的 HTTP 接收器）

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`
- `openhands-agent-server/openhands/agent_server/telemetry/subscriber.py`
- `tests/agent_server/telemetry/test_telemetry_subscriber.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5961](https://github.com/OpenHands/software-agent-sdk/issues/5961): [Bug]: 遥测 conversation_finished 总是报告 total_tokens_bucket 和 cost_bucket 对于实际运行“未知” - 当前状态已关闭，已关闭 2026-10-17T03:11:26Z。

> - [  ] 进行实时运行（在每次统计更新后） LLM 调用，然后是一个裸字符串 `execution_status` 终端更新，然后最终 `full_state` snapshot), `conversation_finished` / `conversation_failed` 报告真实 `total_tokens_bucket` 和 `cost_bucket` - [  ] 终端 `full_state` 仍会生成相同的桶（现有） `test_outcome_reports_real_bucketed_usage`). - [  ] Raw token 计数和成本仍从未发送过。 订阅者始终为总订阅者（永不增加）且非阻塞 [  ] A 单元测试在 `tests/agent_server/telemetry/test_telemetry_subscriber.py` 涵盖实时活动订单 [  ] 地图弹珠 `F32.telemetry-usage-buckets` 通过其 `# bug` marker removed. ### 安装方法请输出简体中文译文 uv  同步在主版本 6e7a853 的 checkout 中，[additional] 上下文根本原因，在 `openhands-agent-server/openhands/agent_server/telemetry/subscriber.py`: - `_handle_state_update` (118行) 调用 `_capture_usage(event)` 只有在第一个终结状态（第134-136行）携带的情况下 `_emit_terminal` 立即发送结果。 - 在一个实时运行中，该事件是 `execution_status` key update fired by `ConversationState`状态变化回调 (`openhands-sdk/openhands/sdk/conversation/state.py:641`, whose `value` 是一个裸字符串。 `_capture_usage` 仅读取 `stats` 从一个字典 `value` （第199行到第203行），因此它不设置就返回了 `_total_tokens` / `_total_cost`. - 结尾 `full_state` 快照，它携带了 `stats`, 是由后来发布的 `EventService` (`openhands-agent-server/openhands/agent_server/

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5967#issuecomment-6159964083)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5967#pullrequestreview-5513083389)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 范围 In-repo 更改：`openhands-agent-server/openhands/agent_server/telemetry/subscriber.py`、其单元测试和 `verify-agent-server` F32 地图。 问题 #5961 `bug` / `ready-for-dev`，该仓库拥有智能体-服务器 telemetry 路径，因此更改应在此处进行，无需跨仓库决策。## 修复后的功能 `_capture_usage` 现在会为每个 `ConversationStateUpdateEvent` 运行，并根据 `key` 进行区分：`key="stats"` 更新（由 `EventService._setup_stats_streaming` 在每次 LLM 调用后发布）直接提供 stats dict，`key="full_state"` 版本快照提供 `value["stats"]`，其他键则提前返回。 因此，总计记录在终端状态之前，因此 `_emit_terminal` — 对于 `finished`、故障状态和 `interrupted` 回退方案 i

<a id="5964-fixagent-server-describe-the-secret-key-fallback-of-telemetryspecsalt"></a>

### #5964: fix(agent-server): 描述 TelemetrySpec.salt 的机密-键回退方案

- 提交：`7d459bcb1111e42cb2e8059d26bc6354ca6cb510` (2026-10-17T05:12:19+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5964).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5964)。 家庭：F01、F02、F03、F29、F31、F32。

陈述意图：

> - 将 `TelemetrySpec.salt` 描述重写为与代码匹配：salt，否则机密键（默认为第一个会话 API 键，因此重启后可以链接引用），否则一个随机的进程级键。 没有行为改变。 README的`OH_TELEMETRY_SALT`行已经说过了。
> - 添加单元测试，将描述与 `build_telemetry_sink` 的行为联系起来（当未设置盐时，引用等于 `pseudonymize(id.bytes, secret_key)`）。
> - 从 `F32.telemetry-salt-docs` 地图项目符号中删除已知错误标记，并更新其散文和匹配的陷阱行。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md`
- `openhands-agent-server/openhands/agent_server/config.py`
- `tests/agent_server/telemetry/test_telemetry_disabled_by_default.py`

链接问题接受上下文：

- [#5960](https://github.com/OpenHands/software-agent-sdk/issues/5960): [Bug]:TelemetrySpec.salt 描述承诺每个进程随机回退方案，但对话引用由 OH_SECRET_KEY 键入并且可在重新启动时链接 - 当前状态已关闭，已关闭 2026-10-17T03:12:21Z。

> - [ ] `TelemetrySpec.salt`的描述称 `OH_SECRET_KEY` 回退方案（以及它背后的会话密钥默认值），说随后的引用在重启时是稳定的，而仅在没有机密密钥的情况下，提到每个进程的随机密钥。- [ ]在`build_telemetry_sink`或`DiagnosticEventFactory`中没有行为改变。 `F32.telemetry-salt-and-kind` 仍然过去。 - [ ] 地图项目符号 `F32.telemetry-salt-docs` 通过，其 `# bug` 标记被删除。 TypeScript已提交的合同(`clients/typescript/src/generated/agent-server-schema.ts`)是基于已锁定的发布镜像生成的，CI's `check:agent-server-api`在任何其他内容上都会失败，因此在修复中不会进行编辑。 它在下一个智能体-服务器版本更新时开始处理新文本。### 安装方法 uv 同步在主分支的检查点中### 版本 main 为 6e7a853### 其他上下文根因：在`openhands-agent-server/openhands/agent_server/config.py:203-209`（`TelemetrySpec.salt`）。 代码：`openhands-agent-server/openhands/agent_server/telemetry/service.py:111-119`（盐，否则`config.secret_key`），`openhands-agent-server/openhands/agent_server/config.py:57-68`（`_default_secret_key`回退到第一个会话API密钥），`openhands-agent-server/openhands/agent_server/telemetry/factory.py:100-101`（仅当没有盐到达工厂时才随机密钥）。 仅文档； 微不足道的严重性。 相关： https://github.com/OpenHands/software-agent-sdk/issues/5936 （`WebhookSpec`上有同样陈旧的描述）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5964#issuecomment-6159897167)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5964#pullrequestreview-5512903049): _该评论由一个AI发布智能体 (OpenHands)._ 范围符合此仓库：`openhands-agent-server`拥有智能体-服务器的OpenAPI合同，包括其字段描述。 更改是文档加上回归测试； 它不涉及任何行为。 `4dac7ef`：验证当前头：- 新的`TelemetrySpec.salt`文本与代码匹配。 `build_telemetry_sink` (`openhands-agent-server/openhands/agent_server/telemetry/service.py`) 将 `spec.salt` 和 `config.secret_key` 传递到 `DiagnosticEventFactory`，并且 `_default_secret_key` (`config.py`) 回退到第一个会话 API 键； 当两者均未设置时，工厂仅生成随机密钥。 重写的描述准确地说明了该顺序，并且 `None` 默认值和 `SecretStr \| None` 类型保持不变。 - 添加的测试`test_salt_falls_back_to_the_secret_k

<a id="5958-fixagent-server-reject-a-create-whose-agent-tool-module-cannot-be-imported"></a>

### #5958: fix(agent-server): 拒绝无法导入智能体工具模块的创建

- 提交：`615759cc3497c8e4a8037a65c3f960da50156b65` (2026-10-17T05:16:33+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5958).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5958)。 族：F04、F05、F08、F09、F10、F11、F12、F31、F32。

陈述意图：

> - `_create_conversation` 记住哪些 `tool_module_qualnames` 模块导入失败； 一旦智能体启动，如果智能体使用这些工具之一并且无法通过其他方式解析，它会引发 `UnavailableAgentTool`，路由器将其映射到 `422`。 智能体不使用其工具的模块仍然只是一个警告。
> - 地图：`F33.custom-tool-module-unimportable` 删除其已知错误标记，现在断言 `422`； F33 陷阱和 F27 `custom-tool-modules` 散文已更新。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md`
- `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`
- `openhands-agent-server/openhands/agent_server/conversation_router.py`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `tests/agent_server/test_conversation_router.py`
- `tests/agent_server/test_conversation_service.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5940](https://github.com/OpenHands/software-agent-sdk/issues/5940): [Bug] 智能体创建了一个不能从服务器导入的模块工具的名称，那么每条消息都是500 — 当前状态关闭，关闭2026-10-17T03:16:35Z。

> - [ ] 开始一个使用服务器无法导入的 `tool_module_qualnames` 模块中的工具的对话 (智能体无法命名工具和模块) 将返回一个 4xx 错误，错误信息包括工具和模块名称。 没有创建任何对话。 - [ ] 服务器无法导入客户端注册的模块，而智能体不使用其工具仍然只记录警告并开始对话（`F33.custom-tool-module` 不变）。 - [ ] `tests/agent_server/` 中的单元测试涵盖了拒绝。 - [ ] 地图项目符号 `F33.custom-tool-module-unimportable` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main ### 版本 main 位于 6e7a853 ### 附加上下文根本原因： - `openhands-agent-server/openhands/agent_server/conversation_service.py:1528-1547` (`_create_conversation`) 导入每个 `tool_module_qualnames` 模块，并且在 `ImportError` 上仅记录警告（“如果尝试使用未注册的工具，智能体将正常失败”，第 1542 行），然后创建对话。 - 在第一条消息中，智能体初始化其工具； `resolve_tool` (`openhands-sdk/openhands/sdk/tool/registry.py:171`) 引发 `KeyError`，其中没有任何内容映射到 HTTP 错误。 相关： https://github.com/OpenHands/software-agent-sdk/issues/4080 （恢复前消失的自定义工具模块； PR  https://github.com/OpenHands/software-agent-sdk/pull/5771  严格保持新鲜对话，仅放松简历）， https://github.com/OpenHands/software-agent-sdk/issues/2667 （已持久化会话的工具集兼容性）。 由第一次完整的智能体式次验证-智能体-s发现的

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5958#issuecomment-6159748558)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5958#pullrequestreview-5513159641)_这篇评论是由AI发布的智能体 (OpenHands)._ ## Review — PR #5958 **范围检查。** 该更改应在这个仓库中：它涉及智能体创建服务器路径和 `verify-agent-server` 所有权均在这里的特征图，它实现了  API-issue #5940 请求 (拒绝创建并返回 4xx 状态码)。 Issue #5940 仍然处于打开状态 `ready-for-dev`, `bug`, `priority:low`. 不需要产品/架构升级。 **在头的验证 `5f29be7b` （所有） CI 检查运行正常，包括 `agent-server-tests`, `cross-tests`, `security`).** 聚焦测试： `tests/agent_server/test_conversation_service.py` + `tests/agent_server/test_conversation_router.py` -> 233 通过。- 与真实环境进行的活的重现 Agent Server 从这个头开始：一个创建的智能体 names `qa_ghost_tool` with `tool_module_qualnames={"qa_ghost_to

<a id="5859-fixagent-server-url-encode-the-vs-code-urls-folder-and-token"></a>

### #5859: fix(agent-server): URL-对 VS Code URL 的文件夹和 token 进行编码

- 提交：`eac3ee16cc988ca4182f3f4e52b1dee67828cd12` (2026-10-17T05:20:36+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5859).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5859)。 家庭：F16。

陈述意图：

> - `VSCodeService.get_vscode_url` 使用 `urlencode(..., quote_via=quote, safe="/")` 构建查询，因此 `folder`（和 `tkn`）准确解码； `/` 保持可读，因此 `folder=/workspace` 不变。
> - 单元测试用于往返（`&`、`#`、`?`、`%`、`+`、空格）和确切的编码形式。
> - 特征图：`F16.vscode-folder-encoding` 失去其 `# bug` 标记和“已知错误”标签，其散文现在陈述了预期行为，并声明了 `Requires: F16.vscode-enabled-status`（没有它，`--only` 在到达断言之前会点击 503“VSCode 已禁用”）。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md`
- `openhands-agent-server/openhands/agent_server/vscode_service.py`
- `tests/agent_server/test_vscode_service.py`

链接问题接受上下文：

- [#5845](https://github.com/OpenHands/software-agent-sdk/issues/5845): [Bug]: VS Code URL 的文件夹参数不是 URL 编码的，因此带有“&”或“#”的工作区路径会打开错误的文件夹 — 当前状态已关闭，已关闭 2026-10-17T03:20:38Z。

> - [ ] `VSCodeService.get_vscode_url` URL - 对查询值进行编码，因此 `folder` 参数解码回包含 `&`、`#`、`?`、`%`、`+` 或空格的路径的确切工作区路径。 - [ ] 现有的普通路径保持其形式（`/` 未转义），因此 `folder=/workspace` 不变。 - [ ] `tests/agent_server/test_vscode_service.py` 中的单元测试涵盖往返行程。 - [ ] 地图项目符号 `F16.vscode-folder-encoding` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 6e7a853 ### 附加上下文根本原因：`openhands-agent-server/openhands/agent_server/vscode_service.py:135` 将 URL 构建为 `f"{base}/?tkn={self.connection_token}&folder={workspace_dir}"`，没有编码。 `/api/vscode/url` (`vscode_router.py:48`) 和会话范围的路由 (`runtime_router.py:104`) 都经过它。 相关：`F16.vscode-url-not-running`（VS Code 未运行时返回 URL）是一个单独的项目，不在此处的范围内。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5859#issuecomment-6158172021)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5859#pullrequestreview-5570230212)：_此审查由 AI智能体（OpenHands）发布。_ **范围。** 属于本仓库：Agent Server 负责 `VSCodeService` 以及标准的 `/api/vscode/url` + `/api/conversations/{id}/vscode/url` REST 路由。 无需跨回购移动。 **当前状态（立即重读）。**头还在`55d5543ab5f32bc2e029a3b05ef349a915033e8d`； PR状态是`closed`和**合并**（合并2026-10-17T03:20:36Z，合并提交`eac3ee16`）。 头部在之前审查的 `f2b8fee`: `55d5543 Merge branch 'main' into claude/umbrella-bug-fixes-tgz9ai-vscode-folder-encoding` 的基础上添加了一项提交。 该提交仅将 `main` 向前推进 - `git show origin/main:.../vscode_service.py` 已经包含完全相同的 `urlencode(..., quote_via=quote, safe="/")` 块 - 因此所审查的代码没有改变。 链接问题 #5845 是 `closed` 和 `bug`、`priority:low`、`

<a id="5856-fixagent-server-report-the-uploaded-file_size-in-the-upload-response"></a>

### #5856: fix(agent-server): 在上传响应中报告已上传的file_size

- 提交：`af05c8b46a8a0a318f853e6297736fb883c8de73` (2026-10-17T05:26:37+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5856).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5856)。 家庭：F04、F08、F10、F11、F12、F13、F14。

陈述意图：

> - `_upload_file` 计算流到磁盘的字节数并将其返回为 `file_size`； 两个上传路由共享它。
> - `tests/agent_server/test_file_router.py` 断言小上传、分块 (>8 KiB) 上传和覆盖的大小。
> - `F14.upload-size` 表格子弹丢弃了 `# bug` 标记和“已知错误”标签，现在还检查 `file_size` 原始 REST 响应，并且其文本和 Gotchas 行描述了已修复的行为。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `5fa4dea24c52` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -731 +731 @@
> -response POST /api/conversations/{runtime_conversation_id}/file/upload 200 application/json 模式=成功
> +响应 POST /api/conversations/{runtime_conversation_id}/file/upload 200 应用程序/json 模式=FileUploadResult
> @@ -735 +735 @@
> -response POST /api/file/upload 200 application/json 模式=成功
> +响应 POST /api/file/upload 200 应用程序/json 模式=FileUploadResult
> @@ -1685,0 +1686,3 @@
> +模式 FileUploadResult 属性 file_size 必需模式=type="integer"
> +sc

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`
- `openhands-agent-server/openhands/agent_server/file_router.py`
- `openhands-agent-server/openhands/agent_server/models.py`
- `tests/agent_server/test_file_router.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5836](https://github.com/OpenHands/software-agent-sdk/issues/5836): [Bug]: 文件上传只响应 {"success": True}，因此 SDK 和 TypeScript 远程工作区无法报告任何 file_size — 当前状态已关闭，关闭于 2026-10-17T03:26:39Z。

> - [ ] 成功上传（全局和会话范围路由）报告写入的字节数，`RemoteWorkspace.file_upload`（同步和异步）将其报告为 `file_size`。 - [ ] TypeScript `RemoteWorkspace.fileUpload` 报告了相同的 `file_size`，因此 `write_file` 不再说 `undefined bytes`。 - [ ] 仅读取 `success` 的现有客户端继续工作（响应仍然是 `{"success": true}` 的超集）。 - [ ] A 单元测试涵盖了报告的尺寸。 - [ ] 地图项目符号 `F14.upload-size` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的检查中 ### Version main at 6e7a853 ### 附加上下文根本原因： - `_upload_file` (`openhands-agent-server/openhands/agent_server/file_router.py:85`) 将主体流式传输到磁盘并返回 `Success()`（第 109 行）； `Success`（`openhands-agent-server/openhands/agent_server/models.py:443`）只有`success`。 - `_file_upload_generator` (`openhands-sdk/openhands/sdk/workspace/remote/remote_workspace_mixin.py:336`) 设置 `file_size=result_data.get("file_size")`。 - `RemoteWorkspace.fileUpload`（`clients/typescript/src/workspace/remote-workspace.ts:171-177`）份`resultData.file_size`； `clients/typescript/src/conversation/local-conversation.ts:655`打印它。 SDK自己的单元测试已经模拟对象响应为`{"success": true, "file_size": 12}`（`tests/sdk/workspace/remote/test_remote_workspace_mixin.py:343`），i.e。 客户收到的回复中包含了尺寸。 可能有两种修复：服务器发送 `file_size`（一项更改，每个客户端都受益），或者每个客户端共同

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5856#issuecomment-6158226293)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5856#pullrequestreview-5513067179): _此评论由一个AI发布智能体 (OpenHands)._ ## 范围本仓库适用于以下更改：该更改仅限于 Python Agent Server (`file_router.py`, `models.py`)，其标准 OpenAPI 响应合同，其回归测试，以及该仓库拥有的 `verify-agent-server` 功能图。 这是一个累加的，向后兼容 REST 的响应改变(`Success`到`FileUploadResult(Success)`，增加了`file_size`)，因此不需要产品/架构决策。## 评估修复是正确的且最小化。 `_upload_file` 现在在其写入的相同块上累积 `len(chunk)` 并返回 `FileUploadResult(file_size=...)`； 因此，字节数准确地反映了服务器写入的内容。 两个上传入口共享这个助手：全局 `POST /api/file/upload` 和对话范围的 `POST /api/conversations/{runtime_convers
- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5856#pullrequestreview-5570071400)_这篇评论是由AI发布的智能体 (OpenHands## 范围本仓库适用于以下变更：该变更仅影响  Python  Agent Server (`file_router.py`, `models.py`), 其他名称 OpenAPI 响应合同，它的回归测试，以及该仓库所有者的所有内容 `verify-agent-server` 特征图。 它是一个累加的向后兼容  REST 响应更改 (`Success` to `FileUploadResult(Success)` 带有附加的 `file_size`）因此，无需做出产品/架构决策 `a30648c`, which merged `main` (已移动到 `5fa4dea`） 由于我之前的审查 `b8ef70a`. 此头上的修复完整且正确。 `_upload_file` accumulates `len(chunk)` 在写入和返回相同块的过程中 `FileUploadResult(file_size=file_size)` (`file_router.py:112`). Both upload 入口分享这个辅助，以便

<a id="5853-fixagent-server-page-search_subdirs-past-names-that-differ-only-by-case"></a>

### #5853: fix(agent-server): 第 search_subdirs 页过去的名称仅大小写不同

- 提交：`501d27323cf36325242508de6fbf6a6a66c05b2b` (2026-10-17T05:32:10+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5853).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5853)。 家庭：F14。

陈述意图：

> - 按 `(name.lower(), name)` 排序：顺序保持不区分大小写，并且仅区分大小写的双胞胎现在具有稳定的顺序。
> - `next_page_id` 现在是下一个条目的确切名称。 一个 `page_id` 与名称完全匹配的都不匹配，因此，一个来自较旧服务器的下划线光标仍然会回到其入口。
> - 两个单元测试：分页过去`Foo`/`foo`，并从小写光标处恢复。 `F14.subdirs-case-pagination` 地图项目符号失去了已知错误标记，其散文和陷阱行现在描述了固定行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F14-files.md`
- `openhands-agent-server/openhands/agent_server/file_router.py`
- `tests/agent_server/test_file_router.py`

链接问题接受上下文：

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5837](https://github.com/OpenHands/software-agent-sdk/issues/5837)：[缺陷]：GET /api/file/search_subdirs 分页始终无法越过两个名称仅大小写不同的目录；当前状态为已关闭，关闭时间为 2026-10-17T03:32:12Z。

> - [ ] 从 `GET /api/file/search_subdirs` 开始的 `next_page_id` 到 `Foo`、`foo`（以及任何其他条目）和 `limit=1` 只访问每个子目录一次，并且不以 `next_page_id` 结束。 - [ ] 按名称排序保持不区分大小写，并且现有的不带大小写孪生的名称分页保持不变。 - [ ] `tests/agent_server/test_file_router.py` 涵盖了对仅案例双胞胎的寻呼。 - [ ] 地图项目符号 `F14.subdirs-case-pagination` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6e7a853 ### 其他上下文根本原因，在 `openhands-agent-server/openhands/agent_server/file_router.py` (`search_subdirs`) 中： - 条目仅按 `name.lower()` 排序（第 896 行），因此 `Foo` 和 `foo` 的顺序取决于磁盘扫描顺序； - 恢复选择第一个条目其`name.lower() == page_id`（第899-903行）； - 光标为 `entries[start_index + limit].name.lower()`（第 908 行），因此 `foo` 的光标也匹配 `Foo`。 建议的修复：按 `(name.lower(), name)` 排序，使顺序为总和且稳定，并使光标为下一个条目的精确名称，从具有该精确名称的条目开始（在更改前发出小写光标的情况下，使用不区分大小写的匹配）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5853#issuecomment-6158052302)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5853#pullrequestreview-5512002589)：_此审查由 AI智能体（OpenHands）发布。_ ## 审查 — `fix(agent-server): page search_subdirs past names that differ only by case`：变更位于 `openhands-agent-server`，即本仓库负责的标准 REST API，因此属于本仓库。 链接问题 #5837 已通过 `ready-for-dev` / `priority:low` 开放； 其接受标准如下。 在头 `71e271c5` 上验证： - CI：在此头上运行的每个检查都是绿色的，包括 `agent-server-tests`、`cross-tests`、`REST API (OpenAPI)`、TypeScript 客户端检查和 `pre-commit`。 没有失败或待处理的检查。 - 重点测试：`uv run --frozen pytest tests/agent_server/test_file_router.py tests/agent_server/test_search_limit_validation.py` → 101 通过。 正确性： - 按 `(name.lower(), name)` 排序使订单总计，因此仅大小写的双胞胎获得不同的位置 a

<a id="5819-fixagent-server-return-404-from-ask_agent-for-an-unknown-conversation"></a>

### ＃5819：fix(agent-server)：从ask_agent返回404未知对话

- 提交：`e98b95654fdfe4001d605a6f61893d65d8fa0b3d` (2026-10-17T05:34:14+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5819).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5819)。 家庭：F04、F05、F08、F09、F10、F11、F12。

陈述意图：

> - `conversation_router.ask_agent`：映射服务的`None`（仅在会话丢失时返回； `EventService.ask_agent` 将 `str`) 返回到 `404 "Conversation not found"`，与 `condense` 给出的答案相同。
> - 未知 ID 情况下的路由器单元测试。
> - verify-智能体-server 映射：删除 `F10.ask-agent-unknown` 已知错误标记，检查 404 详细信息，并在路由响应中列出 404。
> 
> `RemoteConversation.ask_agent` 和 TypeScript 客户端的 `askAgent` 刚刚出现 HTTP 错误，并且 OpenAPI 模式已经声明了 404，所以两个客户端都没有改变。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md`
- `openhands-agent-server/openhands/agent_server/conversation_router.py`
- `tests/agent_server/test_conversation_router.py`

链接问题接受上下文：

- [#5813](https://github.com/OpenHands/software-agent-sdk/issues/5813): [Bug]: POST  /api/conversations/{id}/ask_agent 返回未知对话的500，而不是文档中提到的404 — 现状已关闭，关闭于2026-10-17T03:34:16Z。

> - id 未知的 [ ] `POST /api/conversations/{id}/ask_agent` 返回 `404` (`{"detail": "Conversation not found"}`)，匹配 `condense` 和 `navigate`。 - [ ] 已知对话仍会回答 `200 {"response": ...}`； 无法到达的模型仍然是 `500` 和 `error_id`。 - [ ] `tests/agent_server/test_conversation_router.py` 中的单元测试涵盖了未知 id 的情况。 - [ ] 地图项目符号 `F10.ask-agent-unknown` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的检查中 ### 版本 main 在 6a298a4 ### 附加上下文根本原因： - 当 `_get_or_load_event_service` 发现没有对话时，`ConversationService.ask_agent` (`openhands-agent-server/openhands/agent_server/conversation_service.py:1869-1873`) 返回 `None`。 `EventService.ask_agent` 返回 `str`，因此 `None` 只表示“未找到”。 - 路线 (`openhands-agent-server/openhands/agent_server/conversation_router.py:760-762`) 将 `None` 映射到裸露的 `HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)`，尽管它声明了 `responses={404: ...}`（第 752 行）。 `condense_conversation`（第773-775行）针对相同的情况提出了`404 "Conversation not found"`。 建议修复：在那里加注 `HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")`。 `RemoteConversation.ask_agent`和TypeScript客户端的`askAgent`只是表面HTTP错误，所以他们不需要改变。 相关：#5800（暂停/中断时未知 ID/DELETE/PATCH）。 由第一次完整的智能体式运行 verify-智能体-server 发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5819#issuecomment-6157682633)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5819#pullrequestreview-5511695815)_这篇评论是由AI发布的智能体 (OpenHands)._ ## Review — fix(agent-server)返回 404 错误 ask_agent 对于未知的对话 **范围。** 这应该在这里：[ ] Agent Server 拥有 `/api/**`  REST 合同，变更是路由级别的响应映射。 不需要跨存储库或产品/架构决策。 **我在头部验证了什么 `40bac19`:** - `ConversationService.ask_agent` (`conversation_service.py:1869`) 返回 `None` 仅用于未找到路径 `EventService.ask_agent` is typed `-> str` (`event_service.py:2156`) — so mapping `None` → `404 "Conversation not found"` 在 `conversation_router.ask_agent` 正确。 它匹配了路由声明的 `responses={404: ...}` and the sibling `condense` 该路由会返回相同的状态和详细信息。无需客户端更改。 `RemoteConversation.ask_agent` and the Ty

<a id="5811-fixsdk-refuse-a-blank-acp-model-before-the-first-run"></a>

### ＃5811：fix(sdk)：在第一次运行之前拒绝空白ACP模型

- 提交：`7f41284acefd65a978c1075d7e19631a6730b782` (2026-10-17T05:35:41+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5811).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5811)。 家庭：F05、F08、F09、F10。

陈述意图：

> - `LocalConversation.switch_acp_model` 现在拒绝实时/预运行分支之前的空或仅空白模型（`ValueError`，与 `set_acp_model` 相同的消息），因此没有任何内容已持久化。 智能体-服务器路由已经将`ValueError`映射到400； TypeScript客户端仅转发请求，因此没有任何变化。
> - 单元测试用于 `tests/sdk/conversation/test_switch_model.py` 中的预运行空白情况（`""` 和 `"   "`）。
> - 从 `F09.acp-model-blank` 地图项目符号中删除 `known bug` 标记，并将其散文重写为预期行为。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md`
- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`
- `tests/sdk/conversation/test_switch_model.py`

链接问题接受上下文：

- [#5807](https://github.com/OpenHands/software-agent-sdk/issues/5807): [Bug]: switch_acp_model在第一次运行之前接受一个空白或空格的模型并将其保存——当前状态已关闭，关闭于2026-10-17T03:35:42Z。

> - [ ] `switch_acp_model` 在尚未运行的 ACP 对话中使用空模型或仅空白模型回答 `400`（SDK：引发 `ValueError`）并保持 `agent.acp_model`、`current_model_id` 和 `base_state.json` 不变。 - [ ] 有效的预运行切换仍然被推迟和已持久化 (200)，并且实时会话行为保持不变。 - [ ] `tests/sdk/conversation/test_switch_model.py` 中的单元测试涵盖了空白的预运行案例。 - [ ] 地图项目符号 `F09.acp-model-blank` 通过，其 `# bug` 标记被删除。 ### 安装方法 uv 同步在 main 的签出中 ### 版本 main 在 6a298a4 ### 附加上下文根本原因：非空检查仅存在于 `ACPAgent.set_acp_model` (`openhands-sdk/openhands/sdk/agent/acp_agent.py:4472-4473`) 中。 `LocalConversation.switch_acp_model` (`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1723`) 仅当存在实时会话时才调用它（第 1761-1763 行）； 预运行路径会跳过它并保留未选中的值（第 1782 行的 `model_copy(update={"acp_model": model})`，第 1803 行的 `acp_current_model_id`）。 路由器 (`openhands-agent-server/openhands/agent_server/conversation_router.py:714-720`) 已经将 `ValueError` 映射到 400，因此在实时/预运行分支之前在 `switch_acp_model` 中进行验证修复了 SDK 和 REST 路由。 相关：#3763（引入此路径的预运行延迟），由#3764 修复。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5811#issuecomment-6157500782)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5811#pullrequestreview-5511473642)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论：PR #5811 — fix(sdk)：在第一次运行 **范围之前拒绝空白 ACP 模型。**属于此存储库：守卫位于 SDK 的规范 Python 表面 `LocalConversation.switch_acp_model` 上，并且智能体服务器路由已经映射 `ValueError` → 400，因此一个共享检查涵盖 SDK 和 REST。 没有跨回购移动。 链接问题 #5807 已在 `ready-for-dev` 中开放。 **更改。**新添加的前置保护措施（`if not model or not model.strip(): raise ValueError("model must be a non-empty string")`）使用了与`ACPAgent.set_acp_model`中相同的消息，因此REST的路由返回400状态，并且包含与实时会话相同的详细信息。 它在 `with self._state:` 之前运行，因此拒绝 `self.agent`、`self._state.agent`、`agent_state["acp_current_model_id"]`、

<a id="5795-fixagent-server-refuse-more-than-99-batch-get-ids-with-a-422"></a>

### ＃5795：fix(agent-server)：拒绝超过 99 个带有 422 的批量获取 id

- 提交：`9d07c6d55d1b371ed3d7ce6fba472ecef50f7a90` (2026-10-17T05:45:44+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5795).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5795)。 家庭：F04、F05、F08、F09、F10、F11、F12。

陈述意图：

> 将限制声明为 `ids: Annotated[list[UUID], Query(max_length=99)]` 并删除断言。现在，100+ 个 ID 会返回 422 错误 ("列表应最多有 99 个项目")，服务未被调用，OpenAPI 显示 `maxItems: 99`，遵循了 `le=100` 在搜索 `limit` ( https://github.com/OpenHands/software-agent-sdk/issues/5114 ) 上的声明。
> - 路由器测试现在断言 422（它用于断言 `AssertionError`）、99-id 200 和 OpenAPI 边界。
> - 从`F04.batch-get-limit`地图项目符号中删除`# bug`标记。 配方现在期望 422，其正文显示为 `at most 99 items`。
> 
> 在问题优先级分类过程中，99-id的限制保持不变，TypeScript客户端没有分块。 100 个 id 的 TS 批次现在获得 422，而不是 500。
> 
> 
> ### REST API 合同变更
> 
> 与公共 `/api/**` 路径的基 OpenAPI `6a298a48fcdb` 相比。
> 
> ```差异
> ---基础公共OpenAPI
> +++ 公共头 OpenAPI
> @@ -195 +195 @@
> -参数 GET /api/conversations 查询：ids required=True 模式=type="array" items=type="string" format="uuid"
> +参数 GET /api/conversations 查询：需要 ids=True 架构

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md`
- `openhands-agent-server/openhands/agent_server/conversation_router.py`
- `tests/agent_server/test_conversation_router.py`

链接问题接受上下文：

- [#5114](https://github.com/OpenHands/software-agent-sdk/issues/5114): [Bug]: GET /api/conversations/search 返回 500，限制 > 100（无优雅钳位） — 当前状态已关闭，已关闭 2026-09-17T05:33:34Z。

> - [ ] `GET /api/conversations/search?limit=101` 返回 **422**（不是 500），命名为 `limit`。 - [ ] `limit=100` 仍然返回 `200` 100 个项目； `limit=0` 和负限制仍然返回 422。 - [ ] 测试涵盖 0、1、100 和 101 处的 `limit`，断言 422/200/200/422。 - [ ] 该文件中基于 `assert` 的检查（第 117、118 和 196 行）被真实的验证替换，因此行为与 `python -O` 下相同。 - [ ] `limit=101` 不再在服务器日志中发出 `Unhandled exception ... api.py:616`。 ### 环境 - `openhands-agent-server==1.46.0`（通过 `uvx`），本地模式 - Agent Canvas 1.17.0 - Ubuntu 24.04，m7i.2xlarge，300 GB gp3 - 2026 年 9 月 17 日复制，有约 140 个对话 ### 还有其他吗？ Canvas侧边栏请求`limit=20`，因此正常使用不受影响。 它会咬任何一页请求列表更大的客户端（批量导出、脚本、监控）——因为失败是 `500` 而不是 4xx，它看起来像是服务器错误而不是一个坏请求，这会将调试者引导到错误的路径。 在测量负载下的 list-端点延迟时发现的。 相同的端点是 #4537 的主题（状态锁由子智能体运行保持）； 请注意，即使现在列出路径读取的是已持久化 `base_state.json` 版本而不是实时状态，这个页面大小边缘情况仍然存在。 --- 这个问题是由一个代表 Hussain._ 的 AI 智能体 (OpenHands) 创建和更新的

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

- [#5790](https://github.com/OpenHands/software-agent-sdk/issues/5790)：[缺陷]：GET /api/conversations 接收 100 个或更多 ID 时，会返回带空异常的 500，而不是明确说明限制的 4xx；当前状态为已关闭，关闭时间为 2026-10-17T03:45:46Z。

> - [ ] `GET /api/conversations` 具有 100 个或更多 id 返回一个 4xx，其主体命名为 99-id 限制； 没有任何内容到达对话服务。 - [ ] 99 个 ID 仍然返回 `200`。 - [ ] OpenAPI 模式声明了 `ids` 的限制。 - [ ] `tests/agent_server/test_conversation_router.py` 涵盖 100-id 请求（当前测试断言 `AssertionError`）。 - [ ] 地图项目符号 `F04.batch-get-limit` 通过，其 `# bug` 标记被删除。 ### 检查主版本中的安装方法 uv 同步 ### 版本主版本位于 6a298a4 ### 附加上下文根本原因：`openhands-agent-server/openhands/agent_server/conversation_router.py:292` 中的 `batch_get_conversations` 是 `assert len(ids) < 100`。 `AssertionError`（没有消息）到达`_unhandled_exception_handler`（`openhands-agent-server/openhands/agent_server/api.py:651`），它用`"exception": str(exc)`、i.e回答500。 `""`. TypeScript 客户端在一个请求中发送所有 ID：`clients/typescript/src/conversation/conversation-manager.ts:162` 和 `clients/typescript/src/client/conversation-client.ts:133`。 相关：#5114（搜索时 `limit > 100` 的 500 相同，因为已声明 `le=100` 已修复）。 由 verify-智能体-server 的第一次完整智能体式运行发现； 追踪于#5653。 ---

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5795#issuecomment-6157239944)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5795#pullrequestreview-5511360966)：_此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论：PR #5795 — 拒绝超过 99 个批量获取 ID，并进行 422 ### 范围智能体-服务器 REST API 更改（此存储库拥有的规范 API）。 它替换了一个基于断言的批量大小校验器，使用了一个声明的FastAPI/Pydantic查询约束，与用于搜索`limit`的权威模式一致(`Query(gt=0, le=100)`，#5114)。 在范围内； `f2ac77c0` 无交叉仓库所有权问题。我目前在**的运行行为上进行了验证。** `ids: Annotated[list[UUID], Query(max_length=99)]`将100个ID转换为FastAPI 422 (`"List should have at most 99 items"`)，因此`conversation_service.batch_get_conversations`不会被调用。 `test_batch_get_conv 中的新 `mock_conversation_service.batch_get_conversations.assert_not_called()`

<a id="5773-fixagent-server-accept-short-event-kinds-in-events-search-and-count"></a>

### ＃5773：fix(agent-server)：在事件搜索和计数中接受短事件类型

- 提交：`75abe1eb3f5fca908578d4437e8fee36125e4b0b` (2026-10-17T06:00:17+02:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5773).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5773)。 族：F05、F06、F07、F08、F09、F10、F11、F12、F31。

陈述意图：

> - `EventService._event_matches_filters`（由`search_events`和`count_events`共享）现在接受裸类名或完全限定的类路径。 未知或部分名称仍然会给出空白页面/`0`，并且`kind`仍然与其他过滤器结合。 模式或 TypeScript 客户端的有线格式没有变化。
> - `tests/agent_server/test_event_service.py` 中的单元测试涵盖用于搜索的短类型（与完整路径相同的 ids 和 `next_page_id`，与 `source` 组合，部分路径不匹配）和计数。
> - verify-智能体-server 映射：从 `F06.search-kind-short` 和 `F34.events-search-kind` 中删除已知错误标记，将其散文重写为预期行为，更新了 F05、F06、F08、F33 和 F34 中描述错误的陷阱行，并为 `F06.search-kind-short` 提供了它需要自行运行的 `Requires: F06.send-no-run` 行（如果没有它，`--only` 会针对空日志运行，并在到达标记行之前失败）。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md`
- `.agents/skills/verify-agent-server/references/feature-map/F06-conversation-events.md`
- `.agents/skills/verify-agent-server/references/feature-map/F08-confirmation-security-secrets.md`
- `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md`
- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `openhands-agent-server/openhands/agent_server/event_service.py`
- `tests/agent_server/test_event_service.py`

链接问题接受上下文：

- [#5631](https://github.com/OpenHands/software-agent-sdk/issues/5631): [Bug]: events/search 和 /count with kind=MessageEvent 不返回任何内容； 仅完整类路径匹配 - 当前状态已关闭，已关闭 2026-10-17T04:00:19Z。

> - [ ] `events/search` 和 `events/count` 与 `kind=MessageEvent` 返回与完全限定类型相同的结果； 完全限定的形式继续有效。 - [ ] `tests/agent_server/test_event_service.py` 中的单元测试涵盖了 `search_events` 和 `count_events` 的缩写。 - [ ] `F06.search-kind-short` 和 `F34.events-search-kind` 地图项目符号通过，其已知错误标记已被删除。 ### 检查 main 中的安装方法 uv 同步 ### 版本 main 位于 2804c12 ### 附加上下文根本原因：`EventService._event_matches_filters` (`openhands-agent-server/openhands/agent_server/event_service.py:544`) 在 `f"{event.__class__.__module__}.{event.__class__.__name__}" != kind` 时拒绝事件（第 554-558 行）。 `search_events`（第653行）和`count_events`（第725行）都使用它。 `kind` 线是裸类名（`DiscriminatedUnionMixin.kind` 返回 `self.__class__.__name__`，`openhands-sdk/openhands/sdk/utils/models.py:203-205`），正如路由文档（`event_router.py:80-85`，`:146-151`）和 TS 客户端（`clients/typescript/src/events/remote-events-list.ts:22-23`，行 60 和 83 未更改）所述。 单元测试 (`tests/agent_server/test_event_service.py:265-268`) 仅使用完全限定形式。 建议的修复：接受 `_event_matches_filters` 中的两种形式，例如 ```python cls = type(event) if kind is not None and kind not in (cls.__name__, f"{cls.__module__}.{cls.__name__}"): return False ``` 这使完全合格的调用者能够正常工作。 使用 422 拒绝未知类型并修复文档是另一种选择，但它会破坏客户端的写入

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5773#issuecomment-6156414179)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [reviews APPROVED; 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5773#pullrequestreview-5510938299)_这篇评论是由AI发布的智能体 (OpenHands)._ ## 范围更改属于此处： `openhands-agent-server/` 拥有 canonical REST  API 和 `verify-agent-server` 特征图是属于仓库的技能。 修复仅限于  `kind` 共享的过滤器 `events/search` 和 `events/count`, 以及它推动服务器朝着自己的路由文档所描述的行为`e.g., ActionEvent, MessageEvent`), the wire `kind` field, and the TypeScript 客户端的 `EventSearchOptions.kind` 已经描述过。## 我在当前分支上验证了（`7b0ea38`) - **过滤语义。**  `_event_matches_filters` 现在匹配任何一种 `cls.__name__` 或 `f"{cls.__module__}.{cls.__name__}"`. 直接针对一个真实的  `MessageEvent`: `kind=MessageEvent` 匹配，完全限定路径匹配 `message.MessageEvent` 不，未知名称也不行，且 `kind`

<a id="5783-fixts-honor-maxiterations-and-stuckdetection-in-conversationmanagercreateconversation"></a>

### ＃5783：fix(ts)：荣誉ConversationManager.createConversation中的maxIterations和stuckDetection

- 提交：`1fbfd37f6fb21491ed733fc92d409aff1517ff4a` (2026-10-17T04:10:34Z)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5783).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5783)。 家庭：F34。

陈述意图：

> - `ConversationManager.createConversation` 通过 `maxIterations` 和 `stuckDetection` 到 `RemoteConversation.start()`。
> - `RemoteConversation` 保留两个构造函数选项并将它们用作 `start()` 中的回退方案； `0`/omitted对`maxIterations`（`|| 500`）的处理不变。 还修复了 `BaseConversationOptions.maxIterations` 上过时的“default: 50”文档注释（默认值为 500）。
> - 新的 `conversation-create-options.test.ts` 断言 `POST /api/conversations` 主体； `F34.manager-create-options` 地图项目符号失去了已知错误标记。

更改的路径：

- `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md`
- `clients/typescript/src/__tests__/conversation-create-options.test.ts`
- `clients/typescript/src/conversation/base.ts`
- `clients/typescript/src/conversation/conversation-manager.ts`
- `clients/typescript/src/conversation/remote-conversation.ts`

链接问题接受上下文：

- [#5649](https://github.com/OpenHands/software-agent-sdk/issues/5649): [Bug]: TS ConversationManager.createConversation 忽略 maxIterations/stuckDetection (服务器获取 500/true) — 当前状态已关闭，已关闭 2026-10-17T04:10:38Z。

> - [ ] `ConversationManager.createConversation` 在 `POST /api/conversations` 中发送调用者的 `maxIterations` 和 `stuckDetection`，省略它们将保留今天的默认值 (500, `true`)。 - [ ] 管理器上的单元测试断言请求正文携带这两个值。 - [ ] `F34-typescript-client.md` 中的 `F34.manager-create-options` 项目符号通过，并且其已知错误标记被删除。 ### 检查 main 时的安装方法 uv 同步 ### 版本 main 位于 2804c12 ### 附加上下文根本原因： - `clients/typescript/src/conversation/conversation-manager.ts:221-225` 将 `maxIterations` 和 `stuckDetection` 传递给 `RemoteConversation` 构造函数，然后 `:227-230` 仅使用 `initialMessage` 和 `userId` 调用 `start()`。 - 构造函数 (`clients/typescript/src/conversation/remote-conversation.ts:96-114`) 删除两者，尽管 `BaseConversationOptions` 声明了它们 (`clients/typescript/src/conversation/base.ts:30,32`)。 - `start()` 仅根据其自己的参数构建请求：`max_iterations: options.maxIterations \|\| 500` 和 `stuck_detection: options.stuckDetection ?? true` (`remote-conversation.ts:173-174`)。 ACP 路径不受影响：`createACPConversation` 直接从选项构建请求 (`conversation-manager.ts:355-356`)。 建议修复：将 `maxIterations` 和 `stuckDetection` 传递到 `createConversation` 中的 `start()`。 也可以选择将两者保留在构造函数中，并将它们用作 `start()` 中的回退方案，因为 `hookConfig` 和 `userId` 已经是 (`remote-conversation.ts:167-168`)，因此 `new RemoteConversation(agent, ws, { maxIterations: 7 })` 和

- [#5653](https://github.com/OpenHands/software-agent-sdk/issues/5653)：Agent Server 由 verify-智能体-server 特征图（伞）发现的错误 — 当前状态打开、关闭 —。

> 我是人工智能智能体基于Opus 5.5，帮助Engel Nyst (@enyst) 进行项目维护。 在构建可执行功能图的过程中， Agent Server  API 在 #5621 (the `verify-agent-server` 我们试了所有的技能智能体在真实服务器上测试端口，并在路上发现了产品缺陷。 本期将它们收集起来，所以有一个地方可以看到全貌。 每个错误都是地图中的已知错误项目符号，由括号中的子功能 ID 命名。 `control-agent-server map run --file <family> --only <ID> --fresh` 它重现了它，一旦修复就发布

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5783#issuecomment-6157032250)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5783#pullrequestreview-5511273078): _此评论由 AI 智能体 (OpenHands) 发布。_ ## 评论：荣誉 `ConversationManager.createConversation` ** 中的 maxIterations / stuckDetection 范围：** `clients/typescript/` 镜像浏览器客户端的 Agent Server API，因此此更改属于此存储库。 不需要跨存储库移动或维护者范围决策。 **为什么这是正确的**报告的错误：`ConversationManager.createConversation`接受`maxIterations`/`stuckDetection`，将它们传递给`RemoteConversation`构造函数（删除它们），并在没有它们的情况下调用`start()`，因此`POST /api/conversations`总是携带`max_iterations: 500`/`stuck_detection: true`。 头部修复了两个层： - `conversation-manager.ts` 现在将两个选项转发到 `start()` — 所需的修复。 - `remote-conversation.ts` 保留两个构造函数选项并将它们应用为

<a id="5126-featagent-server-add-start_child_conversation-tool-with-a-pluggable-launcher"></a>

### ＃5126：feat(agent-server)：添加带有可插入启动器的start_child_conversation工具

- 提交：`5966c781ed014efc96c028a99bddd4ff78426741` (2026-10-17T16:03:12+07:00)。 [PR](https://github.com/OpenHands/software-agent-sdk/pull/5126).
- 意图：记录。 运行时：**带有已知缺陷的系列扫描**； [特征证据和限制](intent-runtime-overlay.md#pr-5126)。 族：F01、F02、F03、F04、F05、F06、F08、F09、F10、F11、F12、F13、F27、F29、F30、F31、F32、F33、F34。

陈述意图：

> - `POST /api/conversations/{conversation_id}/children`, backed by `ConversationService.start_child_conversation`. 就像叉子一样，子进程复制了父进程的存储配置机密客户端工具、插件、钩子、标签、确认和安全设置)及其解决办法智能体但是它有一个空的历史，接收了  `task` 作为其第一个用户消息并记录下来 `parent_conversation_id`. `isolation="worktree"` (默认) 重用了现有工作树当该目录不是 Git 仓库时，会进行准备并切换到父目录。 `isolation="shared"` 总是分享它。 响应报告实际应用的隔离。 在进行特定的子代准备之后，启动过程与正常启动过程相同`_launch_prepared_conversation`, 共享的 `_create_conversation`): 运行槽先被获取，因此，一个完整的服务器在收到 429 前会给出一个答复工作树或持久化如果目录存在，则子目录是已持久化，`task` 当交付时，第一个运行将被安排在那个时间槽 Webhook 被通知。
> - `start_child_conversation` `op 中的工具

更改的路径：

- `openhands-agent-server/openhands/agent_server/api.py`
- `openhands-agent-server/openhands/agent_server/config.py`
- `openhands-agent-server/openhands/agent_server/conversation_router.py`
- `openhands-agent-server/openhands/agent_server/conversation_service.py`
- `openhands-agent-server/openhands/agent_server/init_router.py`
- `openhands-agent-server/openhands/agent_server/models.py`
- `openhands-agent-server/openhands/agent_server/tool_router.py`
- `openhands-sdk/openhands/sdk/conversation/request.py`
- `openhands-tools/openhands/tools/child_conversation/__init__.py`
- `openhands-tools/openhands/tools/child_conversation/definition.py`
- `openhands-tools/openhands/tools/child_conversation/impl.py`
- `tests/agent_server/conftest.py`
- `tests/agent_server/test_config.py`
- `tests/agent_server/test_init_router.py`
- `tests/agent_server/test_parent_child_conversations.py`
- `tests/tools/child_conversation/test_start_child_conversation.py`

REST兼容性：[PASSED](https://github.com/OpenHands/software-agent-sdk/pull/5126#issuecomment-5710999102)

审查/讨论决定（原始记录中保留的按时间顺序排列的证据）：

- [评论； APPROVED; 托法尔](https://github.com/OpenHands/software-agent-sdk/pull/5126#pullrequestreview-5279081028)：🍰
- [评论； COMMENTED; all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5126#pullrequestreview-5383129292)：_此评论由 AI 智能体 (OpenHands) 发布。_ 我评论了工作区中的头部 `5f3ce36`，阅读了存储库指南（根 `AGENTS.md`、`.agents/skills/custom-codereview-guide.md` 和智能体-服务器/工具包 `AGENTS.md`），并运行了重点套件： - `uv run pytest tests/tools/child_conversation tests/agent_server/test_parent_child_conversations.py -q` -> 30 通过 - `uv run pytest tests/agent_server/test_parent_child_conversations.py tests/tools/child_conversation tests/agent_server/test_conversation_router.py tests/agent_server/test_openapi_contract.py -q` -> 130 通过 - `uv run pre-commit run --files <changed files>` -> Ruff format/lint、pycodestyle、Pyright、导入规则、工具注册均已通过核心设计合理且适合存储库边界：SDK/agent-server 拥有启动，工作树机制
- [评论； COMMENTED; 所有手机器人](https://github.com/OpenHands/software-agent-sdk/pull/5126#pullrequestreview-5495002135): _这条评论是由一个AI发布的智能体 (OpenHands)._ 我重新审查了当前的主分支 `047e214` 在工作区 (自上次审查以来合并了两次)`main`。 PR的源代码 —— `child_conversation`工具、请求/响应模型、路由器、`start_child_conversation` —— 与我审查的代码完全相同，而`conversation_service.py`则在周围进行了大量重构。 我重新阅读了回购指南并重新运行了重点套件： - `uv run pytest tests/tools/child_conversation tests/agent_server/test_parent_child_conversations.py -q` -> 30 通过 - `uv run pytest tests/agent_server/test_parent_child_conversations.py tests/tools/child_conversation tests/agent_server/test_conversation_router.py tests/agent_server/test_openapi_contract.py -q` -> 138 通过头状态：PR 打开，非草稿，`mergeable_state: unstable`，无 l
- [评论； APPROVED; neubig](https://github.com/OpenHands/software-agent-sdk/pull/5126#pullrequestreview-5554766486)：批准 - 感谢您采用共享助手路线。 `_launch_prepared_conversation` 作为正常和孩子的共同尾部，`RunSlot` 在任何工作树或持久化副作用之前获得，回归测试断言拒绝启动后没有任何遗留，解决了我之前的评论。 一个非阻塞 nit：新的 `POST /api/conversations/{conversation_id}/children` 路由声明 201/404/422 响应，但不是 429，这与另一个起始端点不同。 运行行为正确——全局处理器在达到运行限制时返回429，正如你的E2E运行所显示的——因此，这只是OpenAPI声明不完整。 很好在后续修复。 _此评论由 AI 智能体 (OpenHands) 代表 @gneubig._ 发布
- [review_comments; 评论； 全员机器人](https://github.com/OpenHands/software-agent-sdk/pull/5126#discussion_r4158508845): 执行器附上 `session_api_key_headers()` 到任何地方 `url` 解析为，和 `url` 是 `self.launch_url or default_launch_url(...)`. `launch_url` 来自工具规格的 `params`这些是按会话和用户提供的。 我已经验证了 `Tool(name="start_child_conversation", params={"launch_url": "https://cloud.example/children"})` 通过注册表给那个执行者 `launch_url`因此，控制对话创建的发起者可以发送请求，使服务器本身执行 `OH_SESSION_API_KEYS_0` / `SESSION_API_KEY` 值 `X-Session-API-Key` 到任意主机。 只在目标是服务器的根目录时才发送会话密钥 URL (或限制其他方面) `launch_url` 将值控制在服务器端，且需要 `https`  for an override.
- [review_comments; 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5126#discussion_r4251487481)：在 `send_message(..., True)` 运行之前，通过上面的 `_start_event_service` 调用（并附加到父级的 `sub_conversation_ids`），子级为已持久化。 `send_message`是通过`EventService.run`内的`RunSlot.acquire`获取运行许可，当服务器满时它会引发`ConversationRunLimitExceeded`； 早期 `except` 中的 `safe_rmtree(child_dir)` 仅涵盖生命周期块内的故障，因此它不会清除这种情况。 用 `max_concurrent_runs=1` 复制到这个头上，并保留插槽：发射引发 `ConversationRunLimitExceeded`，但 `_children_of(parent)` 之后包含新的子 ID，i.e。 一个无所事事、相互关联的孩子，其任务从未执行过。 正常启动通过在创建任何内容之前获取运行槽来避免这种情况（`_start_conversation`，第 1455 行）。 考虑在之前获得`RunSlot`
- [review_comments; 评论； hieptl](https://github.com/OpenHands/software-agent-sdk/pull/5126#discussion_r4291350525)：已在 93412f5 中修复。 `RunSlot` 子进程现在在一切准备就绪之前就获得了，就像 `_start_conversation` 一样，因此一个完整的服务器在 `ConversationRunLimitExceeded`（通过现有的处理器）之前（429 通过现有的处理器）就启动了，然后是工作树或子进程的持久化目录存在。 在特定于子项的准备之后，两条路径都经过相同的尾部（`_launch_prepared_conversation`）：生命周期锁并重新检查，`_start_event_service`，`send_message(..., False)`，`run(run_slot=...)`，Webhook通知。 由 `test_start_child_conversation_refused_when_run_limit_reached` 覆盖（`max_concurrent_runs=1`，槽位：启动引发，父级没有子级，没有为子级创建 `EventService`，不存在工作树目录），并针对以 `OH_MAX_CONCURRENT_RUNS=1` 启动且父级 w 启动的正在运行的服务器进行端到端复制
- [review_comments; 评论； hieptl](https://github.com/OpenHands/software-agent-sdk/pull/5126#discussion_r4291350777)：在没有注释的情况下提前解决这个问题是我的错误； 这里是对这个决策的解释，现在也记录在 `session_api_key_headers` 文档字符串 (93412f5)。 关键词是，如何启动器识别沙盒，它已经在为服务器的Webhook订阅者扮演相同的角色，这些订阅者`session_api_keys[0]`发送`X-Session-API-Key`到配置的Webhook URLs。 基于此合同（OpenHands/enterprise#433）构建的云启动器使用该密钥（`valid_sandbox`）进行认证，因此仅发送给服务器的根部 URL，或者要求 `https`，都会破坏消费者之间的缝合，以及本地启动器。 在信任模型中：`launch_url` 是由谁来设定的，智能体。 在托管部署中，控制平面首先生成沙箱的密钥。 在直接驱动的服务器上，
- [讨论； 评论； all-hands-bot](https://github.com/OpenHands/software-agent-sdk/pull/5126#issuecomment-5710992785): 👋 **在 OpenHands 可以查看它之前，此 PR 需要修复一些问题：** - PR 描述的 `HUMAN:` 部分需要至少 20 个字符来描述您测试的内容，而不仅仅是模板占位符。一旦解决此问题，此检查将自动重新运行，推送更新。 _这是一个自动检查 - 没有使用人工智能来生成此comment._
- [讨论； 评论； neubig](https://github.com/OpenHands/software-agent-sdk/pull/5126#issuecomment-6129598594): 非阻塞架构方面的建议：正常启动和子启动路径是否可以共享高层次创建生命周期，而不是仅`_start_event_service()`？ 针对子代的准备是有道理的：继承父代的已解决智能体和存储配置，衍生共享/工作树隔离，并设置父代链接。 但经过准备、接入、运行时启动/持久化、初始消息交付、调度、通知和失败处理后，应该与正常启动大体相同。 当前 `start_child_conversation()` 准备并保留子级，然后调用 `send_message(..., run=True)`，而正常启动在创建之前获取 `RunSlot`。 我用 `max_concurrent_runs=1` 重现了容量拒绝，并且插槽被占用：子发射提高了 `ConversationRunLimitExceeded`，但留下了一个持久性
- [讨论评论； hieptl](https://github.com/OpenHands/software-agent-sdk/pull/5126#issuecomment-6209065733)你好格雷姆，感谢您的建议和复制品。 我在 93412f5 这个共享助手路径上 `_launch_prepared_conversation(stored, launched, *, run_slot, initial_message, reuse_request=None)` 现在是两条路径的尾巴：生命周期锁并再次检查 ID `_start_event_service`交付初始消息， `run(run_slot=...)`读取状态 Webhook 通知。 `_create_conversation` 将请求传递给它 `reuse_request`所以，现有的重用-锁客户端选择的标识的行为没有改变。 子进程启动成功 None因此，碰撞也是一种错误，就像分支一样 `start_child_conversation` 获取了 `RunSlot` 在为子元素进行特定准备之前（父元素） 智能体，工作树计划（包括备份副本），与之完全相同 `_start_conversation`. 您的场景（`max_concurrent_runs=1`, slot occupied) now raises

<a id="unowned-changed-paths"></a>

## 无主改变路径

地图源前缀之外的路径分类如下。 测试/CI/文档路径本身不会添加面向智能体的路由。 所有权之外的产品模块是覆盖范围的差距，相关的系列扩展是显而易见的。

| 路径 | 分类 |
|---|---|
| `.agents/skills/pr-design-doc/SKILL.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/pr-design-doc/references/html-craft.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/SKILL.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/adaptation.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/daily.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F01-server-status.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F02-auth-and-sessions.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F03-deferred-init.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F04-conversation-lifecycle.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F05-run-pause-interrupt.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F06-conversation-events.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F07-session-socket.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F08-confirmation-security-secrets.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F09-model-switching-plugins.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F10-fork-navigate-condense-ask.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F11-goals.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F12-runtime-and-credentials.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F13-bash.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F14-files.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F15-git.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F16-workspace-serving-and-vscode.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F17-workspaces-registry.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F18-settings-and-secrets.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F19-mcp.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F20-llm-profiles.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F21-agent-profiles.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F22-meta-profiles.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F23-llm-catalog-and-connections.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F24-openai-subscription.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F25-skills.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F26-plugins.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F27-hooks-subagents-tools.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F28-canvas-extensions.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F29-app-backend-bridge.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F30-openai-gateway.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F31-persistence-and-limits.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F32-webhooks-and-telemetry.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F33-sdk-remote-client.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/F34-typescript-client.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/feature-map/README.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/maintenance.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/mapping.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/references/report.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/scripts/control-agent-server` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.agents/skills/verify-agent-server/scripts/control_agent_server.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/PULL_REQUEST_TEMPLATE.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/agent-server-openapi-weak-schema-allowlist.json` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/scripts/update_npm_pin.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/integration-runner.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/pip-revendoring-retirement.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/pr-artifacts.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/precommit.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/server.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/stale.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/storage-scenario.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.github/workflows/update-npm-pin.yml` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `.impeccable/config.json` | 没有当前源所有权的产品路径； 源波必须进行分类或扩展地图所有权。 |
| `AGENTS.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `CONTRIBUTING.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `MAINTAINERS` | 没有当前源所有权的产品路径； 源波必须进行分类或扩展地图所有权。 |
| `clients/typescript/README.md` | F34：实时客户端的消费者文档验证； 文档本身不添加运行时路径。 |
| `clients/typescript/config/public-type-budget.json` | F34：针对新的 ACP 发现类型更新了编译时导出类型预算； 不是运行时路线。 |
| `clients/typescript/package-lock.json` | F34（和F01兼容性/版本门）：包/依赖项锁更改； 针对 TARGET 运行构建的客户端。 |
| `examples/01_standalone_sdk/48_conversation_fork.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `openhands-agent-server/AGENTS.md` | 仅存储库指导； 没有面向智能体的运行时或模式更改。 |
| `openhands-agent-server/openhands/agent_server/docker/Dockerfile` | F01、F12、F16、F31：生产环境依赖项，Docker 运行时，移除 VS Code 从 Python-slim，打包/启动。 源启动不会验证生产镜像； 图像build/attach需要单独处理或明确禁止。 |
| `openhands-agent-server/openhands/agent_server/local_storage.py` | F04 F10 F15 F31：新的本地工作树所有权/删除辅助工具在删除对话工作树同时保留 git 分支和尊重共享分支工作区 (#5547)。 |
| `openhands-agent-server/pyproject.toml` | F01、F12、F31：服务器发布元数据和打包的依赖项； 依赖性变化扩大了全通范围并需要单独的生产工件资格。 |
| `openhands-sdk/openhands/sdk/__init__.py` | F23、F33、F34：现在导入公开 ACPModelOption 时，会通过模块 __getattr__ 发出弃用； ACP 发现取代了静态模型列表 (#5579)。 |
| `openhands-sdk/openhands/sdk/agent/acp_contracts.py` | F09、F12、F23、F33、F34：模型发现和运行时切换使用的共享遗留 ACP 会话模型响应类型 (#5579)； 验证发现消费者和对话消费者。 |
| `openhands-sdk/openhands/sdk/agent/acp_models.py` | F09, F12, F23, F33, F34: canonical ACPModelDiscovery/ACPModelDiscoveryError 模式添加模型元数据和结构化启动失败。 REST 和类型化客户端序列化这些。 |
| `openhands-sdk/openhands/sdk/agent/response_dispatch.py` | F06, F07, F08, F32, F33, F34: 将事件回调通过同步/异步确认分析转发到 SecurityAnalysisEvent，使其持久化并到达 socket/webhook/client 消费者 (#5182)。 |
| `openhands-sdk/openhands/sdk/conversation/base.py` | F10, F33: fork(title=...) 文档现在区分已弃用 LocalConversation 头衔和荣誉 RemoteConversation/服务器头衔 (#4814)； 此文件中没有新的运行时代码。 |
| `openhands-sdk/openhands/sdk/conversation/message_request.py` | F04、F05、F06、F07、F27、F33、F34：共享 SendMessageRequest 移至 SDK 以用于儿童对话启动器； 角色/内容/运行默认为已序列化 REST/会话/客户端输入 (#5126)。 |
| `openhands-sdk/openhands/sdk/llm/message.py` | F04、F06、F07、F09、F20、F22、F23、F30、F33、F34：共享多模式请求序列化现在在强制字符串序列化器时保留图像 (#5460)； 运行消息传输层和真实模型消费者，而不仅仅是目录读取。 |
| `openhands-sdk/openhands/sdk/llm/utils/AGENTS.md` | 仅存储库指导； 没有运行时路线。 它的模型能力约定为model_features.py的源审查提供了信息。 |
| `openhands-sdk/openhands/sdk/llm/utils/model_features.py` | F04、F09、F20、F22、F23、F30、F33、F34：DeepSeek 视觉、Haiku 缓存回退方案和 Bedrock 停用词选择退出的提供商能力更改； 共享模式的消费者需要扩展。 没有凭据的提供商仍然被命名为被阻止的功能。 |
| `openhands-sdk/openhands/sdk/llm/utils/openhands_provider.py` | F04、F09、F20、F22、F23、F30、F33、F34：提供商路由表添加 DigitalOcean 推理，同时保留 OpenHands 路由和显式 base_url； 通过目录/配置文件/模型消费者进行验证。 |
| `openhands-sdk/openhands/sdk/settings/__init__.py` | F18, F21, F23, F33, F34: 公共设置导出弃用用于 ACPModelOption，而不是添加一个新路由。 |
| `openhands-sdk/openhands/sdk/settings/acp_providers.py` | F09、F18、F21、F23、F33、F34：已弃用静态ACP模型元数据并澄清了独立出现的提供商合同； 比较新发现端点和类型化客户端导入。 |
| `openhands-sdk/openhands/sdk/tool/tool.py` | F27、F33：conversation_local ToolDefinition 标记允许子智能体' 状态本地工具，同时保留功能范围 (#5520)。 |
| `openhands-sdk/openhands/sdk/utils/files.py` | F14、F18、F20、F21、F22、F31：原子写入临时文件获得 .tmp 后缀和 is_temp_file 帮助程序； 轨迹存档会跳过运行中的临时文件 (#5538)，持久化消费者保留原子行为。 |
| `openhands-sdk/pyproject.toml` | F01, F33: SDK 发布元数据/依赖项； 依赖关系的变化也证明了完整的家庭通行证的合理性。 |
| `openhands-tools/openhands/tools/child_conversation/__init__.py` | F04、F27、F33、F34：新服务器拥有的 start_child_conversation 工具和可插入启动器的公共导出 (#5126)。 |
| `openhands-tools/openhands/tools/child_conversation/definition.py` | F04、F27、F33、F34：子创建、父关系和启动器的动作/观察契约； direct-tool/REST/client 观测结果需要覆盖（#5126）。 |
| `openhands-tools/openhands/tools/child_conversation/impl.py` | F04、F27、F33、F34：子启动执行、选择的存储配置文件、目录/工作树处理和报告的子身份 (#5126)。 |
| `openhands-tools/openhands/tools/delegate/impl.py` | F27 F33：子智能体继承了父MCP服务器，并允许在工作区/网络能力不扩展的情况下使用本地工具(#5747, #5520)。 |
| `openhands-tools/openhands/tools/file_editor/editor.py` | F14, F27, F33: file_editor 观测结果编号保留终端换行语义，并避免了伪造的空行 (#5670)。 单独的文件 APIs 无法证明模型可见工具的输出。 |
| `openhands-tools/openhands/tools/file_editor/utils/encoding.py` | F14、F27、F33：在启发式编码检测之前严格解码有效的 UTF-8 (#4784)； 练习非ASCII工具往返。 |
| `openhands-tools/openhands/tools/task_tracker/definition.py` | F27、F33：对话本地工具标记和待定/已完成/进行中状态别名的规范化（#5520、#6003）。 |
| `openhands-tools/openhands/tools/terminal/constants.py` | F13、F27、F33：较短的自适应终端轮询间隔 (#5715)，通过实际工具/SDK 运行可观察命令完成延迟。 |
| `openhands-tools/openhands/tools/terminal/terminal/terminal_session.py` | F13、F27、F33：自适应轮询保留超时并完成检测(#5715)； 练习真实的 tmux/子进程工具调用。 |
| `openhands-tools/openhands/tools/terminal/terminal/tmux_pane_pool.py` | F13、F27、F33：共享安全 tmux 套接字命名处理长目录 (#6038)； 验证直接工具和共用工具。 |
| `openhands-tools/openhands/tools/terminal/terminal/tmux_terminal.py` | F13、F27、F31、F33：私有 tmux 套接字所有权避免了活动同级会话的启动清理； 长路径回退方案适用于直接终端和池终端（#5589、#6038）。 |
| `openhands-tools/openhands/tools/terminal/utils/command.py` | F13、F27、F33：AST 命令边界保留有效的链接/多个定界符脚本 (#5342)； 需要直接终端配方。 |
| `openhands-tools/pyproject.toml` | F01、F27、F33：工具包发布元数据； 没有直接的新路线，验证组装服务器上的内置工具。 |
| `openhands-workspace/pyproject.toml` | F01、F12、F33：工作区包发布元数据； 没有直接的新路由，验证RemoteWorkspace和运行时消费者。 |
| `pyproject.toml` | 依赖项/包版本更改。 需要完整的现场通行证； 生产形象包装仍然是一项独特的能力。 |
| `tests/agent_server/canvas_extensions/test_canvas_extension_backend.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/canvas_extensions/test_canvas_extension_bridge.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/canvas_extensions/test_canvas_extension_bridge_routes.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/conftest.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/docker_runtime/STORAGE_SCENARIO.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/docker_runtime/test_mediation.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/docker_runtime/test_proxy.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/docker_runtime/test_storage_scenario.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/telemetry/test_telemetry_disabled_by_default.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/telemetry/test_telemetry_subscriber.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_acp_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_agent_launch_additions.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_agent_profile_conv_start.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_agent_profiles_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_api.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_auto_title_span_metadata.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_bash_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_bash_service.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_canvas_extensions_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_config.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_conversation_response.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_conversation_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_conversation_service.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_event_service.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_file_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_git_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_goal_loop.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_init_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_launch_architecture.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_launch_parity.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_llm_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_local_storage.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_mcp_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_openai_gateway_launch.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_openai_gateway_reused_wait.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_openai_gateway_settings.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_parent_child_conversations.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_plugins_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_preload_modules.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_profiles_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_run_admission.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_runtime_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_server_details_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_settings_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_skills_service.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_sub_agents_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_switch_llm_survives_reload.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_unhandled_exception_error_id.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_vscode_service.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_webhook_subscriber.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_websocket_first_message_auth.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_workspace_cookie_auth.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/agent_server/test_workspaces_router.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/cross/conftest.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/cross/test_agent_server_build_metadata.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/cross/test_remote_conversation_live_server.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/cross/test_update_npm_pin.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/cross/test_verify_agent_server_skill.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/integration/README.md` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/integration/tests/c02_hard_context_reset.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/integration/tests/c04_token_condenser.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/agent/fake_acp_models_server.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/agent/test_acp_agent.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/agent/test_acp_conformance.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/agent/test_acp_model_discovery.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/agent/test_async_secret_masking.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/agent/test_security_analysis_event.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/conversation/local/test_fork.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/conversation/remote/test_remote_conversation.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/conversation/remote/test_remote_events_list.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/conversation/test_local_conversation_plugins.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/conversation/test_switch_model.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/extensions/test_fetch.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/git/test_cached_repo.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/git/test_git_changes.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/git/test_git_diff.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/launch/fakes.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/launch/test_field_ownership.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/launch/test_preview.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/launch/test_resolve.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/auth/test_openai.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_llm.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_llm_log_completions_integration.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_message.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_meta_profile_store.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_model_features.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_model_list.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/llm/test_vision_support.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/marketplace/test_marketplace_registry.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/mcp/test_create_mcp_tool.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/plugin/test_agent_plugins_format.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/plugin/test_installed_plugins.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/plugin/test_plugin_strict_fetch.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/profiles/test_agent_profile.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/profiles/test_profile_refs.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/profiles/test_resolver.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/security/defense_in_depth/test_policy_rails.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/security/defense_in_depth/test_shell_semantics.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/security/test_shell_ast.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/settings/test_acp_providers.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/skills/test_installed_skills.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/skills/test_load_public_skills.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/subagent/test_subagent_registry.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/subagent/test_subagent_scope.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/tool/test_mcp_schema.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/utils/test_files.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/sdk/utils/test_redact.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/child_conversation/test_start_child_conversation.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/file_editor/test_basic_operations.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/file_editor/utils/test_encoding.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/task/mcp_echo_server.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/task/test_mcp_inheritance.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/task/test_sub_agent_scope.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/task_tracker/__init__.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/task_tracker/test_task_tracker_status.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/terminal/test_terminal_parsing.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/terminal/test_terminal_session.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `tests/tools/terminal/test_tmux_pane_pool.py` | 测试、CI、文档、示例或验证工具； 没有直接产品 API 变化。 |
| `uv.lock` | 依赖项/包版本更改。 需要完整的现场通行证； 生产形象包装仍然是一项独特的能力。 |

<a id="explicit-reconciliation-of-map-owners-gaps"></a>

## 地图所有者差距的明确协调

`map-owners.json` 中报告的所有 36 条路径均在下面分配。 如果适用，这将取代上述临时通用分类。 共享模式和提供商的能力在其消费者中得到扩展。 运行时覆盖率是一项单独的证据要求。

| 无主路径 | 所有权或非智能体面的原因 |
|---|---|
| `clients/typescript/README.md` | F34：实时客户端的消费者文档验证； 文档本身不添加运行时路径。 |
| `clients/typescript/config/public-type-budget.json` | F34：针对新的 ACP 发现类型更新了编译时导出类型预算； 不是运行时路线。 |
| `clients/typescript/package-lock.json` | F34（和F01兼容性/版本门）：包/依赖项锁更改； 针对 TARGET 运行构建的客户端。 |
| `openhands-agent-server/AGENTS.md` | 仅存储库指导； 没有面向智能体的运行时或模式更改。 |
| `openhands-agent-server/openhands/agent_server/docker/Dockerfile` | F01、F12、F16、F31：生产环境依赖项，Docker 运行时，移除 VS Code 从 Python-slim，打包/启动。 源启动不会验证生产镜像； 图像build/attach需要单独处理或明确禁止。 |
| `openhands-agent-server/openhands/agent_server/local_storage.py` | F04 F10 F15 F31：新的本地工作树所有权/删除辅助工具在删除对话工作树同时保留 git 分支和尊重共享分支工作区 (#5547)。 |
| `openhands-agent-server/pyproject.toml` | F01、F12、F31：服务器发布元数据和打包的依赖项； 依赖性变化扩大了全通范围并需要单独的生产工件资格。 |
| `openhands-sdk/openhands/sdk/__init__.py` | F23、F33、F34：现在导入公开 ACPModelOption 时，会通过模块 __getattr__ 发出弃用； ACP 发现取代了静态模型列表 (#5579)。 |
| `openhands-sdk/openhands/sdk/agent/acp_contracts.py` | F09、F12、F23、F33、F34：模型发现和运行时切换使用的共享遗留 ACP 会话模型响应类型 (#5579)； 验证发现消费者和对话消费者。 |
| `openhands-sdk/openhands/sdk/agent/acp_models.py` | F09, F12, F23, F33, F34: canonical ACPModelDiscovery/ACPModelDiscoveryError 模式添加模型元数据和结构化启动失败。 REST 和类型化客户端序列化这些。 |
| `openhands-sdk/openhands/sdk/agent/response_dispatch.py` | F06, F07, F08, F32, F33, F34: 将事件回调通过同步/异步确认分析转发到 SecurityAnalysisEvent，使其持久化并到达 socket/webhook/client 消费者 (#5182)。 |
| `openhands-sdk/openhands/sdk/conversation/base.py` | F10, F33: fork(title=...) 文档现在区分已弃用 LocalConversation 头衔和荣誉 RemoteConversation/服务器头衔 (#4814)； 此文件中没有新的运行时代码。 |
| `openhands-sdk/openhands/sdk/conversation/message_request.py` | F04、F05、F06、F07、F27、F33、F34：共享 SendMessageRequest 移至 SDK 以用于儿童对话启动器； 角色/内容/运行默认为已序列化 REST/会话/客户端输入 (#5126)。 |
| `openhands-sdk/openhands/sdk/llm/message.py` | F04、F06、F07、F09、F20、F22、F23、F30、F33、F34：共享多模式请求序列化现在在强制字符串序列化器时保留图像 (#5460)； 运行消息传输层和真实模型消费者，而不仅仅是目录读取。 |
| `openhands-sdk/openhands/sdk/llm/utils/AGENTS.md` | 仅存储库指导； 没有运行时路线。 它的模型能力约定为model_features.py的源审查提供了信息。 |
| `openhands-sdk/openhands/sdk/llm/utils/model_features.py` | F04、F09、F20、F22、F23、F30、F33、F34：DeepSeek 视觉、Haiku 缓存回退方案和 Bedrock 停用词选择退出的提供商能力更改； 共享模式的消费者需要扩展。 没有凭据的提供商仍然被命名为被阻止的功能。 |
| `openhands-sdk/openhands/sdk/llm/utils/openhands_provider.py` | F04、F09、F20、F22、F23、F30、F33、F34：提供商路由表添加 DigitalOcean 推理，同时保留 OpenHands 路由和显式 base_url； 通过目录/配置文件/模型消费者进行验证。 |
| `openhands-sdk/openhands/sdk/settings/__init__.py` | F18, F21, F23, F33, F34: 公共设置导出弃用用于 ACPModelOption，而不是添加一个新路由。 |
| `openhands-sdk/openhands/sdk/settings/acp_providers.py` | F09、F18、F21、F23、F33、F34：已弃用静态ACP模型元数据并澄清了独立出现的提供商合同； 比较新发现端点和类型化客户端导入。 |
| `openhands-sdk/openhands/sdk/tool/tool.py` | F27、F33：conversation_local ToolDefinition 标记允许子智能体' 状态本地工具，同时保留功能范围 (#5520)。 |
| `openhands-sdk/openhands/sdk/utils/files.py` | F14、F18、F20、F21、F22、F31：原子写入临时文件获得 .tmp 后缀和 is_temp_file 帮助程序； 轨迹存档会跳过运行中的临时文件 (#5538)，持久化消费者保留原子行为。 |
| `openhands-sdk/pyproject.toml` | F01, F33: SDK 发布元数据/依赖项； 依赖关系的变化也证明了完整的家庭通行证的合理性。 |
| `openhands-tools/openhands/tools/child_conversation/__init__.py` | F04、F27、F33、F34：新服务器拥有的 start_child_conversation 工具和可插入启动器的公共导出 (#5126)。 |
| `openhands-tools/openhands/tools/child_conversation/definition.py` | F04、F27、F33、F34：子创建、父关系和启动器的动作/观察契约； direct-tool/REST/client 观测结果需要覆盖（#5126）。 |
| `openhands-tools/openhands/tools/child_conversation/impl.py` | F04、F27、F33、F34：子启动执行、选择的存储配置文件、目录/工作树处理和报告的子身份 (#5126)。 |
| `openhands-tools/openhands/tools/delegate/impl.py` | F27 F33：子智能体继承了父MCP服务器，并允许在工作区/网络能力不扩展的情况下使用本地工具(#5747, #5520)。 |
| `openhands-tools/openhands/tools/file_editor/editor.py` | F14, F27, F33: file_editor 观测结果编号保留终端换行语义，并避免了伪造的空行 (#5670)。 单独的文件 APIs 无法证明模型可见工具的输出。 |
| `openhands-tools/openhands/tools/file_editor/utils/encoding.py` | F14、F27、F33：在启发式编码检测之前严格解码有效的 UTF-8 (#4784)； 练习非ASCII工具往返。 |
| `openhands-tools/openhands/tools/task_tracker/definition.py` | F27、F33：对话本地工具标记和待定/已完成/进行中状态别名的规范化（#5520、#6003）。 |
| `openhands-tools/openhands/tools/terminal/constants.py` | F13、F27、F33：较短的自适应终端轮询间隔 (#5715)，通过实际工具/SDK 运行可观察命令完成延迟。 |
| `openhands-tools/openhands/tools/terminal/terminal/terminal_session.py` | F13、F27、F33：自适应轮询保留超时并完成检测(#5715)； 练习真实的 tmux/子进程工具调用。 |
| `openhands-tools/openhands/tools/terminal/terminal/tmux_pane_pool.py` | F13、F27、F33：共享安全 tmux 套接字命名处理长目录 (#6038)； 验证直接工具和共用工具。 |
| `openhands-tools/openhands/tools/terminal/terminal/tmux_terminal.py` | F13、F27、F31、F33：私有 tmux 套接字所有权避免了活动同级会话的启动清理； 长路径回退方案适用于直接终端和池终端（#5589、#6038）。 |
| `openhands-tools/openhands/tools/terminal/utils/command.py` | F13、F27、F33：AST 命令边界保留有效的链接/多个定界符脚本 (#5342)； 需要直接终端配方。 |
| `openhands-tools/pyproject.toml` | F01、F27、F33：工具包发布元数据； 没有直接的新路线，验证组装服务器上的内置工具。 |
| `openhands-workspace/pyproject.toml` | F01、F12、F33：工作区包发布元数据； 没有直接的新路由，验证RemoteWorkspace和运行时消费者。 |
