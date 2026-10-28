<a id="validation-checklist"></a>

# 验证清单

<a id="package"></a>

## 套餐

- [ ] `plugin.json` 是插件根目录下的常规文件。
- [ ] 每个打包或解析的路径都保留在插件根目录内。
- [ ] 符号链接、连接点和重分析点不会逃逸包。
- [ ] 包中未嵌入凭据、token 或私钥。

<a id="manifest"></a>

## 清单

- []`$schema`是`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`。
- [ ] `name` 满足v1长度和字符规则。
- [ ] 仅 `$schema`、`name`、`version`、`description`、`author`、`homepage`、`repository`、`license`、`keywords` 和 `extensions` 出现在顶层。
- [ ] 每个 `extensions` 成员都是一个由反向域命名空间作为键控的对象。
- [ ] 可选元数据具有模式所需的类型。

<a id="skills"></a>

## 技能

- [ ] 每个技能都是 `skills/` 的直接子目录。
- [ ] 每个技能都包含一个名为 `SKILL.md` 的常规文件。
- [ ] 前置元数据 `name` 匹配目录名称和智能体技能命名规则。
- [ ] `description` 解释了该技能的作用以及何时使用它。
- [ ] 引用的脚本、引用和资产存在于技能目录中。
- [ ] 每个技能独立验证； 一项无效技能不应掩盖另一项技能的失败。

<a id="mcp-when-present"></a>

## MCP，当存在时

- [ ] 根 `mcp.json` 使用 `https://agent-plugins.org/schemas/1.0.0/mcp.schema.json`。
- [ ] 其规格版本与`plugin.json` 匹配。
- [ ] 每个服务器都声明一个受支持的传输层变体。
- [ ] `command` 是一个可执行文件 token，而不是 shell 命令字符串。
- [ ] 插件相关的可执行路径和工作目录以 `./` 开头。
- [ ] `${PLUGIN_ROOT}` 和 `${PLUGIN_DATA}` 仅出现在定义了扩展的字段中。
- [ ] 远程非环回 URLs 使用 HTTPS 和包含凭据。

## Client compatibility

- [ ] 每个客户端扩展都使用由其所属客户端实现和记录的命名空间。
- [ ] 挂钩、智能体、命令、LSP、UI 和市场元数据不作为可移植 v1 组件呈现。
- [ ] 兼容性包仍然可供仍需要旧版布局的客户端使用。
- [ ] 在可行的情况下，可移植清单和遗留清单是从一个元数据源生成的。
- [ ] 每个受支持的客户端都通过了安装、更新、回滚和行为冒烟测试。

<a id="handoff"></a>

## 切换

- [ ] 迁移报告将每个原始工件映射到其新所有者和位置。
- [ ] 已删除的文件具有经过验证的替换和恢复路径。
- [ ] 记录了其余限制和手动发布步骤。
