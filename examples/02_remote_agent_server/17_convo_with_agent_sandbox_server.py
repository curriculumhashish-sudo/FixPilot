"""运行 Agent Server 位于 Kubernetes-sigs/agent-sandbox pod 中的对话。

先决条件（有关完整的演练，请参阅 agent_sandbox_deploy/README.md）：
  1. 安装了智能体-sandbox 控制器和扩展的 Kubernetes 集群（kind / minikube / GKE），可
  通过 kubeconfig 访问。
  2. 应用了智能体-server SandboxTemplate + SandboxWarmPool： kubectl apply -f
  agent_sandbox_deploy/sandboxtemplate.yaml kubectl apply -f agent_sandbox_deploy/
  sandboxwarmpool.yaml
  3. 使用 pip 安装 OpenHands-工作区 [ 智能体-sandbox ]
  4. 导出 LLM_API_KEY=...（以及可选的 LLM_MODEL、LLM_BASE_URL）

LLM 是从 Pod 内部调用的（智能体在 Agent Server 上运行），因此集群需要到 LLM 端点的出
口。
"""

import os
import time

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Conversation,
    RemoteConversation,
    get_logger,
)
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import AgentSandboxWorkspace


logger = get_logger(__name__)

# 1) LLM 配置
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)

# 2) 从温水池中领取一个吊舱。 如果使用预热池，则可在不到一秒的时间内返回； 工作区通过
# kubectl port-forward 连接到 pod 的 Agent Server（默认的“port_forward”连接模式）。
#
warmpool = os.getenv("AGENT_SANDBOX_WARMPOOL", "openhands-pool")
namespace = os.getenv("AGENT_SANDBOX_NAMESPACE", "default")
logger.info(f"Claiming a sandbox from warm pool {warmpool!r} in {namespace!r}...")
with AgentSandboxWorkspace(
    warmpool=warmpool,
    namespace=namespace,
    # 安全网：如果有内容泄露，30 分钟后自动删除该声明。
    shutdown_after_seconds=30 * 60,
) as workspace:
    # 3) 创建智能体
    agent = get_default_agent(llm=llm, cli_mode=True)

    # 4) 使用直接命令对工作区进行健全性检查
    result = workspace.execute_command("echo 'Hello from agent-sandbox!' && pwd")
    logger.info(f"Command exit code: {result.exit_code}")
    logger.info(f"Output: {result.stdout}")

    # 5) 进行对话
    conversation = Conversation(agent=agent, workspace=workspace)
    assert isinstance(conversation, RemoteConversation)
    try:
        logger.info(f"Conversation ID: {conversation.state.id}")
        conversation.send_message(
            "Read the current repo and write 3 facts about the project into FACTS.txt."
        )
        conversation.run()
        logger.info(f"Agent status: {conversation.state.execution_status}")

        # 6) 演示本机暂停/恢复。 该 Pod 被挂起（operatingMode -> 挂起），其 PVC 被保留，
        # 然后恢复以进行后续操作。
        #
        logger.info("Pausing the sandbox (operatingMode -> Suspended)...")
        workspace.pause()
        time.sleep(3)
        logger.info("Resuming the sandbox (operatingMode -> Running)...")
        workspace.resume()

        conversation.send_message("Great! Now append a 4th fact to FACTS.txt.")
        conversation.run()
        logger.info("Second task completed after resume.")

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")
    finally:
        print("\nCleaning up conversation...")
        conversation.close()
