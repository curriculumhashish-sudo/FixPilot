<a id="follow-up-product-fixes--2026-10-23"></a>

# 后续产品修复 — 2026-10-23

四个单独的草案 PR 解决了 [ 完整验证通过 ](verification-report.md) 发现的四个新缺陷。 每个都使用基于冻结分叉提交 `5966c781ed014efc96c028a99bddd4ff78426741` 的隔离工作树。 所有问题、分支和 PR 都在 `enyst/agent-sdk` 中； 上游没有合并或写入任何内容。

这些结果与维护快照是分开的。 他们不会更改其 **864 个通过、82 个已知错误 xfail、1 个被阻止和 1 个退役 ** 条目，也不会提前接受的基线。 产品PR不包括维护配方的变更。 他们的重点重播使用 [PR #43](https://github.com/enyst/agent-sdk/pull/43) 中的 CLI，`--checkout` 选择每个固定源树。

<a id="changes-and-regression-protection"></a>

## 变更和回归保护

| 缺陷 | 修复PR | 结果 | 自动检查 |
| --- | --- | --- | --- |
| [#39](https://github.com/enyst/agent-sdk/issues/39)：嵌入技能路径返回422 | [#44](https://github.com/enyst/agent-sdk/pull/44) | 获取程序和安装程序共享解析的源/子路径信息，保留嵌入路径名称和存储库根命名。 | 156 SDK 个扩展/技能/插件测试和 93 个服务器技能测试通过。 新的 real-Git 回归在补丁发布之前就失败了。 取消了三项网络标记测试； 实际 GitHub 安装是实时进行的。 |
| [#40](https://github.com/enyst/agent-sdk/issues/40): 配额耗尽验证成功 | [#47](https://github.com/enyst/agent-sdk/pull/47) | 精确的结构化配额代码通过保留的原因/上下文链在提供者异常规范化中幸存下来。 普通费率限制仍为重试； 配额许可证模型回退方案； 预算拒绝停止回退方案。 | 272 个相关测试通过，包括 20 个同步/异步聊天/响应 HTTP 个案例和回退方案个控件。 新的传输层矩阵在补丁发布之前失败了 8 种情况。 |
| [#41](https://github.com/enyst/agent-sdk/issues/41)：缺少TypeScript`public_skills` | [#46](https://github.com/enyst/agent-sdk/pull/46) | 公共配置文件和诊断类型公开可选的可为空字段。 合约测试现在实际上调用 TypeScript 编译器，因此仅类型断言无法静默地通过转译。 | 27 个文件中的 396 项测试通过，加上构建、静态检查和格式化。 在添加字段之前，编译器支持的回归失败了。 静态检查报告未触及的文件中存在五个预先存在的警告。 |
| [#42](https://github.com/enyst/agent-sdk/issues/42)：在新的工作区中子启动失败 | [#45](https://github.com/enyst/agent-sdk/pull/45) | 没有可用提交的存储库使用现有的共享工作区回退方案并报告隔离。 提交的存储库保留工作树和上游跟踪； 没有创建初始提交。 | 41个测试通过，包括一个真实的HTTP 回归，父文件/索引/HEAD保留，已提交/子目录工作树，以及一个有可用远程基的未出生HEAD。 |

所有更改的代码都通过文件范围的存储库预提交检查。 独立审查涵盖了每个产品补丁及其之前/之后的证据。 子评论在第一个补丁中捕获了一个上游跟踪回归：验证提交并将其SHA传递给`git worktree add`丢失了远程跟踪配置。 更正后的补丁验证了所选的引用，但保留了该引用以用于工作树创建； 一个断言首先重现了损失，现在又通过了。

<a id="exact-source-and-live-proof"></a>

## 确切来源和现场证据

在启动证明服务器之前已提交产品代码和回归测试。 医生和运行元数据可识别这些确切的修订。 稍后的仅证据提交不会更改测试的产品代码。

| 问题 | 测试产品修订版 | 新鲜固定运行 | 已审核数据包 |
| --- | --- | --- | --- |
| #39 | `31897798e8bd8e62ef56bdb86dba6588efbbc557` | `20261023-065443-4190-map-f25`, `20261023-065459-fd2d-map-f25` | [命令和HTTP交换](https://github.com/enyst/agent-sdk/blob/1973797e6a6d8ff7ecc9993cf990663d918c7aa1/.pr/fix-39-verification.md) |
| #40 | `06a52395b85039fa5b9c9d0ce18f7085a8b942ab` | `20261023-070627-5271-map-f20`, `20261023-070641-8fe2-map-f20` | [命令和HTTP交换](https://github.com/enyst/agent-sdk/blob/fd5d519e14c9f6bf8c0ad7177d80429fb3147d8b/.pr/quota-validation-evidence.md) |
| #41 | `c250e521e1f0d7e091ce7599a626945bd6c7943a` | `20261023-070220-2697-map-f21`, `20261023-070238-9833-map-f21` | [实时载荷和编译器结果](https://github.com/enyst/agent-sdk/blob/c567fc33340e3a60a0823b5bead10b686354fcbe/.pr/issue-41-evidence.json) |
| #42 | `b2c0490647963cb877d1f0c20394311fa245d6d4` | `20261023-071012-2856-map-f04`, `20261023-071101-a644-map-f04` | [命令和观测结果](https://github.com/enyst/agent-sdk/blob/0178da1e0e66fb0753e122d5eea6577baba8f3b4/.pr/issue-42-evidence.md) |

原始冷冻源将每个缺陷再现两次。 所有四个固定对都报告 **XPASS**，因为单独的维护分支仍然标记其冻结目标处存在的缺陷。 这是预期的修复验证结果：食谱断言返回0，而CLI摘要返回1以标记已更改的已知缺陷状态。 这不是无法解释的测试失败。 每对还保留其传球设置和独特的控制，意外故障或阻碍为零。

对于 #42，修正后的源代码还额外通过了新鲜的实模型工具运行 `20261023-071023-f9ef-fix42-default-child-tool`. 父类调用 `start_child_conversation` 没有隔离论据。 孩子完成，共享隔离被报告，出现在孩子列表中，离开父母的未出生状态 HEAD 通过删除，保留现有文件的完整。 早期的证明 `46ba8bda` 保留作为初始实现的证据，而不是替换为修正后的源代码。

#41 号现场证明使用了官方的 Node 24.21.0，而在此之前在环境的默认 Node 24.19.0 上的尝试在生成合约编译器中失败了。 该拥有的尝试通过协调器清理被停止并保留。 相同的编译器命令在 Node 24.21.0 上完成，然后完整的新对就通过了，没有产品解决方法。

<a id="limits-and-handoff"></a>

## 限制和交接

这些修复是在本地 Linux 源服务器上进行的。 技能安装使用实际的公共GitHub存储库。 子工作流程使用 DeepSeek flash。 配额分类通过真实的 SDK/LiteLLM/OpenAI 传输层使用确定性环回 HTTP 提供者； 它不声明外部计费提供商的行为。 TypeScript 针对修复的工作树自己生成的和公共客户端构建进行实时编译证明载荷。 此后续行动不声称 Agent Canvas UI 覆盖范围或基准测试结果。

GitHub CI 仍在等待中。 已完成的当前水头检查显示最近一次检查没有出现任何故障； 几个更广泛的 Python 作业仍在 `blacksmith-2vcpu-ubuntu-2404` 上排队。 PR #45 具有其工具描述更改所需的 `integration-test` 标签。 它的[早期模型集成结果](https://github.com/enyst/agent-sdk/pull/45#issuecomment-6359527253)报告**0/50通过，因为分支缺少`LLM_API_KEY`和`LLM_BASE_URL`**，尽管工作流已经成功结束。 该运行使用了被取代的头`691d720`，并且既不提供基准测试也不提供最终头证明。 上述本地测试/实时结果独立于这些远程 CI 限制。 所有 PR 仍然是草稿，存储库的 HUMAN 占位符保持不变。

所有任务拥有的服务器和助手都将停止，并保留经过审查的证据。 原始维护报告的模型成本快照不包括此后续修复工作。
