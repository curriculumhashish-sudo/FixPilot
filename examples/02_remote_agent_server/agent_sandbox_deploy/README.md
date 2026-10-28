<a id="running-the-agent-server-in-agent-sandbox-on-a-local-kind-cluster"></a>

# 在本地类型集群上运行智能体-沙箱中的 Agent Server

端到端演练
[`17_convo_with_agent_sandbox_server.py`](../17_convo_with_agent_sandbox_server.py)
使用[种类](https://kind.sigs.k8s.io/)。 相同的步骤适用于 minikube 或云集群，例如 GKE。 仅集群创建步骤不同。

<a id="1-create-a-cluster"></a>

## 1. 创建集群

```bash
kind create cluster --name openhands
```

<a id="2-install-the-agent-sandbox-controller--extensions"></a>

## 2. 安装智能体-沙箱控制器+扩展

从 <https://github.com/kubernetes-sigs/agent-sandbox/releases> 中选择一个版本并应用核心 + 扩展清单：

```bash
export VERSION="vX.Y.Z"
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/manifest.yaml
kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/extensions.yaml
```

等待控制器准备就绪：

```bash
kubectl -n agent-sandbox-system rollout status deploy --timeout=120s
```

<a id="3-apply-the-agent-server-template--warm-pool"></a>

## 3. 应用智能体-服务器模板+暖池

```bash
kubectl apply -f sandboxtemplate.yaml
kubectl apply -f sandboxwarmpool.yaml
```

第一次拉取 `ghcr.io/openhands/agent-server` 可能需要一分钟。 观察池填满（一旦 Agent Server 通过其 `/health` 探针，pod 就会变为 `Ready`）：

```bash
kubectl get pods -w
```

<a id="4-install-the-client-and-run-the-example"></a>

## 4. 安装客户端并运行示例

```bash
pip install openhands-workspace[agent-sandbox]

export LLM_API_KEY=...            # 你的 LLM 键（从 Pod 内部调用）
export LLM_MODEL=...              # 可选，e.g。 托管模型 ID
python ../17_convo_with_agent_sandbox_server.py
```

你应该看到：从热池的秒级请求，pod中的命令运行， 智能体编辑文件，然后是一个 **暂停** (pod suspended, PVC 保留下来的 **resume** (同样的对话继续进行中)

<a id="notes"></a>

## 注释

- **LLM 出口。** 智能体在 pod * 内的 Agent Server * 上运行，因此从 pod 中调用 LLM API。 kind 默认允许出站互联网。 要使用本地 Ollama，请将 `LLM_BASE_URL` 指向可从 pod 访问的地址，并（实际上）确保容器网络可以访问您的主机。
- **冷启动与热池。**使用 `replicas: 0`，池变得按需，并且每个声明都会创建一个新的 Pod（完全冷启动）。 增加 `replicas` 以使吊舱保持就绪状态。
- **隔离性强。**取消注释 `sandboxtemplate.yaml` 中的 `runtimeClassName: gvisor`（需要启用 gVisor 的节点池）以在内核边界沙箱不受信任的智能体代码。
- **清理。** `kind delete cluster --name openhands`。
