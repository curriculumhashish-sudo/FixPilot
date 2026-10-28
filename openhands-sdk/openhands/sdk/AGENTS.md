# Package Guidelines

请参阅 [ 项目根 AGENTS.md](../../../AGENTS.md) 了解存储库范围的策略和工作流程。

<a id="package-structure--module-organization"></a>

## 包结构和模块组织

- 该目录(`openhands-sdk/openhands/sdk/`)包含`openhands.sdk.*`命名空间下的核心PythonSDK。
- 将新模块保留在最近的现有子包（e.g.、`llm/`、`tool/`、`event/`、`agent/`）中，并遵循本地命名模式。
- 在 `tests/sdk/` 下添加/调整单元测试镜像 SDK 路径（例如，对 `openhands-sdk/openhands/sdk/tool/tool.py` 的更改应包含在 `tests/sdk/tool/test_tool.py` 中）。

<a id="build-test-and-development-commands"></a>

## 构建、测试和开发命令

- `make build`：设置开发环境（运行 `uv sync --dev` 并安装预提交挂钩）。
- `make lint`/`make format`：运行Ruff静态检查并格式化。
- `uv run pre-commit run --files <path>`：对您更改的文件运行预提交检查。
- `uv run pytest tests/sdk -k <pattern>`：运行目标SDK测试； 更喜欢首先运行最小的相关测试集。

<a id="coding-style--naming-conventions"></a>

## 编码风格和命名约定

- 软件包支持 Python 3.12 及更高版本； 存储库工具目标 Python 3.13。 保持代码 Ruff 兼容（行长 88）。
- 喜欢明确、准确的类型注释； 使用 Pyright 代替类型检查（不要添加 mypy）。
- 除非没有合理的打字修复，否则避免使用 `# type: ignore`。
- 将导入保留在文件顶部； 除非循环依赖需要，否则避免 `sys.path` 黑客攻击和内联导入。
- 更改 Pydantic 模型或已序列化事件形状时，保留向后兼容性，以便仍可以加载较旧的已持久化数据。

<a id="adding-a-persisted-settings-field"></a>

## 添加已持久化设置字段

当更改已持久化设置模型（例如嵌入它们的 `AgentSettings`、`ConversationSettings` 或智能体-服务器 `PersistedSettings` 载荷）时，请保持向后兼容性显式：

1. 当已持久化 JSON 形状发生不兼容变化时，改变相关的 `schema_version` 常数。
2. 添加相应的`_migrate_*_vN_to_vN+1`函数并将其注册到相应的迁移表中。
3. 在 `tests/sdk/persisted_settings_baselines/vN/` 下添加或更新覆盖历史载荷形状的金色测试夹具。 如果测试夹具依赖于哨兵值的值在迁移过程中存活，记录这些值在测试夹具的顶级 `__expected__` 点的路径映射中，这样检查器就能检测到无声的数据丢失。
4. 运行 `.github/scripts/check_persisted_settings_compat.py`（或 `Persisted settings compatibility checks` 工作流程）以验证基准测试夹具和最新发布的 PyPI 基线是否仍然通过 `from_persisted()` 加载。 PyPI 基线环境与 `uv` 一起安装，使用基线发布上传时间戳作为 `exclude-newer` 截止时间。


<a id="testing-guidelines"></a>

## 测试指南

- 与模拟对象相比，更喜欢真实的代码路径； 重复设置时，在`tests/conftest.py`中引入测试夹具。
- 保持最小化测试并关注改变的行为； 除非需要，否则避免添加广泛的集成测试。

<a id="bedrock--litellm-note"></a>

## 基岩 + LiteLLM 注释

- LiteLLM 将基岩模型的 `api_key` 参数解释为 **AWS 持有者令牌**。 当使用 IAM/SigV4 身份验证（AWS 凭据 / 配置文件）时，对于 Bedrock 模型，请 ** 不 ** 将 `LLM.api_key` 转发到 LiteLLM，否则 Bedrock 可能会返回：
  `Invalid API Key format: Must start with pre-defined prefix`.
