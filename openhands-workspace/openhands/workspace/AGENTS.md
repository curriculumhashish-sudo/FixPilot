# Package Guidelines

请参阅 [ 项目根 AGENTS.md](../../../AGENTS.md) 了解存储库范围的策略和工作流程。

<a id="package-structure--module-organization"></a>

## 包结构和模块组织

- 此目录 (`openhands-workspace/openhands/workspace/`) 包含 `openhands.workspace.*` 命名空间下的工作区实现（Docker、Apptainer、云和 API-远程）。
- 每个后端都位于其自己的子包中（e.g. `docker/`、`cloud/`），并且通常公开 `workspace.py` 中的 `*Workspace` 类。
- 已发布的导入表面为 `openhands-workspace/openhands/workspace/__init__.py` (`__all__` 被视为公共 API)。 保持导入轻量级，因此 `import openhands.workspace` 不会引入构建时依赖项。
- 这些类应与 SDK 工作区接口和类型（例如 `openhands.sdk.workspace.RemoteWorkspace`、`TargetType`、`PlatformType`）保持兼容。

<a id="build-test-and-development-commands"></a>

## 构建、测试和开发命令

- `make build`：设置开发环境（`uv sync --dev`）并安装预提交挂钩。
- `uv run pre-commit run --files <path>`：仅对您更改的文件运行检查。
- `uv run pytest tests/workspace -k <pattern>`：运行工作区测试； 从涵盖您的更改的最窄文件/目录开始。

<a id="coding-style--naming-conventions"></a>

## 编码风格和命名约定

- 软件包支持 Python 3.12 及更高版本； 存储库工具目标 Python 3.13。 保持代码Ruff兼容（行长88）和Pyright友好。
- 更喜欢围绕外部交互的小型、显式包装器（Docker/Apptainer/HTTP）。 尽早验证输入并将副作用操作排除在模块导入时间之外。

<a id="testing-guidelines"></a>

## 测试指南

- 测试位于 `tests/workspace/` 下，通常验证导入行为、模型字段和命令调用。 更喜欢修补命令执行器，而不是在单元测试中需要真正的 Docker。
- 添加针对后端特定行为以及影响公共导入表面的任何更改的重点覆盖范围。

<a id="commit--pull-request-guidelines"></a>

## 提交和拉取请求指南

- 避免将不兼容变更导出到工作区类/符号； 弃用更换公共表面时拆除前。
