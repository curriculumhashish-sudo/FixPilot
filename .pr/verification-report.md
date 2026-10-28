<a id="agent-server-verification--2026-10-23"></a>

# Agent Server 验证 — 2026-10-23

结果：**发生变化，有明确的覆盖范围限制**。 这次维护周期对34个功能家族进行了测试，并使用了`control-agent-server`，审查了源代码和中间的PR意图，修正了过时的配方，并报告了在分支中确认的新缺陷四例。 产品修复是单独的 PR，记录在 [ 后续修复报告 ](fix-report.md) 中。 可接受的维护基线保持不变，因为成功 ChatGPT 授权需要人工帐户批准。

<a id="scope-and-provenance"></a>

## 范围和出处

| 项目 | 价值 |
|---|---|
| 存储库接收写入 | 仅 `enyst/agent-sdk` |
| 冻结目标 | `5966c781ed014efc96c028a99bddd4ff78426741` |
| 接受的基线 | `8ba966d1d3af49f08e04349c055009e1614b48d6` (2026-10-07) |
| 上游检查是否有重复/来源 | `60192ed54db73ac658ac1a07462916126c32d3a0` |
| 服务器 | 1.55.1，从孤立的目标/基线启动工作树 |
| 型号 | DeepSeek 闪存和 v4 Pro； 真实的 ACP 适配器请求； 明确标识本地 HTTP 提供商测试夹具 |
| 主持人 | Linux，Python 3.13，tmux，Chromium，节点，Docker； 由 `docker-init -s` 监督的完整 CLI 个生命周期 |
| 证据根源 | `/tmp/agent-server-verify/20261023-*`; `/workspace/scratch/verify-2026-10-23` |

该分叉比检查的上游快照晚了 60 次提交，并且没有仅分叉提交。 结果适用于测试的分叉：未更改的上游来源是支持证据，而不是实时上游验证的主张。 克隆体并不浅。 在整个维护过程中，产品代码始终保持冻结目标。

Docker 主机服务器运行目标源。 它的子图像是 `ghcr.io/openhands/agent-server:1.55.1-python-minimal`、摘要 `sha256:a6ed8b9ab9c7333e1e0ba9c6950636827ee2c8577b0fab1b05cbbd966fdec569`、报告构建 `5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2`。 这证明了宿主/释放子级的组合。 无法在工作区磁盘限制内解压缩完整映像。 浏览器否定检查使用安装了冻结目标源的隔离最小容器； 他们没有修改主机 Chromium。

<a id="newly-confirmed-product-bugs"></a>

## 新确认的产品错误

每个缺陷在新的健康服务器上重现两次，并通过控制来区分故障与设置或传输层问题。 新的已知错误标记保留了正确的预期结果，并且仅与所展示的症状匹配。

