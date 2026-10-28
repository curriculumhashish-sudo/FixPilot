<a id="reviewed-verification-evidence"></a>

# 审查验证证据

此数据包总结了 TARGET 处 `enyst/agent-sdk` 的实时检查
`5966c781ed014efc96c028a99bddd4ff78426741` 于 2026 年 10 月 23 日 UTC。 它包含选定的断言和出处，而不是完整的记录。 独立审查记录在 [review-notes.md](review-notes.md) 和
[independent-review.json](independent-review.json).

- `issue-39-skill-subpath.json` 至 `issue-42-child-unborn.json`：各两个新鲜复制品，及其阳性对照。
- `retired-known-bugs.json`：F10 标签一致性和 F14 初始化时间轨迹路径在标记删除之前分别在 BASE 处再现为 xfail 两次，在 TARGET 处再现为 xpass 两次。
- `docker-results.json`：真实的Docker生命周期/保留证明和两次启动截止日期通行证； 明确说明发布图像限制。
- `runtime-supplements.json`：独立检查F31保留/磁盘预算和F33同步/异步SDK生命周期观测结果，包括其精确的最新维护的地图重播； F31仍然是独立的补充证据，并且保留了被释放儿童的限制。
- `feature-results.json` / `feature-results.md`: 服务条款、运行ID、分支和源代码 SHAs。 这些元数据表不能替代上面选定的交换。
- `capability-lanes.json` 精确聚焦 F16 OpenVSCode URL/编辑回放和独立审查 F17 不可变存储交换，其中冻结源身份和隔离能力设置。
- `provenance.json`：源运行 ID、相关证据名称和用于本地可追溯性的 SHA-256 校验和。
- `publication-scan.json`：根据配置的环境机密值和常见凭据格式扫描策划的输出。

私有目录、密钥、环境转储、原始凭据交换、原始对话状态和完整服务器日志均被排除在外。 临时绝对路径和本地服务器地址已标准化。 SHA-256 校验和指原始本地工件，不包含在此数据包中。

发布目录仅包含精选的公共文件。 规范的原始 CLI 报告单独保留在该目录之外。 重新生成最终的每个功能快照后重新运行发布扫描。
