"""具有本地 Ollama 模型的 AgentSandboxWorkspace 的完整智能体 e2e（无 API 键）。

在智能体沙箱 pod 内运行 OpenHands 智能体，由本地 Ollama 模型驱动，并让它使用 bash 命
令创建一个文件。

有两个因素可以让这个功能在小型本地模型中可靠地工作：
  * 发出结构化工具调用的模型。 qwen2.5:7b 和 llama3.1:8b 执行； qwen2.5-coder 和：3b
  变体以纯文本形式返回工具调用，智能体无法
  对其进行操作；
  * 一个最小的、仅限终端的智能体。 默认的多功能工具智能体压倒了这种规模的模型，它们计
  划、思考和完成而不执行。

Prerequisites (see TESTING.md): 具有智能体-沙箱控制器和
暖池、*沙箱 pod* 可以到达的 Ollama 端点（集群内服务或任何可到达的主机），以及：

    pip install openhands-workspace[agent-sandbox]

环境：
    OLLAMA_URL 必需，e.g。 HTTP://<ollama-clusterip>:11434 OLLAMA_MODEL 默认值：qwen2
    .5
    AGENT_SANDBOX_WARMPOOL 默认值：OpenHands-pool AGENT_SANDBOX_NAMESPACE 默认值：默
    认值
"""

import os

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.tool import Tool
from openhands.tools.preset.default import register_default_tools
from openhands.tools.terminal import TerminalTool
from openhands.workspace import AgentSandboxWorkspace


WARMPOOL = os.environ.get("AGENT_SANDBOX_WARMPOOL", "openhands-pool")
NAMESPACE = os.environ.get("AGENT_SANDBOX_NAMESPACE", "default")


def main() -> None:
    llm = LLM(
        usage_id="agent",
        model="ollama_chat/" + os.environ.get("OLLAMA_MODEL", "qwen2.5"),
        base_url=os.environ["OLLAMA_URL"],
        api_key=SecretStr("ollama"),  # 被奥拉玛忽视
        reasoning_effort="none",  # qwen2.5没有“思考”模式
        num_retries=8,
        timeout=900,  # CPU 上的小模型每回合可能会很慢
    )
    register_default_tools(enable_browser=False)

    with AgentSandboxWorkspace(warmpool=WARMPOOL, namespace=NAMESPACE) as ws:
        print("connected:", ws.host)
        agent = Agent(
            llm=llm,
            tools=[Tool(name=TerminalTool.name)],
            system_prompt_kwargs={"cli_mode": True},
        )
        conv = Conversation(agent=agent, workspace=ws)
        conv.send_message(
            "Run this exact bash command: echo 'hi from the agent' > hello.txt"
        )
        conv.run()
        print("agent status:", conv.state.execution_status)

        out = ws.execute_command("cat /workspace/hello.txt")
        print(f"hello.txt (exit={out.exit_code}): {out.stdout!r}")
        assert out.exit_code == 0 and "hi from the agent" in out.stdout, out

    print("AGENT E2E PASSED")


if __name__ == "__main__":
    main()
