<a id="independently-reviewed-observations"></a>

# 独立审查观测结果

问题 JSON 文件保留源运行 ID、签出 SHA、选定的交换和 SHA-256 出处。 这些观测结果与原始工件进行了检查； 它们的状态不仅仅从地图摘要中推断出来。

| 寻找 | 审查控制 | 审查失败 |
|---|---|---|
| [第39期](https://github.com/enyst/agent-sdk/issues/39) | 显式`repo_path: "skills/github"`与`name: "github"`返回200； GET是200，DELETE是200，后续的GET是404。 | 嵌入 `/skills/github` 的同一公共存储库返回 422：`Invalid skill. Ensure the source contains a valid SKILL.md.` 两个新的尝试都一致。 |
| [第40期](https://github.com/enyst/agent-sdk/issues/40) | 普通瞬态 HTTP 429 给出 `{"valid":true,"error":null}`； 配置文件列表等于其前验证值。 | 本地HTTP提供商记录为429，`error.type`和`error.code`均等于`insufficient_quota`； 现场验证端点仍然返回 `{"valid":true,"error":null}`。 两种新的尝试都一致。 |
| [第41期](https://github.com/enyst/agent-sdk/issues/41) | 实时 OpenHands 配置文件和具体化响应均包含 `public_skills: null`。 生成的合约密钥形状进行编译。 | 导出的 `OpenHandsAgentProfile` 和 `AgentProfileDiagnostics` 均拒绝与 TS2353 相同的密钥。 每次尝试独立地重新运行捕获的编译器测试夹具都会给出生成合约出口 0 和导出类型出口 2。 |
| [第42期](https://github.com/enyst/agent-sdk/issues/42) | 显式 `isolation: "shared"` 返回 201，并且该子级到达 `finished`。 相同的测试夹具有 `.git` 但没有 HEAD 提交，由只读 `rev-parse --verify HEAD` 独立确认（出口 128）。 | 省略隔离会返回 500，其中包含 `Git command failed: git worktree add ... HEAD`。 两种新的尝试都一致。 |

TypeScript 诊断是：

```text
error TS2353: Object literal may only specify known properties, and '"public_skills"' does not exist in type 'Shape<OpenHandsAgentProfile>'.
error TS2353: Object literal may only specify known properties, and '"public_skills"' does not exist in type 'Shape<AgentProfileDiagnostics>'.
```

还直接检查了两个退役标记：

- `F10.fork-tags-consistent`：每次 BASE 运行都会观察到 GET `tags.qa` 不存在 (`null`)，但已持久化标签断言返回 `src`； 每次 TARGET 运行都会观察到 `null` 两侧。 源标签仍然存在 `src`，因此控件显示存在预期的设置。 在删除之前，两个 BASE 都尝试 xfail，两个 TARGET 都尝试 xpass。
- `F14.trajectory-init-path`：延迟初始化达到`ready`，并且新创建的会话在每次尝试中都是可读的。 每个 BASE 全局轨迹请求都会返回 404 并在其范围请求之前停止配方。 每次 TARGET 运行都会针对全局和范围轨迹请求返回 200。 因此，没有声明范围内的 BASE 请求。

仅发布选定的公共字段、断言结果和编译器诊断。 原始载荷、私有目录、密钥材料、完整服务器日志和原始凭据交换被排除在外。 单独的扫描记录准确的已知机密比较和格式检查； 这是一项额外的检查，而不是对每个未知数的保证机密。