- 如果您需要 Bedrock bearer-token auth，请在环境中设置 `AWS_BEARER_TOKEN_BEDROCK`（而不是使用 `LLM_API_KEY`）。
- 对于面向 LiteLLM 的运行时逻辑，首选 `openhands.sdk.llm.utils.litellm_provider.LLMProvider`，而不是手动拆分 `LLM.model`。 接受 SDK 边界处的完整模型字符串，然后立即标准化为 LiteLLM 的已解析的 `provider` + `model` 视图。
- 不要为传输层与功能复制多个提供者对象。 在 `LLM` 设置期间初始化面向 LiteLLM 的传输层提供程序一次，并在规范模型字符串（`LLM.model_canonical_name` 或
  `LLM.model`).
- 避免 `LLM` 中的每次调用提供程序缓存刷新逻辑。 如果提供程序/模型发生更改，请构造一个新的 `LLM` 实例，而不是尝试就地改变传输层提供程序状态。
- Keep `unverified_models` UI 分区保守策略： LiteLLM 推理在有用传输层行为是这样的，但它比UI应该更积极地对模糊的原始ID（例如地区Bedrock ID）进行分类。

<a id="event-type-deprecation-policy"></a>

## 事件类型弃用政策

修改事件类型（e.g.、`TextContent`、`Message` 或事件序列化中使用的任何 Pydantic 模型）时，请遵循以下准则以确保向后兼容性：

<a id="critical-requirement-old-events-must-always-load"></a>

### 关键要求：旧事件必须始终加载

**旧事件应该始终加载而不会出现错误。**生产系统可能会恢复包含事件已序列化与旧 SDK 版本的对话。 不兼容变更至事件模式将导致生产故障。

**重要提示**：已弃用字段处理程序是**永久的**，永远不应删除。 它们确保旧对话始终可以加载，无论它们何时创建。

<a id="when-removing-a-field-from-an-event-type"></a>

### 从事件类型中删除字段时

1. **切勿在没有弃用处理程序的情况下使用 `extra="forbid"` ** - 这将拒绝包含已删除字段的旧事件。

2. **使用 `handle_deprecated_model_fields` 实用程序添加模型验证器来处理已弃用字段 **：
   ```python
   from openhands.sdk.utils.deprecation import handle_deprecated_model_fields

   class MyModel(BaseModel):
       model_config = ConfigDict(extra="forbid")

       # 加载旧事件时，向后兼容性的已弃用字段将被静默删除。 这些被永久保存。
       #
       _DEPRECATED_FIELDS: ClassVar[tuple[str, ...]] = ("old_field_name",)

       @model_validator(mode="before")
       @classmethod
       def _handle_deprecated_fields(cls, data: Any) -> Any:
           """Remove deprecated fields for backward compatibility with old events."""
           return handle_deprecated_model_fields(data, cls._DEPRECATED_FIELDS)
   ```

3. **编写测试来验证新旧事件格式是否正确加载**：
   - 测试旧格式（带有已弃用字段）是否成功加载
   - 测试新格式（不带已弃用字段）是否有效
   - 测试加载一系列混合旧/新事件是否有效

<a id="test-naming-convention-for-event-backward-compatibility-tests"></a>

### 事件向后兼容性测试的测试命名约定

**测试名称中的版本应该是存在特定事件结构的 LAST 版本。**

例如，如果 `enable_truncation` 在 v1.11.1 中被删除，则测试应命名为 `test_v1_10_0_...`（具有该字段的最后一个版本）。

本次公约：
- 明确正在测试哪个版本的格式
- 避免跨多个版本对同一结构进行重复测试
- 记录字段最后出现在模式中的时间

测试名称示例：
- `test_v1_10_0_text_content_with_enable_truncation` - 使用 `enable_truncation` 测试最后一个版本
- `test_v1_9_0_message_with_deprecated_fields` - 使用消息已弃用字段测试最新版本
- `test_text_content_current_format` - 测试当前格式（不需要版本）

