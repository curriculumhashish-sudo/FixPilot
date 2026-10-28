<a id="openhands-agent-server"></a>

# OpenHands-智能体-服务器

请参阅 [ 项目根 AGENTS.md](../AGENTS.md) 了解存储库范围的策略和工作流程。

<a id="development"></a>

## 发展

该包位于单体仓库根目录中。 典型命令（从存储库根目录运行）：

- Install deps: `make build`
- 运行智能体-服务器测试：`uv run pytest tests/agent_server`

<a id="pyinstaller-data-files"></a>

## PyInstaller 数据文件

添加运行时加载的非Python文件（JS、模板等）时，使用`collect_data_files`将它们添加到`openhands-agent-server/openhands/agent_server/agent-server.spec`。


<a id="stress--scale-tests"></a>

## 压力/规模测试

`tests/agent_server/stress/` 是一个在进程内运行的负载测试套件，用于测试智能体- 实时规模下的服务器失败模式子智能体许多对话，长时间运行的 bash，慢 Webhook, WebSocket  背压，etc.

<a id="running-stress-tests"></a>

### 正在运行压力测试

该套件通过 `pyproject.toml` 中的 `addopts = -m 'not stress and not acp_live and not docker_live'` 从默认集合 ** 中 ** 排除。 使用 `-m stress` 覆盖过滤器：

```bash
# 运行完整的压力套件（在开发人员笔记本电脑上约 3-5 分钟）
uv run pytest -m stress

# 运行单个压力测试文件
uv run pytest -m stress tests/agent_server/stress/test_conversation_listing.py

# 验证默认情况下取消选择压力测试
uv run pytest --collect-only -q  # 压力测试显示为“已取消选择”
```

**注意：** 裸露的 `pytest tests/agent_server/stress/` 将收集然后取消选择
因为 `addopts` 过滤器仍然适用 - 始终在路径旁边传递 `-m stress` 以进行路径范围的运行。

<a id="how-the-test-infrastructure-works"></a>

### 测试基础设施如何运作

测试针对智能体-服务器 FastAPI 应用程序运行 **in-process** — 没有真正的二进制文件，没有真正的网络，没有真正的 LLM。 关键测试夹具（在`conftest.py`中）是：

| 测试夹具 | 目的 |
|---|---|
| `conversation_service` | 实数 `ConversationService` 指向 `tmp_path/persist` |
| `bash_service` | 每次测试 `BashEventService`，monkeypatched 到 bash 路由器 |
| `app` | FastAPI 应用程序通过依赖覆盖连接到测试服务 |
| `client` | `httpx.AsyncClient` 超过 `ASGITransport`（共享测试事件循环） |
| `probe` | `ResourceProbe` — psutil 支持的后台采样器，用于 RSS、FD、线程、CPU |

**为什么 TestLLM 需要解决方法：** `StartConversationRequest` 往返
通过 JSON（`model_dump` → 重新验证），这会剥离 `TestLLM` 的私有
`_scripted_responses`. 测试使用 `placeholder_llm()` 作为请求，然后调用
`conversation.switch_llm(real_test_llm)` 创建后。 这个图案是在
`scripts.start_conversation_with_test_llm()`.

<a id="layout"></a>

### 布局

| 文件 | 角色 |
|---|---|
| `__init__.py` | 套件文档字符串和顶级文档 |
| `conftest.py` | 共享测试夹具（服务、应用程序、客户端、探针） |
| `budgets.py` | 具有断言阈值的冻结数据类（延迟、RSS、FD、事件计数） |
| `probe.py` | `ResourceProbe` — 用于预算断言的 psutil 后台采样器 |
| `scripts.py` | `SlowTestLLM`, `placeholder_llm()`, `start_conversation_with_test_llm()`, `wait_for_terminal()` |
| `test_*.py` | 每种故障模式一个文件 |

<a id="adding-a-new-stress-test"></a>

### 添加新的压力测试

1. **创建 `test_<failure_mode>.py`** — 每个 bug 类一个文件。 从模块文档字符串开始，命名捕获的 bug 类和任何警告。
2. **在模块级别添加`pytestmark = pytest.mark.stress`**，以便默认情况下取消选择测试。
3. **将`budgets.py`中的预算**定义为冻结`@dataclass(frozen=True, slots=True)`。 优先考虑相对于基线的比率 (e.g., `rss_growth_factor`) 而不是绝对数字； 绝对阈值仅适用于其定义为无限增长的故障模式。 添加模块级常量实例（e.g.,
   `MY_BUDGET = MyBudget()`).
4. **使用`conftest.py`测试夹具**（`conversation_service`、`bash_service`、`client`、
   `probe`) — 不要创建临时服务。 如果测试需要自定义应用程序配置（e.g.、Webhook 配置），请在测试文件中本地覆盖测试夹具（有关示例，请参阅 `test_slow_webhook.py`）。
5. **使用`scripts.py`助手**进行常见操作：
   - `SlowTestLLM` — `TestLLM` 具有合成的每次调用延迟（使并行性可观察）。
   - `start_conversation_with_test_llm()` — 创建对话，安装 TestLLM，可选择将初始消息排队。
   - `wait_for_terminal()` — 轮询对话状态，直到达到最终状态。
6. **主张预算**，而不是幻数。 在 `assert` 中包含一条诊断消息，解释可能的回归（请参阅现有测试的示例）。
7. **POSIX-only** — 该套件使用 `psutil.num_fds()`、文件锁、bash 管道和 shell 内置命令。 没有 Windows 垫片。

<a id="live-server-integration-tests"></a>

