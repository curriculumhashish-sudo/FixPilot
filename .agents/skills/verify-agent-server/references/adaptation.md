<a id="where-this-workflow-comes-from"></a>

# 这个工作流程来自哪里

这是一个独立编写的改编自 Poteto 的 MIT 许可的 pstack（[backnotprop/pstack](https://github.com/backnotprop/pstack)，一个与线束无关的镜像）
[cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack)) and
[cursor-team-kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit) 控制技能，通过兄弟 `verify-openhands` 技能
[`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands/tree/main/.agents/skills/verify-openhands),
将相同的方法应用于 Agent Canvas UI：

- [创建验证技能](https://github.com/cursor/plugins/blob/main/pstack/skills/create-verification-skill/SKILL.md)：访谈仓库，然后生成启动/医生/驱动/证据/清理和一个功能地图，然后端到端证明一个食谱，最后移交。
- [特征图示例](https://github.com/cursor/plugins/tree/main/pstack/skills/create-verification-skill/references/feature-map-example)每个功能一个文件，包含四个部分，稳定ID，每一步都写在其中 `control-<app>`  CLI 所以这是一个简单的可重跑命令。
- [维护验证技能](https://github.com/cursor/plugins/blob/main/pstack/skills/maintain-verification-skill/SKILL.md): 检查卫生，平行源波，单个串行活波，以及将它们归类为地图漂移，利用空隙和产品缺陷。
- [构建杠杆](https://github.com/cursor/plugins/blob/main/pstack/skills/principle-build-the-lever/SKILL.md)和[控制-CLI](https://github.com/cursor/plugins/blob/main/cursor-team-kit/skills/control-cli/SKILL.md)：构建驱动和证明工作的工具； 每一步一个动作，确定性等待睡眠，清理你开始的事情。
- [贝尼的控制适配器合同和验证现有修复](https://github.com/backnotprop/pstack/tree/main/automations/benny/skills/reproduce-and-fix-issues/references)报告功能和哪些路段可以驾驶或被阻塞，开始之前先确认环境，只有在基线重复两次且修补的构建也重复两次后才确认修复。
- [CLI-for-智能体](https://github.com/cursor/plugins/blob/main/cli-for-agent/skills/cli-for-agents/SKILL.md)：非交互式标志，分层 `--help` 示例、可操作错误、幂等命令、机器可读输出。

<a id="agent-server-decisions"></a>

## 智能体-服务器决策

本产品的“用户”是一个智能体，或承载它的程序，因此被测试的接口是 REST 和 WebSocket  API 而不是屏幕。

- **A CLI 优于原始 HTTP 和 WebSocket，而不是 TypeScript 客户端。** TypeScript 客户端是一个正在测试的消费者：它被固定到已发布的服务器映像，它故意不包装每个路由，并且它将服务器行为（状态代码、错误主体、关闭代码、标头）隐藏在其自身后面。 拉线时，每条路线在着陆当天均可到达。 消费者仍然被覆盖：每个家庭列出 SDK 和 TypeScript 个客户端方法，这些方法到达它，`exec` 运行 SDK 或客户端程序。
- ** 路由表是库存。** `map routes` 导入了 checkout 的 app（在默认配置和 Docker 运行模式下），因此它看到 WebSockets，只配置的路由和 OpenAPI 忽略的路由。 每个家庭在`Routes:`行上声明其拥有的路线； `map coverage` 失败，直到每条路线都只有一个所有者，`map check` 失败，当配方或
  `Routes:` 行命名了应用程序不再提供服务的路线。
- **食谱是被解析的，而不仅仅是阅读。** `map check` 运行时间
  映射中的 `control-agent-server ...` 命令通过实参解析器，因此重命名的动词或标志而不是下一个智能体会破坏检查。
- **维护从合同开始。**每周通行证区分 BASE 和 TARGET 之间的路由表，并将更改的文件路由到家庭
  `map owners`，然后依赖现有的 oasdiff 破损检查来进行模式更改，而不是重新派生它。
- **每周一次之间的每日通行证。**程序在
  [daily.md](daily.md) follows `verify-openhands`' daily pass: it drives only
  自记录的基线以来，这些家庭发生了变化，并在没有任何合并时提前停止。 `map baseline` 在运行之间保持状态自由。
- **通过配置隔离。**每次运行都有一个私人`HOME`，
  `OH_PERSISTENCE_DIR`，配置文件，工作区会话路径，工作树根目录，tmux 目录，会话密钥，机密密钥和端口，以及继承调用者`OH_*` 或LLM 变量的None，因此运行时从不接触开发人员
  `~/.openhands` 或另一个智能体运行。
- **没有模拟对象。**重启(持久化和恢复)，密钥轮换，延迟初始化，未认证模式，配置更改和录制Webhook汇流点是CLI动词，因此实际服务器上的食谱可以到达这些状态。
- **基于模型的食谱使用 DeepSeek V4.1 Flash** 从环境密钥验证后，保存之前，再从服务器的预飞行验证，所以是一个 CI  智能体可以不用输入就运行它们机密 into argv or logs。
- 未导入：浏览器守护进程、UI技能的截图和视口检查（这里没有UI），鼠标插件配置，模型路由
  `disable-model-invocation`，以及自主航运或合并机构。

这些是 `.agents/skills`（[AgentSkills 格式 ](https://docs.openhands.dev/sdk/guides/skill)）下此存储库的贡献者工作流程。 它们补充了中描述的单元、实时服务器、压力和契约测试
[SKILL.md](../SKILL.md#how-this-fits-with-the-tests), and do not replace them.
