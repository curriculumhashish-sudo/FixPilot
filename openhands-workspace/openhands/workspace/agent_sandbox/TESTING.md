<a id="testing-agentsandboxworkspace"></a>

# 测试 `AgentSandboxWorkspace`

三层，从根本没有集群到完整的智能体运行。 它们中的每一个都在本地运行，无需 API 键。 这些步骤是集群无关的，因此它们可以在任何你的 `kubectl` 可以到达的集群上运行。

1. **单元测试**，不需要簇。
2. **无钥匙工作区冒烟测试**，需要真实的集群，但不需要LLM。 它本身证明了集成：声明、执行、暂停/恢复和持久化。
3. **完整智能体 e2e**，需要一个真实的集群加上本地 Ollama 模型（无密钥）或托管 LLM 密钥。

<a id="prerequisites"></a>

## 先决条件

- 可通过 kubeconfig 访问的 Kubernetes 集群（kind/minikube/cloud），其中
  [agent-sandbox controller + extensions](https://github.com/kubernetes-sigs/agent-sandbox#installation)
  安装。
- `kubectl`，对于本地 Ollama 运行，[`ollama`](https://ollama.com)（或使用下面的集群内 Ollama 清单）。
- 该软件包及其可选客户端：

  ```bash
  pip install openhands-workspace[agent-sandbox]
  ```

<a id="1-unit-tests-no-cluster"></a>

## 1. 单元测试（无簇）

```bash
uv run pytest tests/workspace/test_agent_sandbox_workspace.py -v
```

这些模拟对象 `k8s-agent-sandbox` 客户端，因此不需要集群或凭据。

<a id="2-cluster-setup-shared-by-tiers-2-and-3"></a>

## 2. 集群设置（由第2层和第3层共享）

安装控制器（从 <https://github.com/kubernetes-sigs/agent-sandbox/releases> 中选择一个版本）：

```bash
export VERSION="v0.5.2"
kubectl apply -f "https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${VERSION}/sandbox-with-extensions.yaml"
kubectl -n agent-sandbox-system rollout status deploy --timeout=180s
```

应用智能体-服务器 `SandboxTemplate` 和 `SandboxWarmPool`（来自
[`../deploy/`](../deploy/)):

```bash
kubectl apply -f ../deploy/sandboxtemplate.yaml
kubectl apply -f ../deploy/sandboxwarmpool.yaml
kubectl get pods -w    # 等待温池 Pod 就绪
```

第一次拉取 `ghcr.io/openhands/agent-server` 可能需要一分钟。 在 kind 上，您可以预加载它以避免集群内拉取：

```bash
docker pull ghcr.io/openhands/agent-server:1.42.1-python
kind load docker-image ghcr.io/openhands/agent-server:1.42.1-python --name <cluster>
```

<a id="3-keyless-workspace-smoke-test-no-llm"></a>

## 3. 无钥匙工作区烟雾测试（无 LLM）

这验证了没有 LLM 的整个集成，并且它与
**安全默认模板**因为没有任何东西离开容器，所以没有网络
需要改变政策。

```bash
python testing/smoke_test.py
```

预期：来自热池的亚秒声明，在 pod 中运行的命令，然后
`pause()` / `resume()` 其中暂停之前写入的文件在（持久卷状态在暂停后仍然存在）和干净的拆卸之后仍然存在。

<a id="4-full-agent-e2e"></a>

## 4. 完整智能体 e2e

OpenHands 智能体在沙盒 Pod 内运行 ** 并从那里调用 LLM，因此
**沙盒 Pod 必须能够到达 LLM**：

- **托管 LLM（公共 API）：** 安全默认模板已允许公共出口，因此无需更改。
- **本地/集群内LLM：**默认模板的`NetworkPolicy`阻止私有范围（集群和主机IP）。 对于测试，放松一下：

  ```bash
  kubectl patch sandboxtemplate openhands-agent-server --type merge \
    -p '{"spec":{"networkPolicyManagement":"Unmanaged"}}'
  # 重新创建池，以便新的 pod 接受更改：
  kubectl patch sandboxwarmpool openhands-pool --type merge -p '{"spec":{"replicas":0}}'
  kubectl patch sandboxwarmpool openhands-pool --type merge -p '{"spec":{"replicas":1}}'
  ```

  `Unmanaged` 完全放弃了该策略，这对于一次性测试集群来说很好，但不适合实际使用。 对于本地测试之外的任何内容，请保留策略 ** 托管 **，并仅允许智能体需要的内容。 请参阅中注释的 `networkPolicy` 块
  [`deploy/sandboxtemplate.yaml`](deploy/sandboxtemplate.yaml) for a copy-pasteable
  范围出口规则（DNS + 你的 LLM 端点）。

<a id="4a-no-key-using-local-ollama"></a>

### 4a. 没有钥匙，使用当地的 Ollama

部署集群内 Ollama 并拉取支持工具的模型：

```bash
kubectl apply -f testing/ollama.yaml
kubectl rollout status deploy/ollama --timeout=180s
kubectl exec deploy/ollama -- ollama pull qwen2.5
```

> **模型选择很重要。**使用返回 * 结构化 * 工具调用的模型：
> `qwen2.5` (7b) 和 `llama3.1:8b` 有效。 `qwen2.5-coder` 和 `:3b` 变体
> 将工具调用作为纯 **text** 返回，因此智能体永远不会起作用。 快速检查：
>
> ```bash
> 卷曲 -s HTTP://<ollama>:11434/api/chat -d '{"model":"qwen2.5","stream":False,
>   "messages":[{"role":"user","content":"调用 run_bash 生成 hello.txt"}],
>   "工具":[{"类型":"功能","功能":{"名称":"run_bash","参数":
>   ]}' | python3 -c ''
>   '导入 sys,JSON;print("tool_calls:",json.load(sys.stdin)["消息"].get("tool_calls"))'
> ```
>
> 非 `null` `tool_calls` 表示该模型可用。

运行它，指向 Ollama 服务：

```bash
export OLLAMA_URL="http://$(kubectl get svc ollama -o jsonpath='{.spec.clusterIP}'):11434"
python testing/agent_ollama_example.py
```

示例中包含的注释：
- `reasoning_effort="none"`，因为qwen2.5没有“思考”模式，否则请求会被`does not support thinking`拒绝。
- **一个智能体仅限终端的**，因为默认的多工具智能体会压倒这个大小的模型：它们计划、思考和完成，但从未执行。
- CPU 上的小模型速度较慢（每转最多几分钟）； 这个例子设定了一个慷慨的超时。

<a id="4b-with-a-hosted-key"></a>

### 4b. 使用托管密钥

任何 `RemoteWorkspace` 风格的用法都有效； 构建工作区并将其交给
`Conversation`:

```python
from pydantic import SecretStr
from openhands.sdk import LLM, Conversation
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import AgentSandboxWorkspace

llm = LLM(usage_id="agent", model="<model>", api_key=SecretStr("<key>"))
with AgentSandboxWorkspace(warmpool="openhands-pool") as ws:
    conv = Conversation(agent=get_default_agent(llm=llm), workspace=ws)
    conv.send_message("Write 3 facts about this repo into FACTS.txt.")
    conv.run()
```

一个有能力的托管模型可以驱动完全默认智能体； 这就是 4b 使用的原因
`get_default_agent` 而 4a 使用最小的智能体。

<a id="what-success-looks-like"></a>

## 成功是什么样的

- 测试运行时会出现 `SandboxClaim`、`Sandbox` 和 pod：

  ```bash
  kubectl get sandboxclaim,sandbox,pods
  ```

- 冒烟测试：标记文件仍然存在 `pause()`/`resume()`.
- 智能体 e2e：智能体发出 `terminal` 动作，`/workspace/hello.txt` 最终得到预期的内容。
- 退出时，工作区会自动删除 `SandboxClaim`（及其 pod）。

<a id="cleanup"></a>

## 清理

```bash
kubectl delete -f testing/ollama.yaml --ignore-not-found
kubectl delete -f ../deploy/sandboxwarmpool.yaml -f ../deploy/sandboxtemplate.yaml --ignore-not-found
# kind: kind 删除集群 --name <cluster>
```

<a id="troubleshooting"></a>

## 故障排除

| 症状 | 原因/修复 |
|---|---|
| 智能体已连接，但LLM呼叫超时； 奥拉马什么也没收到 | 沙盒 Pod 无法到达 LLM。 默认 `NetworkPolicy` 阻止专用范围（集群 ClusterIPs、主机 IP）。 添加范围出口规则（请参阅 `deploy/sandboxtemplate.yaml` 中的注释块），或添加 `networkPolicyManagement: Unmanaged` 以获取一次性测试集群。 公共/托管 APIs 已被允许。 |
| 智能体回复文本和`finish`，但不执行任何操作（无`ActionEvent`） | 该模型以文本形式返回工具调用。 使用 `qwen2.5` (7b) 或 `llama3.1:8b`； 避免`qwen2.5-coder`和`:3b`。 使用上面的原始 `/api/chat` 探针进行验证。 |
| `litellm ... "<model>" does not support thinking` | 在`LLM`上设置`reasoning_effort="none"`（qwen2.5没有思维模式）。 |
| 智能体计划/思考/完成但从未运行命令 | 默认的 7 工具智能体对于小型模型来说太重。 使用最小的仅终端智能体（如 `agent_ollama_example.py` 中），或更大/托管模型。 |
| `model '<name>' not found` 编辑 Ollama 部署后 | 模型商店是`emptyDir`； 编辑 Deployment 会重新启动 pod 并擦除它。 再次`kubectl exec deploy/ollama -- ollama pull <model>`（或使用PVC）。 |
| `resume()` 失败并出现端口或“网络命名空间已关闭”错误 | 恢复后出现短暂的流失； 工作区重试带有新鲜的当地港口。 如果您看到它持久化，请加注 `health_check_timeout`。 |
| 索赔永远不会变成就绪状态 | 第一个智能体-服务器镜像拉取速度慢； 预加载它（参见步骤 2）或升高 `sandbox_ready_timeout`。 |
| `AgentSandboxWorkspace requires the 'agent-sandbox' extra` | `pip install openhands-workspace[agent-sandbox]`. |