## 实时服务器集成测试

`tests/cross/test_remote_conversation_live_server.py` 中的测试应涵盖对服务器行为的小端点添加或更改。 这些测试启动一个带有补丁的 LLM 的真实 FastAPI 服务器，并端到端地运行完整的 HTTP / WebSocket 堆栈。 每当变更足够本地化，可以在那里添加或扩展一个测试，以捕捉预期的行为。


<a id="verifying-api-changes-against-a-real-server"></a>

## 正在根据真实服务器验证 API 更改

要证明 API 改变了消费者看待它的方式（真实的服务器进程、真实的套接字、重新启动和真实的模型），请使用
[`verify-agent-server`](../.agents/skills/verify-agent-server/SKILL.md) skill:
`control-agent-server map owners --changed origin/main...HEAD` 命名受影响的功能系列，`control-agent-server map run --file Fnn --fresh` 重播系列的配方。 新的或更改的路线需要特征地图中的所有者（`control-agent-server map coverage`）。


<a id="concurrency--async-safety"></a>

## 并发 / 异步安全

- `ConversationState` 使用同步 `FIFOLock`。 在异步智能体-服务器代码中，当会话可能正在运行时，切勿直接在事件循环上执行 `with conversation._state`。
- WebSocket立即重新连接呼叫`EventService.subscribe_to_events()`； 如果初始状态快照创建在异步上下文中的状态锁上阻塞，则整个 FastAPI 事件循环可以停止服务 `/ready` 和类似的探针。
- 相同的规则适用于 `ConversationService.update_conversation()` 中的元数据更新：保留锁定的突变/快照语义，但首先将同步锁等待移至工作线程线程中。
- 在异步路由/服务中，在等待网络 I/O 之前将状态锁获取移至 `run_in_executor(...)`（或另一个工作线程线程边界）。


<a id="rest-api-compatibility--deprecation-policy"></a>

## REST API 兼容性 & 弃用政策

智能体-服务器 **REST API**（`/api/**` 下的 FastAPI OpenAPI 表面）是公共 API，并且在各个版本中必须保持向后兼容。

所有 REST 条合同中断都需要弃用条通知和一条跑道
**5 次版本发布** 在删除旧合同或签订合同之前
不兼容的强制更换。

<a id="deprecating-an-endpoint"></a>

### 弃用端点

当弃用 REST 端点时：

1. 通过将 `deprecated=True` 传递给 FastAPI 路由装饰器，将操作标记为 OpenAPI 中的已弃用。
2. 添加文档字符串注释，其中包括：
   - 已弃用所在的版本
   - 计划删除的版本（默认值：**5 次版本发布** 稍后）
3. **不要**将`openhands.sdk.utils.deprecation.deprecated`用于FastAPI条路线。 该装饰器影响 Python 警告/文档字符串，而不是 OpenAPI，并且在声明的弃用版本之前可能是无操作。

Example:

```py
@router.post("/foo", deprecated=True)
async def foo():
    """做点什么。

    Deprecated since v1.2.3 and scheduled for removal in v1.7.0.
    """
```

确切的句子形状正是 CI 检查所寻找的，因此请保持措辞接近上面的示例。

<a id="deprecating-a-rest-contract-change"></a>

### 弃用 REST 合同变更

如果现有端点的请求或响应模式需要不兼容的更改：

1. **不要**在没有迁移路径的情况下替换旧合约。
2. 在端点文档和发布说明中为旧合同添加弃用通知，包括已弃用中版本和删除目标。
3. 在客户端迁移时，让旧合同在 **5 次版本发布** 内可用。 更喜欢附加模式更改、并行字段或版本化端点或跑道期间的版本化合同。
4. 仅在跑道结束后删除旧合同或强制执行不兼容的形状。

<a id="removing-an-endpoint-or-legacy-contract"></a>

### 删除端点或旧合同

删除端点或之前支持的 REST 合约是不兼容变更。

- 端点且旧合同必须有弃用通知 **5 次版本发布** 在移除之前。
- 任何引入允许的破坏性 REST API 更改的版本都应该在 5 个次要版本弃用跑道之后至少有一个 **MINOR** SemVer 碰撞。

<a id="ci-enforcement"></a>

### CI 执行

流程 `Agent server REST API breakage checks` 比较当前 OpenAPI  模式在之前的 `openhands-agent-server` 从选择的发布 PyPI但是生成基线模式从当前目录下的匹配的 git 标签工作区在 diffing 之前依赖集 [oasdiff](https://github.com/oasdiff/oasdiff).

目前它强制执行：
- FastAPI 路由处理程序不得使用 `openhands.sdk.utils.deprecation.deprecated`。
- 端点该文档弃用在其 OpenAPI 描述中还必须设置
  `deprecated: true`.
- 必须在上一个版本中已经标记为 `deprecated: true`，并且在基线 OpenAPI 描述中记录的计划移除版本已经达到。
- The recognized removal note uses the same wording as the deprecation checks, for example: `Deprecated since v1.14.0 and scheduled for removal in v1.19.0.`
- 其他破坏REST合同的变更未通过检查； 替代品必须额外发货或在版本合同之后发货，直到 5 个次要发布跑道结束。
- CI 检查强制执行弃用跑道，而不是发布范围的 SemVer 策略。 某个版本是否也需要 MINOR 升级仍然取决于该版本中更改的全部范围。

一些合同级别的迁移路径细节仍然依赖于人工审核，因为 OpenAPI 自动化无法完全推断出每个兼容的部署策略。

WebSocket/SSE 端点不在本政策范围内（仅 OpenAPI）。
