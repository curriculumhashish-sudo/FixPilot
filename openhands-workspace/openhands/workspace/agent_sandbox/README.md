# AgentSandboxWorkspace

在由以下人员管理的 Kubernetes Pod 内运行 OpenHands Agent Server
[`kubernetes-sigs/agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox).

Pod 是从 `SandboxWarmPool` 声明的，因此预热池可以在亚秒级启动，而不是为每个会话支付容器冷启动费用。 它添加了本机暂停/恢复（通过沙箱 `operatingMode`），并通过持久卷添加了在暂停后仍可存活的工作区状态。 gVisor / Kata 隔离可通过在 `SandboxTemplate` 上设置 `runtimeClass` 来实现。

它是一个插入式 `RemoteWorkspace`，因此它可以在 `DockerWorkspace` 所做的任何地方工作，
from a laptop kind or minikube cluster to a cloud cluster such as GKE.

<a id="install"></a>

## 安装

```bash
pip install openhands-workspace[agent-sandbox]
```

这会拉入用于创建和管理沙箱的 [`k8s-agent-sandbox`](https://pypi.org/project/k8s-agent-sandbox/) 客户端。

<a id="prerequisites"></a>

## 先决条件

1. 可通过 kubeconfig 访问 Kubernetes 集群，并安装智能体-沙箱控制器 + 扩展（[安装指南](https://github.com/kubernetes-sigs/agent-sandbox#installation)）。
2. 运行 Agent Server 的 `SandboxTemplate` 和引用它的 `SandboxWarmPool`。 准备应用的清单位于 [`deploy/`](deploy/) 中：

   ```bash
   kubectl apply -f deploy/sandboxtemplate.yaml
   kubectl apply -f deploy/sandboxwarmpool.yaml
   ```

<a id="usage"></a>

## 用途

```python
from openhands.sdk import Conversation
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import AgentSandboxWorkspace

with AgentSandboxWorkspace(warmpool="openhands-pool", namespace="default") as workspace:
    result = workspace.execute_command("echo hello && pwd")
    print(result.stdout)

    conversation = Conversation(agent=get_default_agent(llm=llm), workspace=workspace)
    conversation.send_message("Write 3 facts about this repo into FACTS.txt.")
    conversation.run()
```

<a id="connection-modes"></a>

### 连接方式

* `connection="port_forward"`（默认）将 `kubectl port-forward` 生成到 pod。 这可以在笔记本电脑上针对本地类型或 minikube 以及您的 kubeconfig 可以访问的任何集群进行工作。 `host_port`为您选择一个免费的本地端口。
* `connection="direct"` 表示您自己提供 `host`：`sandbox-router` 或网关 URL，或者当 OpenHands 在集群中运行时提供集群内 DNS 名称。 没有启动端口转发。

<a id="testing"></a>

### 测试

请参阅 [`TESTING.md`](TESTING.md) 了解端到端演练：单元测试、无密钥工作区烟雾测试以及针对本地 Ollama 模型的完整智能体运行（无 API 密钥）。

<a id="pause--resume"></a>

### 暂停/恢复

```python
workspace.pause()    # operatingMode -> 暂停； Pod 终止，PVC 保留
workspace.resume()   # operatingMode -> 运行； 重新连接到 Agent Server
```

<a id="where-configuration-lives"></a>

### 配置所在的位置

大多数旋钮属于 Kubernetes，而不是 Python 构造函数：

- CPU、内存、图像、`runtimeClass` 和安全性上下文属于
  `SandboxTemplate.spec.podTemplate`.
- 预热和池大小属于`SandboxWarmPool.spec.replicas`。
- 网络出口允许列表属于模板的 `NetworkPolicy`。
- 持久卷属于模板的 `volumeClaimTemplates`。

Python侧旋钮：`warmpool`（必需）、`namespace`、`server_port`、`connection`、
`host_port`, `kube_context`, `sandbox_ready_timeout`, `health_check_timeout`,
`shutdown_after_seconds`, `labels`, `pod_labels`, `pod_annotations`.
