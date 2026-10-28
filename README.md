
 FixPilot智能体 SDK 提供 Python、TypeScript 和 REST API，用于**构建能够处理代码的智能体**。

你可以使用  FixPilot智能体 SDK 完成：
* 一次性任务，例如为仓库编写 README
* 日常维护任务，例如更新依赖
* 涉及多个智能体的大型任务，例如重构和重写

智能体既可以将本机用作工作区，也可以通过 Agent Server 在临时工作区中运行 （例如 Docker 或 Kubernetes 环境）。

你还可以使用 SDK 构建新的开发工具：
[OpenHands CLI](https://github.com/OpenHands/OpenHands-CLI) 和 [OpenHands Cloud](https://github.com/OpenHands/OpenHands) 都由它驱动。

可以从[示例](https://docs.openhands.dev/sdk/guides/hello-world)入手，或[阅读文档](https://docs.openhands.dev/sdk)了解更多信息。

<a id="quick-start"></a>

## 快速开始

下面展示了如何使用 SDK 构建智能体：

```python
import os

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


llm = LLM(
    model="gpt-5.5",
    api_key=os.getenv("LLM_API_KEY"),
)

agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ],
)

cwd = os.getcwd()
conversation = Conversation(agent=agent, workspace=cwd)

conversation.send_message("Write 3 facts about the current project into FACTS.txt.")
conversation.run()
print("All done!")
```

安装说明和详细配置请参阅[入门指南](https://docs.openhands.dev/sdk/getting-started)。 在本仓库中进行本地开发时，运行 `make build` 安装工作区依赖和 pre-commit 钩子。

<a id="repository-boundaries"></a>

## 仓库职责边界

本仓库维护 Python SDK 和 Agent Server 的标准实现，以及兼容浏览器的 [TypeScript 客户端](clients/typescript/)。其职责涵盖智能体、工具、对话、工作区、事件、REST/WebSocket API，以及访问该 API 的类型化客户端。[`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) 中的 Agent Canvas 使用此 TypeScript 客户端；[`OpenHands/automation`](https://github.com/OpenHands/automation) 则负责调度、Webhook、运行历史和任务分发。SDK/Agent Server 执行自动化系统分发的对话。

通常的调用链为 SDK/Agent Server → OpenAPI 契约 → `clients/typescript` → Agent Canvas。后端行为和接口端点由 Python SDK 或 Agent Server 包负责；兼容浏览器的客户端访问由 `clients/typescript` 负责；界面由 Agent Canvas 负责；自动化生命周期由 `automation` 负责。

<a id="documentation"></a>

## 文档

详细文档、教程和 API 参考请访问：

**[ https://docs.openhands.dev/sdk ](https://docs.openhands.dev/sdk)**

文档内容包括：
- [入门指南](https://docs.openhands.dev/sdk/getting-started) — 安装与配置
- [架构与核心概念](https://docs.openhands.dev/sdk/arch/overview) — 智能体、工具、工作区等
- [使用指南](https://docs.openhands.dev/sdk/guides/hello-world) — Hello World、自定义工具、MCP、技能等
- [Agent Server API 参考](https://docs.openhands.dev/sdk/guides/agent-server/api-reference/server-details/alive) — 远程智能体服务器的 REST API 参考

<a id="examples"></a>

## 示例

`examples/` 目录包含完整的用法示例：

- **独立 SDK**（`examples/01_standalone_sdk/`）— 智能体基础用法、自定义工具和核心工作流
- **远程 Agent Server**（`examples/02_remote_agent_server/`）— 客户端与服务器架构及 WebSocket 连接
- **GitHub 工作流**（`examples/03_github_workflows/`）— CI/CD 集成与自动化工作流
- **技能与插件**（`examples/05_skills_and_plugins/`）— AgentSkills、插件和市场示例

<a id="skills-for-modern-package-tooling"></a>

## 现代包管理工具的技能

通过 `AgentContext(load_public_skills=True)` 启用公共技能后，默认的
`OpenHands/extensions` 市场可提供 `uv`、`deno` 等技能。 对于包含 `uv.lock`、`deno.json`、`deno.jsonc` 或 `deno.lock` 等标识文件的仓库， 智能体可以自动获取对应的最新包管理指导。

启用公共技能加载的最小示例见
`examples/01_standalone_sdk/03_activate_skill.py`。

<a id="contributing"></a>

## 参与贡献

开发环境配置、测试和贡献指南见 [DEVELOPMENT.md](DEVELOPMENT.md)。

<a id="community"></a>

## 社区

- [加入 Slack](https://openhands.dev/joinslack) — 与 OpenHands 社区交流
- [GitHub 仓库](https://github.com/OpenHands/software-agent-sdk) — 源代码与问题反馈
- [文档](https://docs.openhands.dev/sdk) — 完整文档

<a id="cite"></a>

## 引用

```
@misc{wang2025openhandssoftwareagentsdk,
      title={The OpenHands Software Agent SDK: A Composable and Extensible Foundation for Production Agents}, 
      author={Xingyao Wang and Simon Rosenberg and Juan Michelini and Calvin Smith and Hoang Tran and Engel Nyst and Rohit Malhotra and Xuhui Zhou and Valerie Chen and Robert Brennan and Graham Neubig},
      year={2025},
      eprint={2511.03690},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2511.03690}, 
}
```
<hr>

<a id="thank-you-to-our-contributors"></a>

### 感谢所有贡献者

[![贡献者](https://assets.openhands.dev/readme/openhands-software-agent-sdk-contributors.svg)](https://github.com/OpenHands/software-agent-sdk/graphs/contributors)

<hr>

<a id="trusted-by-engineers-at"></a>

### 以下企业的工程师正在使用

<div align="center"> <br/><br/> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/tiktok.svg"> <img src="https://assets.openhands.dev/logos/external/black/tiktok.svg" alt="TikTok" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/vmware.svg"> <img src="https://assets.openhands.dev/logos/external/black/vmware.svg" alt="VMware" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/roche.svg"> <img src="https://assets.openhands.dev/logos/external/black/roche.svg" alt="Roche" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/amazon.svg"> <img src="https://assets.openhands.dev/logos/external/black/amazon.svg" alt="Amazon" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/c3-ai.svg"> <img src="https://assets.openhands.dev/logos/external/black/c3-ai.svg" alt="C3 AI" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/netflix.svg"> <img src="https://assets.openhands.dev/logos/external/black/netflix.svg" alt="Netflix" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/mastercard.svg"> <img src="https://assets.openhands.dev/logos/external/black/mastercard.svg" alt="Mastercard" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/red-hat.svg"> <img src="https://assets.openhands.dev/logos/external/black/red-hat.svg" alt="Red Hat" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/mongodb.svg"> <img src="https://assets.openhands.dev/logos/external/black/mongodb.svg" alt="MongoDB" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/apple.svg"> <img src="https://assets.openhands.dev/logos/external/black/apple.svg" alt="Apple" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/nvidia.svg"> <img src="https://assets.openhands.dev/logos/external/black/nvidia.svg" alt="NVIDIA" height="17" hspace="5">
</picture> <picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://assets.openhands.dev/logos/external/white/google.svg"> <img src="https://assets.openhands.dev/logos/external/black/google.svg" alt="Google" height="17" hspace="5">
</picture> </div>
