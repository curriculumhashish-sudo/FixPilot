<a id="migration-guide"></a>

# 迁移指南

使用本指南将现有插件映射到智能体 Plugins v1 可移植核心，同时保持客户端特定行为可用。

<a id="1-inventory-before-conversion"></a>

## 1. 转换前的库存

找到所有插件清单和组件根。 常见的遗留或特定于客户的工件包括：

- `.claude-plugin/plugin.json`、`.plugin/plugin.json`、`.github/plugin/plugin.json`、`.codex-plugin/plugin.json` 或不带智能体插件 `$schema` 的根清单。
- `skills/`、`.agents/skills/`、`.github/skills/`、`.claude/skills/` 或配置的自定义路径下的技能。
- `.mcp.json`、`.github/mcp.json` 中的 MCP 配置、另一个客户端配置或内联清单字段。
- `hooks.json`、`hooks/hooks.json`、设置文件或内联清单字段中的挂钩。
- 命令、提示词、自定义智能体、LSP 服务器、UI 资产、身份验证声明和市场目录。

在知道其使用者和替代者之前，请勿删除或移动任何内容。

<a id="2-map-every-artifact"></a>

## 2. 绘制每个工件的地图

| 现有神器 | 智能体插件 v1 目标 | Compatibility action |
| --- | --- | --- |
| 插件身份和元数据 | 根`plugin.json` | 仅当目标客户端仍然需要时才保留旧清单。 尽可能从一个来源生成副本。 |
| 可重复使用的技能 | `skills/<name>/SKILL.md` | 规范化前置元数据并将脚本、引用和资产保留在技能目录中。 |
| MCP 服务器 | 根`mcp.json` | 转换客户端特定字段并声明显式传输层类型。 仅为不支持的字段或传输层保留客户端适配器。 |
| 钩子 | 没有便携式 v1 目的地 | 使用客户端拥有的扩展命名空间或保留客户端兼容性包。 |
| 自定义智能体或角色 | 没有便携式 v1 目的地 | 将其保存在客户端扩展或兼容包中。 仅当按需指令真正保留其语义时才转换为技能。 |
| 命令或提示词 | 没有便携式 v1 目的地 | 在适当的时候将可重复使用的任务指令转换为技能； 否则保留客户端功能。 |
| LSP 服务器 | 没有便携式 v1 目的地 | 将其保留为客户端扩展或兼容性包。 |
| UI 或应用程序集成 | 没有便携式 v1 目的地 | 将其保留为客户端扩展或兼容性包。 |
| 市场进入、安装策略、签名 | 便携式包装外 | 将其保存在平台的分发存储库或发布流程中。 |

<a id="3-create-the-portable-manifest"></a>

## 3. 创建便携式清单

从最小的有效根清单开始：

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "your-plugin"
}
```

允许的可选字段为 `version`、`description`、`author`、`homepage`、`repository`、`license`、`keywords` 和 `extensions`。 模式已关闭。 即使特定客户端历史上接受过未知的顶级字段，它们也是不合格的。

插件名称应为1到64个字符，使用小写字母 ASCII，数字，连字符，和点，以一个或多个字母或数字开头和结尾，并且不能包含 `--` 或 `..`。

<a id="4-normalize-skills"></a>

## 4. 技能标准化

每个可发现的技能必须是 `skills/` 的直接子级：

```text
skills/
└── deploy/
    ├── SKILL.md
    ├── scripts/
    ├── references/
    └── assets/
```

`SKILL.md` 名称必须与其父目录匹配。 将与技能相关的依赖项保留在该目录内，并在移动文件后更新引用。 不要依赖嵌套技能目录的递归发现。

<a id="5-convert-mcp-configuration"></a>

## 5. 转换 MCP 配置

可移植的 MCP 配置属于根 `mcp.json`，而不是内联于 `plugin.json`：

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "example": {
      "type": "stdio",
      "command": "node",
      "args": ["${PLUGIN_ROOT}/server/index.js"],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
```

对 `command` 使用单个可执行文件 token； 不要在该字段中放置 shell 命令行。 捆绑的可执行文件使用相对插件`./path`。 非环回远程服务器使用HTTPS。 不要将机密嵌入远程标头中。

<a id="6-preserve-platform-behavior"></a>

## 6. 保留平台行为

迁移首先应该是累加的：

1. 添加可移植根清单和组件。
2. 保持工作客户端包完好无损。
3. 让便携式文件成为事实来源。
4. 仅当客户文档需要时才生成或复制旧适配器。
5. 测试每个受支持的客户端。
6. 仅在用户迁移后才删除旧文件。

存储库可以将可移植插件和客户端适配器保持为同级：

```text
repository/
├── plugin/                 # Agent Plugins v1 portable package
└── client-adapters/        # Generated or maintained platform packages
    ├── client-a/
    └── client-b/
```

适配器不是便携式核心的一部分。 清楚地标记哪些文件是规范的，并在必须发送多个清单或布局时自动同步。

<a id="7-test-the-migration"></a>

## 7. 测试迁移

至少测试：

- 使用符合要求的智能体插件客户端加载插件。
- 技能发现和激活。
- 每个 MCP 传输层和工具（如果存在）。
- [legacy installation and all retained hooks] 智能体，commands, LSP, 或 UI 行为。
- 从上次发布的客户端特定包进行升级和回滚。

仅当可移植核心验证并且承诺的客户端行为仍然有效时，迁移才完成。
