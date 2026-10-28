# Package Guidelines

请参阅 [ 项目根 AGENTS.md](../../../AGENTS.md) 了解存储库范围的策略和工作流程。

<a id="package-structure--module-organization"></a>

## 包结构和模块组织

- 此目录 (`openhands-tools/openhands/tools/`) 包含 `openhands.tools.*` 命名空间下的运行时工具实现。
- 大多数工具都位于专用子包中（例如 `terminal/`、`file_editor/`、`browser_use/`），并且通常会拆分：
  - `definition.py`：公共架构/元数据/注册
  - `impl.py` / `core.py`：运行时实现
- 将 `openhands-tools/openhands/tools/__init__.py` 视为 `openhands-tools` 的已发布表面； `__all__` 被认为是公开的 API。

<a id="build-test-and-development-commands"></a>

## 构建、测试和开发命令

- `make build`：设置开发环境（`uv sync --dev`）并安装预提交挂钩。
- `uv run pre-commit run --files <path>`：仅对您触摸的文件运行检查。
- `uv run pytest tests/tools -k <pattern>`：运行工具测试套件； 更喜欢首先运行一个重点子集（e.g. `uv run pytest tests/tools/terminal`).

<a id="coding-style--naming-conventions"></a>

## 编码风格和命名约定

- 软件包支持 Python 3.12 及更高版本； 存储库工具目标 Python 3.13。 保持代码Ruff兼容（行长88）和Pyright友好。
- 工具名称、参数模式和输出模式是面向用户的，并且经常在测试中引用，例如 `tests/tools/test_tool_name_consistency.py`； 避免不兼容变更。 如果模式必须更改，请提供向后兼容加载路径。
- 在添加运行时加载的资产（Jinja `.j2` 模板或 JS `browser_use/js/`）时，请确保它们作为包数据包含（当需要时更新智能体-server PyInstaller 规范）。

<a id="testing-guidelines"></a>

## 测试指南

- 在`tests/tools/`下添加/调整单元测试，镜像工具包。 让测试集中在你改变的行为上。
- 与模拟对象相比，更喜欢真实的代码路径； 当模拟不可避免时 (e.g. 外部进程），将设置集中在 `tests/conftest.py` 或 `tests/tools/<tool>/conftest.py` 中。

<a id="commit--pull-request-guidelines"></a>

## 提交和拉取请求指南

- 将更改范围保持在 tool(s) 所触及的范围内，并在运行更广泛的套件之前运行最小的相关测试。