| 问题 | 特点 | 预期/观察到 | 区分控制 |
|---|---|---|---|
| [#39](https://github.com/enyst/agent-sdk/issues/39) | `F25.install-documented-sources` | 嵌入式 GitHub 技能子路径安装为 200 / 在存储库根重命名后返回 422 | 显式 `repo_path` 安装、读回和卸载相同的技能 |
| [#40](https://github.com/enyst/agent-sdk/issues/40) | `F20.validate-quota-exhausted` | 结构化 `insufficient_quota` 响应给出 `valid:false` / 给出 `valid:true` | 普通瞬态429仍然有效； 记录准确的 HTTP 响应； 配置文件存储不变 |
| [#41](https://github.com/enyst/agent-sdk/issues/41) | `F21.ts-payload-types` | 导出的配置文件/诊断类型接受实时 `public_skills` / 均拒绝 TS2353 | 生成的 OpenAPI 类型编译相同的实时载荷键集 |
| [#42](https://github.com/enyst/agent-sdk/issues/42) | `F04.child-unborn` | 新鲜的工作区中的默认子级创建返回 201 / 从 `git worktree add ... HEAD` 返回 500 | 共享孩子在真实模型上完成； 已提交存储库工作树和非 Git 回退方案成功 |

使用维护分支的 CLI 和配方图进行重现：

```sh
export PATH="$PWD/.agents/skills/verify-agent-server/scripts:$PATH"
control-agent-server map run --file F25 --only F25.install-documented-sources --fresh --repeat 2 --record --keep-going
control-agent-server map run --file F20 --only F20.validate-quota-exhausted --fresh --repeat 2 --record --keep-going
control-agent-server map run --file F21 --only F21.ts-payload-types --fresh --repeat 2 --record --keep-going
control-agent-server map run --file F04 --only F04.child-unborn --fresh --repeat 2 --record --keep-going
```

在 PID 1 不收割子收割机的主机上，将每个完整命令包装在 `docker-init -s --` （或另一个子收割机）中。 首先构建TypeScript客户端； 真实模型食谱需要配置DeepSeek凭据。 问题主体和审查的证据包包含准确的观察结果和运行 ID。

重复检查涵盖了上游和分叉问题列表、上游伞 #5653、分叉审计 #33 以及现有的配方参考。 关闭上游 #5895 涉及早期解析器拒绝，而 #39 到达安装并失败后续目录名称验证。 关闭了上游 #5100/#4936 关于配额验证/重试行为的闭包；#40 隔离了在真实 HTTP 路径上丢失的结构化错误信息。 较旧的 TypeScript 总括条目涉及其他领域，而不是新引入的 `public_skills`。 未找到匹配的子/未出生存储库报告。

该分叉没有最近关闭的问题。 根据要求的介绍而检查的最近关闭的三份上游报告是#6045、#5963 和#5959。 新问题使用相同的介绍，智能体身份准确更改为 Codex：“我是 AI 智能体 (Codex)，帮助 Engel Nyst (@enyst) 进行项目维护。”

<a id="corrected-recipes-and-harness"></a>

## 更正了配方和安全带

只有在满足 ** 两个基线 xfail 和两个目标 xpass **：`F10.fork-tags-consistent`（fork metadata，upstream #4814）和 `F14.trajectory-init-path`（deferred-init 持久化路径，#5696）之后，才退役了两个已知的 bug 标记。 他们的正确主张仍然活跃。 只有在冻结叉目标保留其标记后才能修复现有缺陷。

其他更改遵循记录的源意图：空凭据标准化； 工具可用性和预载隔离； 子REST/工具集成； 瞬态事件流增量； 活动/默认智能体删除后配置文件修复 (#5983)； 插件清单回退方案 (#5990); 插件获取路由所有权； 真实的 ACP 模型发现和类型化客户端； Docker 生命周期/启动期限； 和 Git 时间戳/提供者响应测试夹具。 完整的系列重播遵循更改后的可执行配方，并针对特定环境的分支进行补充运行。

的 CLI 现在记录并要求健康 `doctor` 每次运行前，结果都会自动启动新的地图运行。 医生正确识别了休眠的延迟初始化状态、其在认证之前准备的行为 WebSocket 握手拒绝，而不是无报告就终止，而是报告失败的认证网络探针。 的 HTTP  LLM  测试夹具接受 `status:CODE:JSON`, 保留显式空值体，因此可以测试结构化的配额响应模拟的 SDK. 该技能解释了容器主机的进程收获。

<a id="intent-and-contract-review"></a>

## 意向和合同审查

基线和目标之间的所有 130 次提交均通过 GitHub 的提交到 PR API 得到解决。 账本记录描述、更改路径、评审讨论、关联验收标准和REST兼容性评论，与运行结果分开。 源波覆盖了所有 34 个家庭，包括 Python 和 TypeScript 消费者。 所有 36 个最初在系列源前缀之外的更改产品路径均与系列或具体的非智能体面向原因进行了协调。

路线比较新增`POST /api/acp/models`、`POST /api/conversations/{conversation_id}/children`、`POST /api/plugins/fetch`； 它被删除或新已弃用 None。 ACP 发现已经拥有所有权； 另外两个现在拥有可执行的覆盖范围和所有者。 成功的家庭检查并不声称对每个细节的每个PR都独立证明：运行时覆盖记录适用功能的结果和能力限制。

最终结构检查通过了 34 个家庭和 948 个条目。 覆盖率报告了206条路线：196条已拥有和驾驶的路线，10条明确排除的生成文档或Docker通配符转发路线，0条未拥有但未驾驶的路线，0条已拥有但未驾驶的路线，无重复拥有者，无过期排除。 转发行为本身就有活生生的Docker证据。

<a id="coverage-limits-and-resolved-prerequisites"></a>

## 覆盖范围限制和已解决的先决条件

唯一被阻止的功能是 `F24.login-complete`成功 ChatGPT 订阅授权需要人工账号审批。 已执行设备启动/轮询/错误/注销路径。 可接受的基线保持不变。 用户明确请求维护 PR 尽管云覆盖限制了范围，所以这个 PR  证明了的纠正措施，但不声称完全无阻的通行。

初始环境限制已解决，而不是算作产品故障：

- Docker 生命周期、启动截止日期、存储保留、磁盘预算清理和同步/异步 SDK 消费者与真实的守护进程运行。 五分钟回收计时器没有缩短，也没有直接调用。
- 浏览器否定检查使用了一个隔离的目标源容器，在标准路径中没有 Chromium； 阳性探针私下提供了其可执行文件。
- 所有三个 OpenVSCode lanes 运行在隔离的目标-源容器中，包括活的进程准备就绪、文件编码以及实际编辑器访问。
- 不可变文件系统配方在一次性容器中传递。 只有它的`chattr`助手收到了`CAP_LINUX_IMMUTABLE`； 实际服务器的运行速度为 UID 1000，没有有效或环境功能。 不可变的标志被清除，容器被删除。
- 初始僵尸进程断言在此主机的非收割 PID 1 下失败。 重放`docker-init -s`下通过原始断言传递的完整CLI生命周期。 根拥有的测试容器证据目录也中断了一次运行列表检查； 有针对性的所有权修复和新的重播解决了这个问题。

`F34.event-stream-reconnect-native` Node 22.22.0 中仍然存在一个已知的 bug。 源代码和构建的客户端在两次测试中都失败了 BASE 和 TARGET 在 Node 22 上运行，并在 Node 24.19.0 的两次版本上通过。 观察者现在选择记录的受影响的运行时； 该标记并未作为产品修复而退役。 历史版本1.22.0版本门测试夹具 pins FastAPI 从该版本的锁文件中，因为今天不受约束 FastAPI 不再导入旧版本。 上传-响应配方现在断言文档中的内容 `file_size` 由#5856添加的。

未声明任何 Agent Canvas 浏览器 UI、PyInstaller 工件、完整 Docker 图像、非 Linux 主机或任意第三方提供商兼容性。 REST、WebSocket、Python、SDK 和 TypeScript 结果保留了单独的证据。 在确认之前，通过自动工具筛选停止了单独的探索性候选者； 它没有被绕过、被视为缺陷或被用来改变期望。

<a id="final-results-and-validation"></a>

## 最终结果和验证

快照：2026-10-23T06:44:47+00:00。 **948条映射条目：864通过，82个已知错误的失败，一个被阻塞，一个被退役；**947个活跃条目都被执行或明确阻塞。 不存在无法解释的故障、未解决的 xpass 或未尝试的条目。 82 个 xfails 计数功能检查，而不是明显的问题，并且包括四个新报告的缺陷。

冻结的地图包含 935 个条目。 此 PR 添加 13 并删除 None。 `F03.auth-before-gate` 仍然是退役库存，而不是运行时通行证。 这些总数选择每个特征最新完成的目标证据并保留单独的分支。 完整的证据表保留了早期的失败、意外的通过、基线尝试和随后的更正； 原始尝试总数不得被误认为是唯一覆盖范围。 仅解析器的试运行不包括在运行时计数中。

| 家庭 | 参赛作品 | 通行证 | 已知故障 | 被阻止 | 退休 |
|---|---:|---:|---:|---:|---:|
| F01 | 11 | 11 | 0 | 0 | 0 |
| F02 | 21 | 20 | 1 | 0 | 0 |
| F03 | 25 | 23 | 1 | 0 | 1 |
| F04 | 36 | 30 | 6 | 0 | 0 |
| F05 | 31 | 28 | 3 | 0 | 0 |
| F06 | 29 | 25 | 4 | 0 | 0 |
| F07 | 24 | 22 | 2 | 0 | 0 |
| F08 | 23 | 20 | 3 | 0 | 0 |
| F09 | 28 | 22 | 6 | 0 | 0 |
| F10 | 25 | 22 | 3 | 0 | 0 |
| F11 | 25 | 24 | 1 | 0 | 0 |
| F12 | 31 | 28 | 3 | 0 | 0 |
| F13 | 29 | 28 | 1 | 0 | 0 |
| F14 | 30 | 27 | 3 | 0 | 0 |
| F15 | 29 | 27 | 2 | 0 | 0 |
| F16 | 26 | 25 | 1 | 0 | 0 |
| F17 | 24 | 24 | 0 | 0 | 0 |
| F18 | 29 | 27 | 2 | 0 | 0 |
| F19 | 28 | 26 | 2 | 0 | 0 |
| F20 | 36 | 32 | 4 | 0 | 0 |
| F21 | 32 | 29 | 3 | 0 | 0 |
| F22 | 24 | 20 | 4 | 0 | 0 |
| F23 | 28 | 24 | 4 | 0 | 0 |
| F24 | 20 | 18 | 1 | 1 | 0 |
| F25 | 33 | 29 | 4 | 0 | 0 |
| F26 | 26 | 24 | 2 | 0 | 0 |
| F27 | 32 | 30 | 2 | 0 | 0 |
| F28 | 29 | 28 | 1 | 0 | 0 |
| F29 | 29 | 28 | 1 | 0 | 0 |
| F30 | 27 | 25 | 2 | 0 | 0 |
| F31 | 23 | 22 | 1 | 0 | 0 |
| F32 | 30 | 27 | 3 | 0 | 0 |
| F33 | 43 | 40 | 3 | 0 | 0 |
| F34 | 32 | 29 | 3 | 0 | 0 |

验证：`make build`/development在BASE和TARGET处的依赖关系； TypeScript `npm ci` 并在两个修订版上进行构建； **69 CLI 次测试通过**（39.74 秒）； **通过了25项独立元数据检查**； 通过了结构/路线覆盖检查和预提交挂钩。 所有维护的食谱更改都有实时证据，或者对于未更改的脚本 F31 集成，还包括成功解析的执行 shell 语句。 本PR中未编辑产品来源。

在成本快照中，在 64 个捕获的运行和 211 个对话中，观察到的 SDK 报告的模型成本为 **$0.189769**。 这是观察到的下限，而不是发票：快照通过运行/对话/模型最大值进行去重，排除了合成测试夹具成本，未捕获验证ping或已删除历史记录可能缺失。 ACP 适配器标签/费率可能与实际 DeepSeek 计费不同。

证据和意图：

- [审核了交换、控制和溯源](evidence/README.md)
- [功能和尝试表](evidence/feature-results.md)
- [提交/PR意图日志](intent-ledger.md)
- [运行时协调](intent-runtime-overlay.md)

公共数据包包含选定的已审核字段和元数据。 完整的原始转录本保留在出处记录的本地运行路径中； 私钥、原始凭据交换和完整服务器日志均不包含在发布范围内。 发布扫描未发现配置的机密值。 所有任务拥有的服务器、助手和容器在证明后都会停止； 证据被保留。