<a id="example-see-textcontent-and-message-in-openhandssdkllmmessagepy"></a>

### 示例：参见`openhands/sdk/llm/message.py`中的`TextContent`和`Message`

这些类演示了处理已弃用字段同时维护向后兼容性和已持久化事件的正确模式。

<a id="public-api-removal-policy"></a>

## 公共 API 移除政策

通过 `openhands.sdk.__all__` 导出的符号是 SDK 的公共表面。 两项 CI 政策管理变更：

1. **弃用 before removal** – 在移除公共之前 API 它必须被标记已弃用使用 canonical helpers `openhands.sdk.utils.deprecation`, and the 弃用必须至少声明一个移除目标 **5 次版本发布** 之后 `deprecated_in`.

   这适用于：
   - 从 `openhands.sdk.__all__` 中删除一个符号。
   - 从通过 `openhands.sdk.__all__` 导出的类中删除公共类成员（方法/属性/属性）。

   可接受的弃用标记：
   - `@deprecated(deprecated_in=..., removed_in=...)` 函数/类/方法的装饰器
   - `warn_deprecated(feature, deprecated_in=..., removed_in=...)` 用于运行时路径（e.g.，属性访问器）。 对于成员，请使用限定的功能名称，例如 `"LLM.some_method"`。

   注意：出于删除成员的目的，弃用一个类被视为弃用其成员。

2. **MINOR 版本提升** – 任何不兼容变更（移除或结构）至少需要 MINOR 版本提升。

这些由 `check_sdk_api_breakage.py` 强制执行（在版本 PR 上运行）。 弃用截止日期由 `check_deprecations.py` 单独执行（每 PR 运行一次）。

<a id="documentation-workflow"></a>

## 文档工作流程

文档位于 `sdk/` 文件夹下的 **github.com/OpenHands/docs** 中。 当你添加功能或修改 APIs 时，必须更新文档。

<a id="workflow"></a>

### 工作流程

1. 克隆此存储库旁边的文档存储库：`git clone https://github.com/OpenHands/docs.git ../openhands-docs`
2. 在两个存储库中创建匹配的分支
3. 更新 `openhands-docs/sdk/` 文件夹中的文档
4. **如果您要创建 PR 至 `OpenHands/software-agent-sdk`**，则还必须在 `sdk/` 文件夹中创建相应的 PR 至 `OpenHands/docs` 以及文档更新
5. 在其描述中交叉引用 PR

Example:
```bash
cd ../openhands-docs
git checkout -b <feature-name>
# 编辑 sdk/ 文件夹中的文件
git add sdk/
git commit -m "Document <feature>

Co-authored-by: openhands <openhands@all-hands.dev>"
git push -u origin <feature-name>
```

<a id="running-sdk-examples"></a>

## 运行 SDK 个示例

在实现或修改 `examples/` 中的示例时，请务必在提交之前验证它们是否有效：

```bash
# 使用 All-Hands LLM 代理运行示例
LLM_BASE_URL="https://llm-proxy.eval.all-hands.dev" LLM_API_KEY="$LLM_API_KEY" \
  uv run python examples/01_standalone_sdk/<example_name>.py
```

`LLM_API_KEY` 环境变量可以在 OpenHands 开发环境中使用，并与 All-Hands LLM 代理（`llm-proxy.eval.all-hands.dev` 或 `llm-proxy.app.all-hands.dev`）一起使用。 如果未找到，请咨询用户以获取 LLM 键。

对于使用批评家模型 (e.g., `34_critic_example.py`) 的示例，批评家在使用 All-Hands LLM 代理时会自动配置 - 无需额外设置。

<a id="commit--pull-request-guidelines"></a>

## 提交和拉取请求指南

- 遵循存储库现有的提交风格（简短、命令式的主题； 如果有帮助，请使用范围前缀，例如 `fix(sdk):`）。
- Keep PR focused 更新文档和测试，当更改公共部分时 APIs 用户行为。
