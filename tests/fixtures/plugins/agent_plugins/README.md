<a id="agent-plugins-fixture-corpus"></a>

# 智能体插件测试夹具语料库

签入 [智能体 Plugins](https://agent-plugins.org) v1.0.0 软件包，使用者

- `tests/sdk/plugin/test_agent_plugins_conformance.py` — 客户端一致性检查表，每项一项测试，通过 `Plugin.load()` 驱动。
- `tests/sdk/conversation/test_local_conversation_agent_plugins.py` — 相同的软件包一直驱动到配置的 `Conversation`。

每个包都按原样从磁盘加载。 测试时不会获取任何内容，因此该套件离线运行。

| 套餐 | 它的用途是什么 |
| --- | --- |
| `agent-plugins-example/` | 官方示例插件，逐字提供（见下文）。 仅限技能。 |
| `full-package/` | SDK 实现的每个组件类型：技能、同时支持传输层的 `mcp.json` 和 `dev.openhands` 扩展（清单数据加命令、智能体和挂钩）。 |
| `manifest-only/` | 一个清单，仅此而已——每个固定的组件位置都不存在。 |
| `non-fatal-manifest/` | 包含规范标记为非致命的两种违规：未知的顶级字段和非对象 `extensions`。 |
| `unsupported-schema/` | 声明 `1.1.0`，这是此 SDK 不提供的已发布模式版本。 |
| `fatal-manifest/` | 违反第 5.5 条的 `name`。 提供一项绝不能被发现的技能和`mcp.json`。 |
| `partial-failures/` | 每个组件类型都有一条损坏的条目：一个损坏的技能，一个损坏的智能体，以及五个MCP条目，必须单独跳过（不支持`sse` 传输层，逃逸`command`，一个`${PLUGIN_ROOT}` `command`，必须不展开，逃逸`cwd`，纯-`http`远程URL]。 它的 `good-server` 既不包含 `args` 也不包含 `cwd`，因此它也固定 stdio 默认值。 |
| `wrong-locations/` | Claude Code 布局（`.mcp.json`、`hooks/`、`commands/`、`agents/`）加上不受支持的 `lsp/` 组件类型，全部位于根目录。 只有`skills/`才能加载。 |
| `mcp-version-mismatch/` | 目标为 1.1.0 的 `mcp.json` 旁边的 1.0.0 清单：MCP 已禁用，但技能未禁用。 |

<a id="the-vendored-example-plugin"></a>

## 供应的示例插件

`agent-plugins-example/` 是逐字副本
[agentplugins/agent-plugins-example](https://github.com/agentplugins/agent-plugins-example)
在提交 `5f3f5084a821aefa792e79500dd8f0462ab83473` (2026-08-05)，MIT 获得许可。

它被 vendored 而不是 fetched，因此测试 conformance 声明时，不添加任何网络触及的测试，而是直接测试 PR 端口的真正上游字节。 要刷新它，请用新的签出目录替换该目录并更新上面的提交。

<a id="adding-a-package"></a>

## 添加包

保持每个包的最小化和单一用途：每个包有一个故障边界，以它所引脚的行为命名。 一个包永远不能加载它本来会贡献的组件，因此测试可以断言它们未被发现。
